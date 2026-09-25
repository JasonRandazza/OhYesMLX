"""Uniform lifecycle over five heterogeneous local runtimes.

One dataclass per runtime behind one interface, because nothing else about them is alike:
``mlx_lm.server`` is Python, Osaurus is a Swift app behind a launcher, oMLX is a CLI shim
that execs an app binary, ``optiq serve`` is an MLX-optimised fork of mlx-lm, and vMLX is an
Electron app whose CLI is one entry point into the engine that app bundles. All five
speak OpenAI-compatible HTTP on loopback; beyond that, each names the same weights
differently and each starts with flags the others would choke on.

    handle = RUNTIMES["osaurus"].start(artifact_dir, "ornith-1.0-35b-jang_4m")
    ...measure...
    handle.stop()          # does not return while the port is held or the process lives

**Readiness is not the port, and for no runtime here is it the model list.**
On a load failure mlx-lm 0.31.3 binds 8081 and logs ``Starting httpd at 127.0.0.1 on port
8081...`` after the load thread has already raised, so a client POST connects and then
hangs forever with zero bytes received. Its ``/v1/models`` handler cannot be believed
either: it lists ``str(Path(--model).resolve())`` straight off disk, so the inventory
returns the right id even when the model was never loaded. oMLX lists every directory it
finds in its catalog the same way, and Osaurus lists a model it then answers ``not
installed or registered with any provider`` for. Both signals are therefore required --
the model id *and* a log with no load failure in it -- and the log is read again once the
id appears, because a runtime writes the failure while it is answering the model list
(docs/research/2026-09-14-oq-portability-spike.md,
docs/research/2026-09-15-grid-loadability-probe.md).

The flag tuples below are ported verbatim from LMRE's ``runtime_adapters``. They are not
defaults, they are pins, and each one costs something when it is left to the runtime.

The cache pin (Phase 6, plan 06-02) is a start-command flag on four of the five runtimes and
a host setting on the fifth. ``cache_state=None`` is the pin not taken, and every runtime
starts exactly as it did before the pin existed. ``"off"`` is prefix/KV reuse disabled and
``"on"`` is enabled, and the value a runtime cannot deliver is refused up front rather than
approximated -- see :meth:`Runtime.cache_state_refusal` and, for the one runtime with no flag
in either direction, :meth:`Osaurus.cache_state_refusal`.

The KV-quantization pin (Phase 4, study 03-05) is the same shape one cache down: the codec a
runtime's KV cache is held in, pinned by name rather than by width (:data:`KV_QUANTS`, which is
where the names and why they are codec names are defined). ``kv_quant=None`` is the pin not
taken and leaves every command byte-identical to the ones recorded before it existed; a value a
runtime cannot deliver is refused up front rather than approximated into a neighbouring codec --
see :meth:`Runtime.kv_quant_refusal`.

Two more pins of the same shape follow, one decode-side and one load-side: ``mtp_depth``
(:data:`MTP_DEPTHS`) and ``stream_experts`` (:data:`STREAM_EXPERTS`). Each carries a second
question the two above do not have, because each flag is accepted on a model that silently falls
back: a depth is only MTP if the artifact carries the heads the runtime will load
(:func:`vmlx_mtp_refusal` and :func:`optiq_mtp_refusal`, both before anything starts), and ``on``
is only streaming if the server's own log says so (:meth:`Runtime.stream_experts_missing`, after
it). The depth pin has a log half too, on the one runtime whose engine is built later than its
start: :meth:`Optiq.mtp_depth_missing`.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .osaurus_settings import (
    DEFAULT_CONFIG_DIR as OSAURUS_CONFIG_DIR,
    MISSING as OSAURUS_MISSING,
    UNREADABLE as OSAURUS_UNREADABLE,
    capture_osaurus_settings,
    describe_drift,
    diff_against_baseline,
    load_baseline,
)

# A 35B takes minutes to load, and a slow cold read of a 20 GB artifact can take more.
READY_TIMEOUT_S = 900.0
READY_POLL_S = 1.0
MODELS_TIMEOUT_S = 5.0
VERSION_TIMEOUT_S = 30.0
STOP_TIMEOUT_S = 30.0
STOP_POLL_S = 0.25
TERM_GRACE_S = 10.0
KILL_GRACE_S = 5.0
# How much of a runtime's log a readiness poll reads. 64 KB was not enough to hold a
# failure: a shape mismatch prints one parameter name per line, so oMLX's fatal line sat
# 1.4 KB inside the 64 KB window on the read that mattered and had scrolled out of it by
# the next one -- the same log reaches 266 KB with its parameter dump printed three times
# (results/logs/omlx-20260915T135626-71559.log: line 2530 at byte 136,891 of 201,042).
# ponytail: a dump longer than this hides the fatal line again; the upgrade path is a
# forward scan that stops at the first failure line instead of reading a window.
LOG_TAIL_BYTES = 1024 * 1024

# How much of a runtime's log a *startup banner* check reads, from the START of the file. The
# two windows are not interchangeable and neither is a second copy of the other: a failure line
# scrolls out of a head, and a banner scrolls out of a tail. Measured over the 781 logs in
# results/logs, every line this check reads sits in the first 8,088 bytes -- OptiQ's mode banner
# at 787 and its pre-load line at 978 (results/logs/optiq-20260920T023332-73621.log), vMLX's
# `Flash MoE enabled:` at 8,088 (results/logs/vmlx-20260920T023513-73621.log) -- and the startup
# banner furthest into any log here is `Native MTP:` at 33,786
# (results/logs/vmlx-20260915T134352-32665.log). A tail window would miss all of them: the log
# that reaches 3,532,257 bytes keeps its head 2.4 MiB below where one would start
# (results/logs/vmlx-20260918T042800-77766.log, `Native MTP:` at 11,154). A banner beyond this
# window is missed, and the direction that fails is a FAILed cell rather than a published number
# under a pin the runtime does not hold.
LOG_HEAD_BYTES = 1024 * 1024

LSOF = shutil.which("lsof") or "/usr/sbin/lsof"
LOGS_DIR = Path(__file__).resolve().parents[1] / "results" / "logs"
OSAURUS_EXECUTABLE = "/Applications/osaurus.app/Contents/MacOS/osaurus"
_RUN_STARTED_PIDS: set[int] = set()

# The two states the cache pin may take. `None` is not a third state: it is the absence of the
# pin, and it must never read as "off" -- the runs measured before the pin existed ran each
# runtime's own default, and those defaults were not uniform (the Osaurus grid columns ran
# with its prefix cache ON). `on` is not "whatever the runtime happens to do" either: it is
# the state whose reuse the run header names, pinned where that runtime has a way to pin it.
CACHE_STATE_OFF = "off"
CACHE_STATE_ON = "on"
CACHE_STATES = (CACHE_STATE_OFF, CACHE_STATE_ON)

# The KV-cache pin's values, and the whole of them. They name the CODEC rather than a bit width,
# because the codec is the thing that has to be held constant and a width alone does not say
# which one it is:
#
#   `off`      the runtime's own native, full-precision cache
#   `affine8`  MLX's affine codec at 8 bits, group size pinned in the start command
#   `affine4`  the same at 4 bits
#
# "Affine" is `mx.quantize`'s default mode -- signed integer codes plus a per-group float scale
# and bias (`mlx/core/__init__.pyi:3396`, and `QuantizedKVCache.update_and_fetch` passes no mode
# of its own). **`fp8` is not one of these values and is not a spelling of `affine8`**: nothing
# in this set has an FP8 (E4M3/E5M2) KV codec, so the earlier study's "FP8" arms were affine
# 8-bit and a name saying float8 is false about what ran. A genuine float8 codec would get its
# own value and its own column on the day one appears, because it would not be comparable with
# `affine8`. `int4`/`int8` are not values either: they read correctly for this affine path and
# falsely for the TurboQuant codebook codecs two of these runtimes also carry, so the codec is
# what gets named and the width stays free for a codec that is not affine. The group size is a
# second variable and is pinned in the command rather than inherited -- `optiq` defaults it to
# 64 (`optiq/cli.py:2504`).
#
# Per-runtime evidence, and which value each can actually be driven into, is
# docs/research/2026-09-24-kv-quant-surface.md (§2.3 for the names, §9 and §11 for the mapping).
# `None` is not a value: it is the pin not taken -- the runs measured before it existed ran each
# runtime's own codec, and those were not uniform -- and it is never read as `off`.
KV_QUANT_OFF = "off"
KV_QUANT_AFFINE8 = "affine8"
KV_QUANT_AFFINE4 = "affine4"
KV_QUANTS = (KV_QUANT_OFF, KV_QUANT_AFFINE8, KV_QUANT_AFFINE4)

# The MTP-depth pin's values, and the whole of them. Two of the five runtimes here have a
# multi-token-prediction depth to pin -- vMLX's native in-model MTP heads and OptiQ's bundled
# head both draft N tokens per verify cycle -- and the values are the depths they accept beside
# an explicit off:
#
#   `off`  MTP not running: vMLX's own kill switch, `--disable-native-mtp` (cli.py:1662-1667);
#          OptiQ's own default, `--mtp` being `is_flag=True, default=False`
#          (optiq/cli.py:2554-2558), so its off is the absence of two flags
#   `1`    one draft token per verify cycle: `--native-mtp-depth 1 --native-mtp-depth-policy
#          fixed`, or `--mtp --mtp-depth 1`
#   `2`, `3`  the same at those depths
#
# The values are strings, `off` beside `1`/`2`/`3`, because the set is a word and three numbers
# and the header value is compared exactly -- the same shape `cache_state` and `kv_quant` have.
# They are not a bit width and not a count of tokens: `--native-mtp-depth` is documented as
# "Starting depth for native in-model MTP heads on preserved-MTP bundles" (cli.py:4304-4314) and
# is capped at `native_mtp_max_depth()`, 3 by default (native_mtp.py:28-44), while OptiQ's own
# help caps it in words -- "acceptance ~70% at depth 2, drops at depth 3+" (optiq/cli.py:2559-2563)
# -- over a `depth <= 0` guard that returns before anything is patched (optiq/serve.py:437-438).
#
# **The policy is part of the value and not a second pin, and only vMLX has one.** vMLX's default
# policy is `adaptive`, which "may also lower the depth on measured acceptance and tries depth 1
# once against the configured depth's measured cost, keeping the measured winner" (cli.py:4324-4331)
# -- so depth can change *within* one request and a cell measured under it is not a cell at depth
# N. `--native-mtp-depth-policy fixed` is therefore passed with every depth, and the adaptive path
# is not reachable through this pin. OptiQ needs no equivalent: its cycle takes `cycle_K = depth`
# once and holds it for the whole call, the HuggingFace-style dynamic-depth adapter having been
# measured at 4-17% *slower* and removed (optiq/runtime/engine.py:897-905, :920).
#
# **Why the other three refuse depth values**, written here once because the reason is a property
# of each runtime and not of this pin. oMLX's MTP is the per-model settings boolean `mtp_enabled`
# -- `mtp_enabled: bool = False` (model_settings.py:303), "Enable native multi-token prediction"
# (:170-171) -- which has no depth of its own; the depth it does carry,
# `mtp_num_draft_tokens: Optional[int] = None` (:304-308), is an adaptive controller's ceiling
# rather than a fixed depth, and no option in `omlx/cli.py` names either. Osaurus's depth is host
# config, `mtp.mode` and `mtp.explicitDepth` ("must be 1, 2, or 3", docs/runtimes/osaurus.md:344)
# in `~/.osaurus/config/server-runtime.json`, with no start-command surface in either direction
# and a force-on that is refused without a `vmlx_mtp_tuning.json` sidecar (docs/runtimes/osaurus.md:900).
# mlx-lm 0.31.3 drops the head at load -- `weights = {k: v for k, v in weights.items() if "mtp."
# not in k}` (`mlx_lm/models/qwen3_5.py:313` in ~/.local/share/ohyesmlx/mlx-lm-0.31.3) -- so there
# is nothing left for a depth to apply to. OptiQ is that same server, and it is the runtime that
# puts a head back: its own loader reads the `optiq/mtp.safetensors` sidecar
# (optiq/runtime/mtp/artifacts.py:104-115).
#
# `None` is not a value: it is the pin not taken -- those runs measured each runtime's own MTP
# default, which for vMLX on a bundle carrying heads is *not* `off` and for OptiQ is `off` -- and
# it is never read as `off`.
MTP_DEPTH_OFF = "off"
MTP_DEPTHS = ("off", "1", "2", "3")

# The two environment variables that make `--native-mtp-depth-policy fixed` actually fixed on
# vMLX 1.6.59, and the whole of the depth pin's second half beside the flag. `fixed` turns off one
# controller and leaves two running:
#
#   * it disables the depth *economics* probe, and only that -- the CLI writes
#     ``VMLINUX_NATIVE_MTP_ADAPTIVE_DEPTH=0`` for the policy (cli.py:1679-1681), which makes
#     ``_native_mtp_adaptive_policy()`` False (mllm_batch_generator.py:6397-6400) and so makes the
#     probe's own default False (``:6403-6418``). The probe's own docstring says what is still
#     live: "With the probe off and ``VMLX_NATIVE_MTP_AR_SAFETY=0`` the depth is pinned; the
#     per-cycle first-draft confidence gate (``VMLX_NATIVE_MTP_DRAFT_MARGIN``) is a separate,
#     older mechanism and still shortens low-confidence drafts."
#   * the AR-safety valve still demotes -- one rung per trip while the depth is above 1
#     (``:6988-7002``), and to plain autoregressive decode at depth 1 (``:7029-7047``), which ends
#     the request in the handoff the log calls ``finish=fallback_to_ar`` (``:18387-18402``). It is
#     on by default (``native_mtp_ar_safety.py:113-114``, ``env_flag(True, ...)``) and is what the
#     CLI's own help names as the mechanism this variable disables: "fixed then never leaves its
#     depth, even when slower than plain decoding" (cli.py:4325-4329).
#   * the sticky start rung still inherits the previous request's demotion -- ``start_depth = 1``
#     when the last request on the engine ended in AR or D1 (``:17275-17286``), gated by
#     ``_native_mtp_reentry_enabled()`` (``:6345-6348``), the same flag shape one variable over.
#
# Both reads take ``0`` as off (``native_mtp_ar_safety.py:89-93``,
# ``mllm_batch_generator.py:5913-5925``); nothing in the engine writes either spelling into
# ``os.environ`` ahead of them, and the process the harness spawns is the one that runs the
# engine -- ``~/.local/bin/vmlx`` execs the bundle's console script, which runs
# ``vmlx_engine.cli.main()`` in place and reaches ``uvicorn.run`` (cli.py:2943) -- so the
# ``env K=V ...`` prefix a depth cell's command carries reaches both readers. The values are
# written rather than left to the ambient environment for that reason: a shell that exported
# either one would otherwise move depth underneath the pin.
#
# `off` and the absent pin pass neither variable and stay byte-identical to the commands recorded
# before this pin existed.
VMLX_MTP_FIXED_ENV = (
    "VMLX_NATIVE_MTP_AR_SAFETY=0",
    "VMLX_NATIVE_MTP_AR_REENTRY=0",
)

# The two lines `Vmlx.mtp_depth_missing` reads out of that log, as patterns rather than as
# substrings: each carries the number the verdict is about. Verbatim shapes, from
# results/logs/vmlx-20260925T063452-16321.log:
#
#   MLLM MTP[chatcmpl-71c1df01] start rung D1 (previous request ended in D1); promotion probe ...
#   MLLM MTP[chatcmpl-71c1df01] accept_by_depth[d1=51/71,d2=5/12,d3=0/0] forwards[...]
_VMLX_START_RUNG = re.compile(r"start rung D(\d+)")
_VMLX_ACCEPT_BY_DEPTH = re.compile(r"accept_by_depth\[([^\]]*)\]")

# Where OptiQ looks for an MTP head when the config does not name one, in its own order. Its
# resolver takes the path the config gives under `mlx_lm_extra_tensors.mtp_file` first and only
# then tries these four spellings, because the sidecar has lived in all of them
# (optiq/runtime/mtp/artifacts.py:104-115, and the subfolder-first/root-fallback pair at
# optiq/sidecar_layout.py:39-50). Copied rather than imported for the reason
# :data:`VMLX_MTP_FAMILIES` is: the table lives inside a package this harness does not depend on.
OPTIQ_MTP_HEAD_RELS = (
    "optiq/mtp.safetensors",
    "mtp.safetensors",
    "mtp/weights.safetensors",
    "model-mtp.safetensors",
)

# vMLX's own MTP family gate, copied deliberately and cited: `_RUNTIME_SUPPORTED_FAMILIES`
# (native_mtp.py:64-79) is the set of families whose draft/verify path vMLX actually wires, and
# `_FAMILY_ALIAS` (native_mtp.py:49-55) is how it normalises their spellings. An artifact can
# carry MTP heads in a family outside this set -- vMLX's own status for one is
# `weights_present_runtime_unwired` (native_mtp.py:1110-1117), and its source records the
# bundles that hit it as measured: "Nemotron 3.5 Lightning (JANG_2L/4M/6M, 34 mtp.layers.0.*
# tensors, num_nextn_predict_layers=1) and Inkling ... ran plain autoregressive with nothing in
# the log to say why" (native_mtp.py:1296-1303) -- and a depth cell there would publish a depth
# the decode never used. This is a copy rather than an import: the table lives
# inside the app bundle, importing it pulls the whole engine in (see :meth:`Vmlx.version_command`)
# and reading its source at run time would be worse. The ceiling is that a vMLX release adding a
# family makes this refuse a cell that could have been measured, which is the conservative
# direction; the upgrade path is to re-read the table from the bundle on each release.
VMLX_MTP_FAMILIES = (
    "qwen3_5",
    "qwen3_5_moe",
    "qwen4_exp",
    "hy_v3",
    "glm5_next",
    "dots3_note",
)
VMLX_MTP_FAMILY_ALIASES = {
    "qwen3_5_text": "qwen3_5",
    "qwen3_6": "qwen3_5",
    "qwen3_6_text": "qwen3_5",
    "qwen3_5_moe_text": "qwen3_5_moe",
    "qwen4_exp_text": "qwen4_exp",
}

# The expert-streaming pin's values, and the whole of them. `on` means the runtime is streaming
# MoE expert weights from SSD on demand instead of holding the fused expert tensors resident --
# OptiQ's `--stream-experts` (optiq/cli.py:3095-3104) and vMLX's `--flash-moe`
# (vmlx_engine/cli.py:3963-3970). `off` means it is not, and for both of these it is a flag that
# has to be passed rather than a default left alone: OptiQ's own default is `auto`, which streams
# a MoE the moment its weights exceed 0.70 of total RAM (`--stream-experts/--no-stream-experts`
# defaults to `None` -> `auto`, optiq/cli.py:2607-2615 and :3095-3096; identical weights then
# decode ~5x slower, with nothing in the artifact explaining it), and vMLX's `--flash-moe`
# is `default=False` (cli.py:3966, and `FlashMoEConfig.enabled: bool = False` at
# flash_moe_config.py:29) -- which is why the harness has pinned `--no-stream-experts` since
# before this pin existed.
#
# **Both runtimes fall back to a resident load silently**, so neither flag is evidence that
# streaming happened and each runtime's own log is: OptiQ's `[optiq.serve] SSD expert streaming:
# on` plus `pre-loaded <path>` (cli.py:3101, serve.py:1654-1662) and vMLX's `Flash MoE enabled:
# <n> layers patched` (server.py:8996-9002). A cell whose log does not show it is FAIL, quoted
# from that log -- see :meth:`Runtime.stream_experts_missing`.
#
# `None` is not a value here either: it is the pin not taken, and the runs measured before it
# existed left each runtime's own default in place -- OptiQ's `auto` for the two cells measured
# without the harness's `--no-stream-experts`, and vMLX's off. Those are not one state.
STREAM_EXPERTS_OFF = "off"
STREAM_EXPERTS_ON = "on"
STREAM_EXPERTS = (STREAM_EXPERTS_OFF, STREAM_EXPERTS_ON)

# Osaurus's `concurrency.smeltMode` is the one place its expert behaviour is decided, and it is
# host state: the enum is `engineSelected | disabled | flashMoE | ssdStreaming`
# (docs/runtimes/osaurus.md:298, and the same four words are in the app binary's key table). It
# is NOT one of `osaurus_settings.TRACKED_KEYS`, so the drift gate does not attest it and the
# refusal below reads it directly. Only `disabled` is a state in which nothing about experts is
# being changed underneath the cell.
OSAURUS_SMELT_DISABLED = "disabled"

# Loopback-only key for a run-owned oMLX. Not a shared secret, and not user state.
OMLX_API_KEY = "ohyesmlx-local"
OMLX_CATALOG_TOKEN = "{OHYESMLX_OMLX_CATALOG}"
OMLX_CATALOG_DIRNAME = "catalog"
OMLX_BASE_DIRNAME = "base"
SAFE_CATALOG_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")

# vMLX's engine source ships inside the app bundle the ``vmlx`` wrapper on PATH execs, and
# the constant in it is the version the running server reports: server.py passes it as the
# FastAPI app version (docs/runtimes/vmlx.md §9.4). There is no version subcommand and
# ``vmlx --version`` exits 2, so this file is where the provenance is.
VMLX_ENGINE_INIT = (
    "/Applications/vMLX.app/Contents/Resources/vmlx-engine-source/vmlx_engine/__init__.py"
)
VMLX_VERSION_SED = r's/^__version__ = "\([^"]*\)".*$/\1/p'

# A line that means the runtime will never answer, whatever the port says. Kept narrow
# on purpose: this gate fails a run, so a pattern that matches ordinary startup chatter
# would make a healthy runtime look broken.
LOG_ERROR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r"^Exception in thread "),
    re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception):\s"),
    re.compile(r"^\[?(?:error|ERROR)\]?[:\s]"),
    re.compile(
        r"\b(?:failed to load|error while loading|unable to load|exited unexpectedly)\b",
        re.IGNORECASE,
    ),
    re.compile(r"Address already in use", re.IGNORECASE),
    re.compile(r"\b(?:Segmentation fault|Abort trap|Bus error|Killed: 9)\b"),
)

# What an inventory poll can raise while a runtime is still coming up.
_TRANSIENT = (OSError, http.client.HTTPException, ValueError, KeyError, TypeError)


class RuntimeLifecycleError(RuntimeError):
    """Base class for a runtime that could not be started or stopped cleanly."""


class RuntimeStartError(RuntimeLifecycleError):
    """A runtime never became ready, or was refused before it was spawned."""


class RuntimeStopError(RuntimeLifecycleError):
    """A runtime did not release its port."""


def _now() -> float:
    return time.monotonic()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _run(command: tuple[str, ...], timeout_s: float):
    """Run a short-lived helper command. ``None`` if it could not be run at all."""
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _spawn(command: tuple[str, ...], log_path: Path) -> int:
    """Start a runtime detached, logging to *log_path*, and return its pid.

    New session, so the tree it creates can be signalled as a group: oMLX starts through
    a shell shim and Osaurus through a launcher, and a signal to the pid alone is not
    guaranteed to reach the server.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "ab", buffering=0) as log:
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as error:
            raise RuntimeStartError(f"could not start {command[0]}: {error}") from error
    return process.pid


def _process_alive(pid: int) -> bool:
    """Whether *pid* is still running, reaping it first when it is our own child.

    Without the reap an exited child stays a zombie, and ``kill(pid, 0)`` keeps
    succeeding on it -- so a stopped runtime would look alive forever.
    """
    try:
        reaped, _status = os.waitpid(pid, os.WNOHANG)
    except OSError:
        pass
    else:
        if reaped == pid:
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _resident_osaurus_pids() -> tuple[int, ...]:
    result = _run(("ps", "-axo", "pid=,args="), STOP_TIMEOUT_S)
    if result is None:
        raise RuntimeStartError(
            "could not inspect running processes for resident Osaurus app instances"
        )
    pids = []
    for line in result.stdout.splitlines():
        pid_text, _, argv = line.strip().partition(" ")
        argv0 = argv.split(maxsplit=1)[:1]
        if pid_text.isdigit() and argv0 and argv0[0] == OSAURUS_EXECUTABLE:
            pid = int(pid_text)
            if pid not in _RUN_STARTED_PIDS and _process_alive(pid):
                pids.append(pid)
    return tuple(pids)


def _signal_tree(pid: int, sig: int) -> None:
    try:
        os.killpg(os.getpgid(pid), sig)
    except ProcessLookupError:
        return
    except PermissionError as error:
        raise RuntimeStopError(
            f"permission denied signalling process group of {pid}"
        ) from error


def _signal_process(pid: int, sig: int) -> None:
    """Signal one pid, and only it.

    Deliberately not the process group. A pid recovered from the port belongs to a runtime's
    own launcher, whose grouping this harness never established -- ``osaurus serve`` hands
    the port to an app process by a mechanism of its own -- and a group signal could reach
    something this run has no claim on.
    """
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        return
    except PermissionError as error:
        raise RuntimeStopError(f"permission denied signalling process {pid}") from error


def _port_is_free(port: int) -> bool:
    """Whether nothing is listening on *port*, per ``lsof``.

    A port this cannot be verified on is reported as busy: the caller is deciding
    whether to hand a port to a runtime or to let a run finish, and in both cases
    "unknown" has to mean "not free yet".
    """
    result = _run((LSOF, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"), STOP_TIMEOUT_S)
    if result is None:
        return False
    return not result.stdout.strip()


def _listener_pids(port: int) -> tuple[int, ...] | None:
    """The pids listening on *port* right now, per ``lsof -t``.

    This is how a process a runtime's launcher handed off to is named. ``osaurus serve``
    starts the app, prints ``listening on http://127.0.0.1:1337`` and exits, so the pid this
    run spawned is not the one holding the weights -- and once ``osaurus stop`` has freed the
    port there is nothing left to find it by. So it is read while the port is still held.

    Reading it is only ever a claim about a process this run started: :meth:`Runtime.start`
    refuses to spawn over a listener it did not create, so anything listening on the port
    after that check appeared because this run spawned a runtime onto it.
    """
    result = _run((LSOF, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"), STOP_TIMEOUT_S)
    if result is None:
        return None
    return tuple(
        dict.fromkeys(
            int(line) for line in result.stdout.split() if line.strip().isdigit()
        )
    )


def _serving_pid(spawned: int, port: int) -> int:
    """The pid actually holding the weights, which is not always the one that was spawned.

    ``osaurus serve`` starts the app, prints the address it is listening on and exits, so a
    sampler pointed at the spawned pid measures a launcher on its way out -- 4.7 MB from a
    single sample, against 2,699-4,172 MB and 11-14 samples from every runtime that stays.
    The port names the survivor, on the same claim :func:`_listener_pids` documents: a
    listener that appeared after :meth:`Runtime.start` refused to spawn over one is ours.

    The spawned pid is kept whenever the port cannot improve on it: nothing listening,
    the spawned pid already listening, or more than one distinct listener. An unreadable
    port is not a licence to sample a stranger's memory and publish it as this cell's.
    """
    listeners = _listener_pids(port)
    if listeners is not None and len(listeners) == 1 and spawned not in listeners:
        return listeners[0]
    return spawned


def _read_log(path: Path) -> str:
    """The tail of a runtime's log, or ``""`` when there is nothing to read yet."""
    try:
        with open(path, "rb") as log:
            log.seek(0, os.SEEK_END)
            size = log.tell()
            log.seek(max(0, size - LOG_TAIL_BYTES))
            return log.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _read_log_head(path: Path) -> str:
    """The head of a runtime's log, or ``""`` when there is nothing to read yet.

    The startup banner's window, not the failure line's: see :data:`LOG_HEAD_BYTES`.
    """
    try:
        with open(path, "rb") as log:
            return log.read(LOG_HEAD_BYTES).decode("utf-8", "replace")
    except OSError:
        return ""


def _read_log_all(path: Path) -> str:
    """The whole of a runtime's log, or ``""`` when there is nothing to read yet.

    The third window this module reads, and the one a *per-request* claim needs: a start banner
    is in the head (:func:`_read_log_head`) and a failure line is in the tail (:func:`_read_log`),
    but a request's own accounting -- its start rung, its finish, its ``accept_by_depth`` row -- is
    written once per request for as long as the server runs, so any fixed window at one end is a
    window on part of the visit's requests. The whole file is the definition because the file is
    the visit's: one ``vmlx serve`` process writes one log, and these logs are a few hundred KB
    (the two depth runs of 2026-09-25 are ~290-300 KB), so the read is bounded by the visit and
    not by a copy budget. An unreadable or absent file answers ``""`` -- the absence of evidence,
    which every caller reports rather than passes.
    """
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _banner_evidence(
    name: str,
    log_path: str | None,
    *,
    claim: str,
    required: tuple[str, ...],
    fallback: tuple[str, ...],
    banner_why: str,
    fallback_why: str,
) -> str | None:
    """Why a runtime's own log does not show *claim*, or ``None`` when it does.

    ``required`` is every line the runtime prints when *claim* really holds, and ``fallback`` is
    the lines it prints instead when it does not -- the same set that makes a flag in a command
    no evidence at all. A log that carries no fallback line either says so rather than quoting
    nothing: the absence is the finding, and the log path is what a reader follows.

    Both halves of the two pins that follow this pattern read their evidence here, because it is
    one reading of one window (:data:`LOG_HEAD_BYTES`) and two copies of it would be two places
    for the same check to drift: :meth:`Runtime.stream_experts_missing` for the streaming pin and
    :meth:`Optiq.mtp_depth_missing` for the depth pin. What a caller supplies beyond the markers
    is the prose around them -- *banner_why*, why a banner is evidence of the claim at all, and
    *fallback_why*, what the runtime did instead of it.
    """
    if log_path is None:
        return (
            f"{claim} cannot be verified on {name}: this run was started without a log path, "
            f"and {banner_why}. This cell is FAIL rather than a number published under a pin "
            "nothing checked."
        )
    text = _read_log_head(Path(log_path))
    missing = [marker for marker in required if marker not in text]
    if not missing:
        return None
    quoted = next(
        (
            line.strip()
            for line in text.splitlines()
            if any(marker in line for marker in fallback)
        ),
        None,
    )
    if quoted is None:
        # The absence is the finding and the cause is not known, so it is not guessed at: the
        # line this check reads may simply be beyond the head window (see LOG_HEAD_BYTES).
        return (
            f"{claim} was not delivered: {name}'s own log never printed {missing[0]!r}, and it "
            "says nothing about why. The flag was accepted, so this cell is FAIL rather than a "
            f"number published under a pin nothing confirmed (log: {log_path})."
        )
    return (
        f"{claim} was not delivered: {name}'s own log never printed {missing[0]!r}, and it says "
        f"{quoted!r} instead. The flag was accepted and {fallback_why}, so this cell is FAIL "
        "rather than a number published under a pin it does not hold "
        f"(log: {log_path})."
    )


def _stream_evidence(
    name: str,
    log_path: str | None,
    *,
    required: tuple[str, ...],
    fallback: tuple[str, ...],
) -> str | None:
    """Why a runtime's log does not show expert streaming, or ``None`` when it does.

    The streaming pin's reading of :func:`_banner_evidence`: *claim* is the pin's own `on`, and
    the prose is why a streaming banner is evidence -- the two runtimes that take the flag both
    load resident without failing anything when they cannot stream.
    """
    return _banner_evidence(
        name,
        log_path,
        claim="stream_experts='on'",
        required=required,
        fallback=fallback,
        banner_why=(
            "the runtime's own banner is the evidence that streaming is on rather than falling "
            "back to a resident load"
        ),
        fallback_why="the load fell back to the resident path",
    )


def _read_json_object(path: Path) -> dict | None:
    """One JSON object off disk, or ``None`` when it is absent, unreadable or not an object."""
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _log_path(name: str) -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    return LOGS_DIR / f"{name}-{stamp}-{os.getpid()}.log"


def osaurus_smelt_mode() -> object:
    """The host's ``concurrency.smeltMode``, which decides Osaurus's expert behaviour.

    Not one of ``osaurus_settings.TRACKED_KEYS``, so the drift gate does not attest it and it is
    read here instead: the same file, and the same two sentinels, so an unreadable host is
    visibly unreadable rather than indistinguishable from a default one. The enum is
    ``engineSelected | disabled | flashMoE | ssdStreaming`` (:data:`OSAURUS_SMELT_DISABLED`) --
    one of them changes how many experts are resident, and none of them is visible in a start
    command.
    """
    payload = _read_json_object(OSAURUS_CONFIG_DIR / "server-runtime.json")
    if payload is None:
        return OSAURUS_UNREADABLE
    cursor: object = payload
    for part in ("concurrency", "smeltMode"):
        if not isinstance(cursor, dict) or part not in cursor:
            return OSAURUS_MISSING
        cursor = cursor[part]
    return cursor


def vmlx_mtp_refusal(artifact_dir: str) -> str | None:
    """Why vMLX cannot be measured at an MTP depth on this artifact, or ``None`` when it can.

    Four checks, each cited where it is applied and each with its own reason below: the family
    must be one vMLX wires (``native_mtp.py:64-79``), the bundle must not declare MTP dropped
    (``:883-925``), the config must declare an MTP layer (``:538-546``), and the index must carry
    ``mtp.*`` tensors (``:606-611``). Together they are vMLX's own ``artifact_available`` and
    ``runtime_supported`` (``:1012-1021``) read off the files, and the reason they are read here
    rather than from the log is vMLX's own measured note (``native_mtp.py:1296-1303``): a bundle
    that declares MTP but is not runtime-supported "used to deactivate in total silence, so the
    model ran plain autoregressive with nothing in the log to say why", and the banner is still
    skipped altogether for a ``not_configured`` bundle (``cli.py:2441``).

    The accepted case is a bundle on this host: ``models--JANGQ-AI--Qwen3.5-4B-JANG_4S`` declares
    one MTP layer, indexes 31 ``mtp.layers.0.*`` tensors under family ``qwen3_5``, and its
    recorded start log carries ``Qwen3.5/3.6 MTP model adapter applied``
    (results/logs/vmlx-20260924T032906-11424.log:38).

    # ponytail: an artifact with no ``model.safetensors.index.json`` cannot be enumerated, so a
    # depth cell on one is refused. vMLX reads the safetensors headers directly for those
    # (``native_mtp.py:189-212``, ``safe_open``), a dependency this harness does not carry; the
    # upgrade path is a header reader over that format's own 8-byte length prefix.
    """
    bundle = Path(artifact_dir)
    config = _read_json_object(bundle / "config.json")
    if config is None:
        return (
            f"mtp_depth cannot be pinned on {artifact_dir}: there is no readable config.json, so "
            "the MTP layers the depth would apply to cannot be established from the artifact. "
            "vMLX accepts --native-mtp-depth on a bundle with no MTP heads and decodes plain "
            "autoregressive without saying so, so this cell is N/A at a depth rather than "
            "measured as MTP."
        )
    jang = _read_json_object(bundle / "jang_config.json") or {}
    if not jang:
        # The sidecar may be embedded in config.json instead of standing beside it
        # (native_mtp.py:95-106).
        embedded = config.get("jang_config", config.get("jang"))
        jang = embedded if isinstance(embedded, dict) else {}

    # The family, resolved the way `_bundle_family` resolves it (native_mtp.py:236-248): the
    # stamped capability first, then the config's own model_type, then the one under text_config.
    capabilities = jang.get("capabilities")
    capabilities = capabilities if isinstance(capabilities, dict) else {}
    text_config = config.get("text_config")
    text_config = text_config if isinstance(text_config, dict) else {}
    family = None
    for raw in (capabilities.get("family"), config.get("model_type"), text_config.get("model_type")):
        name = str(raw).strip().lower() if isinstance(raw, str) and raw.strip() else None
        if name:
            family = VMLX_MTP_FAMILY_ALIASES.get(name, name)
            if family != "unknown":
                break
    if family not in VMLX_MTP_FAMILIES:
        return (
            f"mtp_depth cannot be pinned on {artifact_dir}: its family is {family or 'unstated'}, "
            f"and vMLX wires an MTP draft/verify path for {VMLX_MTP_FAMILIES} only "
            "(native_mtp.py:64-79). A bundle outside that set reads "
            "'weights_present_runtime_unwired' (native_mtp.py:1110-1117) even when its MTP "
            "heads are on disk, so a depth cell here would publish a depth the decode never "
            "used. This cell is N/A at a depth rather than measured as MTP."
        )

    # Whether the bundle drops MTP, by every route `native_mtp_status` reads it
    # (native_mtp.py:883-925): the explicit boolean, the sidecar's own flags and stamped mode,
    # and the runtime block's `bundle_has_mtp`.
    mtp_sidecar = jang.get("mtp") if isinstance(jang.get("mtp"), dict) else {}
    runtime_sidecar = jang.get("runtime") if isinstance(jang.get("runtime"), dict) else {}
    stamped_mode = str(mtp_sidecar.get("mtp_mode") or "").strip().lower()
    dropped = (
        jang.get("drop_mtp") is True
        or mtp_sidecar.get("enabled") is False
        or mtp_sidecar.get("kept") is False
        or stamped_mode in {"none", "absent", "disabled", "off"}
        or runtime_sidecar.get("bundle_has_mtp") is False
    )
    if dropped:
        return (
            f"mtp_depth cannot be pinned on {artifact_dir}: the bundle declares MTP dropped -- "
            "jang_config.drop_mtp, mtp.enabled/kept, the stamped mtp.mtp_mode or "
            "runtime.bundle_has_mtp says so (native_mtp.py:883-925) -- so no draft head is "
            "loaded and a depth cell here would publish a depth the decode never used. This "
            "cell is N/A at a depth rather than measured as MTP."
        )

    # Whether the config asks for MTP layers at all, from every source
    # `_config_mtp_layer_count` reads (native_mtp.py:537-571): the config and its text_config,
    # then the sidecar's own counts.
    declared = None
    for raw in (
        config.get("num_nextn_predict_layers"),
        config.get("mtp_num_hidden_layers"),
        text_config.get("num_nextn_predict_layers"),
        text_config.get("mtp_num_hidden_layers"),
        runtime_sidecar.get("mtp_layers"),
        mtp_sidecar.get("num_layers"),
        mtp_sidecar.get("num_hidden_layers"),
    ):
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            declared = value
            break
    if declared is None:
        return (
            f"mtp_depth cannot be pinned on {artifact_dir}: neither config.json nor "
            "jang_config.json declares an MTP layer -- num_nextn_predict_layers, "
            "mtp_num_hidden_layers, runtime.mtp_layers or mtp.num_layers (native_mtp.py:537-571) "
            "-- so vMLX's own status for this bundle is 'metadata_inconsistent' or "
            "'configured_without_runtime' (native_mtp.py:1071-1072, :1130) and its decode runs "
            "without a draft head. This cell is N/A at a depth rather than measured as MTP."
        )

    # Whether the weights carry MTP tensors, by the key pattern `_mtp_keys_from_weight_keys`
    # matches (native_mtp.py:606-611). The index is the only enumeration available without a
    # dependency; see the ceiling note above.
    index = _read_json_object(bundle / "model.safetensors.index.json")
    weight_map = index.get("weight_map") if isinstance(index, dict) else None
    if not isinstance(weight_map, dict):
        return (
            f"mtp_depth cannot be pinned on {artifact_dir}: the artifact has no readable "
            "model.safetensors.index.json, so its tensors cannot be enumerated and the MTP "
            "heads a depth would drive cannot be shown to exist. This cell is N/A at a depth "
            "rather than measured as MTP."
        )
    mtp_keys = [
        str(key) for key in weight_map if re.search(r"(^|\.)mtp(\.|$)", str(key))
    ]
    if not mtp_keys:
        return (
            f"mtp_depth cannot be pinned on {artifact_dir}: its safetensors index holds no "
            "mtp.* tensors, so vMLX loads no draft head however the depth flag is spelled "
            "(native_mtp.py:944, :1012-1018) and its own banner is suppressed for a "
            "not_configured bundle (cli.py:2441). A depth cell here would decode plain "
            "autoregressive and publish as MTP; it is N/A at a depth instead."
        )
    return None


def optiq_mtp_refusal(artifact_dir: str) -> str | None:
    """Why OptiQ cannot be measured at an MTP depth on this artifact, or ``None`` when it can.

    Two checks, both read off the files before anything is started and both OptiQ's own: the
    config must declare an MTP layer (``_num_mtp_layers``, ``mtp_patch.py:69-76``, whose answer
    of zero sends the injector home before it looks for a head at ``:382-385``), and the head
    file must be where its resolver looks (``expected_mtp_file``, ``mtp/artifacts.py:104-115``:
    the path the config names under ``mlx_lm_extra_tensors.mtp_file`` first, then the four
    spellings of :data:`OPTIQ_MTP_HEAD_RELS`).

    Why up front rather than only from the log, when this runtime does not fall back quietly:
    it fails **loudly but late**. With ``--mtp`` and no head it attaches one anyway, logs a
    single warning (``MTP head not attached (...)``, ``engine.py:297-304``) and then raises at
    the first request, which is answered to the client as HTTP 404 with that text in the body
    and nothing in the log (``serve.py:459-464``, ``mlx_lm/server.py:1424-1427``). So a cell
    refused here is N/A with this reason and costs no model load, and the second half -- that a
    head really attached -- is asked of the log after the start, by
    :meth:`Optiq.mtp_depth_missing`.

    The accepted case is on this host: both of ``mlx-community/Qwen3.5-4B-OptiQ-4bit`` and
    ``mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit`` name ``optiq/mtp.safetensors`` in
    ``mlx_lm_extra_tensors.mtp_file`` and declare ``mtp_num_hidden_layers: 1``, and the 35B
    sidecar is 1,644,816,560 B on disk.

    # ponytail: an artifact carrying ``mtp.*`` tensors in its *main* weights is refused here,
    # and OptiQ can read those too (``_embedded_mtp_weight_map``, ``mtp_patch.py:277-299``). That
    # route is not opened on purpose: every OptiQ quant on this host ships the sidecar, and
    # accepting the embedded one would mean this harness judging a head's completeness from an
    # index. The ceiling is a false refusal, which costs a cell rather than a number.
    """
    bundle = Path(artifact_dir)
    config = _read_json_object(bundle / "config.json")
    if config is None:
        return (
            f"mtp_depth cannot be pinned on {artifact_dir}: there is no readable config.json, so "
            "the MTP layer and the head OptiQ would build from it cannot be established from the "
            "artifact. This cell is N/A at a depth rather than measured at one no decode may "
            "have used."
        )

    # The layer count, from every source `_num_mtp_layers` reads (mtp_patch.py:69-76): the
    # config's own, then the two under text_config.
    text_config = config.get("text_config")
    text_config = text_config if isinstance(text_config, dict) else {}
    declared = None
    for raw in (
        text_config.get("mtp_num_hidden_layers"),
        text_config.get("num_nextn_predict_layers"),
        config.get("num_nextn_predict_layers"),
    ):
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            declared = value
            break
    if declared is None:
        return (
            f"mtp_depth cannot be pinned on {artifact_dir}: neither config.json nor its "
            "text_config declares an MTP layer -- mtp_num_hidden_layers or "
            "num_nextn_predict_layers (mtp_patch.py:69-76) -- so OptiQ's injector returns before "
            "it looks for a head (:382-385), the engine attaches without one (:297-304) and "
            "every request is answered HTTP 404 (serve.py:459-464). A depth cell here would "
            "publish a depth no decode used; it is N/A at a depth instead."
        )

    # The head file, resolved the way `expected_mtp_file` resolves it: the config's own answer
    # wins, and the four spellings are tried only when it gives none.
    extra = config.get("mlx_lm_extra_tensors")
    named = extra.get("mtp_file") if isinstance(extra, dict) else None
    if isinstance(named, str) and named.strip():
        candidates = (bundle / named,)
    else:
        candidates = tuple(bundle / rel for rel in OPTIQ_MTP_HEAD_RELS)
    if not any(candidate.exists() for candidate in candidates):
        return (
            f"mtp_depth cannot be pinned on {artifact_dir}: no MTP head is where OptiQ resolves "
            "one -- looked for "
            + ", ".join(str(candidate) for candidate in candidates)
            + " (mtp/artifacts.py:104-115) -- so --mtp attaches an engine with no draft head and "
            "answers every request HTTP 404 (serve.py:459-464, mlx_lm/server.py:1424-1427). This "
            "cell is N/A at a depth rather than measured at one the decode never used."
        )
    return None


def log_load_error(text: str) -> str | None:
    """The load failure visible in a runtime's log, or ``None`` when the log is clean.

    The *last* match is returned, not the first: a Python traceback names its cause on
    its final line (``ValueError: Model type gemma4_unified not supported.``), and the
    first is only ever the marker that says one is coming.
    """
    found = None
    for line in text.splitlines():
        if any(pattern.search(line) for pattern in LOG_ERROR_PATTERNS):
            found = line.strip()
    return found


def _raise_on_log_error(name: str, log_path: Path) -> None:
    """Raise when the runtime's log reports a load failure, and only then.

    Called before the model list is polled and again after it has answered with one of our
    ids. The second read is what catches a runtime that lists a model it cannot serve, and
    it has to happen second: the failure is written *while* the model list is being
    answered -- live, oMLX answered ``GET /v1/models`` with a JANG artifact at 13:56:29,1xx
    and the VLM path had failed on it at 13:56:29,130
    (results/logs/omlx-20260915T135626-71559.log).
    """
    error = log_load_error(_read_log(log_path))
    if error is not None:
        raise RuntimeStartError(f"{name} failed to load: {error} (log: {log_path})")


def _inventory(base_url: str, *, api_key: str | None = None) -> tuple[str, ...]:
    """The model ids a runtime is currently offering."""
    request = urllib.request.Request(f"{base_url}/models")
    if api_key:
        request.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(request, timeout=MODELS_TIMEOUT_S) as response:
        payload = json.loads(response.read())
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise ValueError(f"unrecognised model list from {base_url}")
    return tuple(
        entry["id"]
        for entry in data
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    )


def _hub_repo_parts(name: str) -> tuple[str, str] | None:
    """``(organization, repository)`` out of one ``models--<org>--<name>`` path component.

    The hub's flat layout, parsed in one place for both spellings that need it: Osaurus
    takes the repository alone and lowercases it, and vMLX takes the pair as the path holds
    it. ``None`` when the component is not a repo directory or either half is empty.
    """
    if not name.startswith("models--"):
        return None
    organization, _, repository = name[len("models--") :].partition("--")
    if organization and repository:
        return organization, repository
    return None


def hub_repo_name(artifact_dir: str) -> str | None:
    """The repo an HF-cache artifact belongs to, lowercased, or ``None`` if it is not one.

    The hub lays a repo out as ``models--<org>--<name>/snapshots/<commit>``, so the
    directory a cell is handed is the commit hash and ``name_forms`` can derive nothing
    but hashes from it. The repo's name survives only in the ``models--<org>--<name>``
    directory above ``snapshots/``, and Osaurus serves every model under it, lowercased:
    the live inventory reads ``qwen3.5-4b-oq4``, ``ornith-1.0-35b-jang_4m``, and so on.
    """
    for part in Path(os.path.abspath(artifact_dir)).parts:
        found = _hub_repo_parts(part)
        if found is not None:
            return found[1].lower()
    return None


def name_forms(artifact_dir: str) -> tuple[str, ...]:
    """Every name one artifact is served under, derived from its directory.

    Ported from LMRE's model-ID alias registry. The forms are the ones actually observed
    between these runtimes and that project's cells: the HF repo id (``mlx-community/X``),
    the flat-hub spelling (``mlx-community__X``), the routed spelling Osaurus gives an
    oMLX model (``omlx/X``), and the artifact directory itself, which is what
    ``mlx_lm.server`` and ``optiq serve`` report.
    """
    path = Path(os.path.abspath(artifact_dir))
    forms = [path.name]
    if path.parent.name:
        forms += [f"{path.parent.name}/{path.name}", f"{path.parent.name}__{path.name}"]
    forms += [f"omlx/{path.name}", str(path)]
    return _ordered(forms)


def _ordered(*groups) -> tuple[str, ...]:
    """The names in priority order, first mention winning and nothing repeated."""
    seen: dict[str, None] = {}
    for group in groups:
        for name in group:
            if name:
                seen.setdefault(name, None)
    return tuple(seen)


def resolve_model_id(candidates: tuple[str, ...], inventory: tuple[str, ...]) -> str | None:
    """The name the runtime itself is using, or ``None`` if it is offering none of them.

    The match is returned as the runtime spells it, never as it was asked for: a handle
    carries what the server answers to, because that is what a request must name.
    """
    available = set(inventory)
    for candidate in candidates:
        if candidate in available:
            return candidate
    return None


@dataclass(frozen=True)
class OmlxScratch:
    """The per-run directories an oMLX start is given, all under one removable root."""

    root: Path
    catalog: Path
    base: Path
    link_name: str


def omlx_link_name(artifact_dir: str, model_id: str) -> str:
    """The name oMLX will serve the weights under.

    A catalog entry cannot contain a slash, so the HF repo id spelling is unavailable
    here and the artifact's own directory name is the last resort -- which is what
    LMRE's oMLX cells used.
    """
    for candidate in (model_id, *name_forms(artifact_dir)):
        if SAFE_CATALOG_NAME.fullmatch(candidate):
            return candidate
    raise RuntimeStartError(f"no safe oMLX catalog name for {artifact_dir!r}")


def create_omlx_scratch(artifact_dir: str, model_id: str) -> OmlxScratch:
    """A fresh model catalog and base path for oMLX, holding exactly one model.

    oMLX serves whatever directory ``--model-dir`` points at, so a directory holding one
    symlink is how a cell is made to see only its own model. The base path is per-run for
    the same class of reason: oMLX writes catalog settings under it, and they must not
    land in the user's own configuration.
    """
    artifact = Path(artifact_dir).resolve()
    if not artifact.is_dir():
        raise RuntimeStartError(f"artifact is not a directory: {artifact_dir}")
    root = Path(tempfile.mkdtemp(prefix="ohyesmlx-omlx-"))
    try:
        catalog = root / OMLX_CATALOG_DIRNAME
        base = root / OMLX_BASE_DIRNAME
        catalog.mkdir()
        base.mkdir()
        link_name = omlx_link_name(artifact_dir, model_id)
        (catalog / link_name).symlink_to(artifact, target_is_directory=True)
        return OmlxScratch(root=root, catalog=catalog, base=base, link_name=link_name)
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise


def remove_omlx_catalog(catalog: Path) -> None:
    """Remove a catalog this process created, and nothing else.

    Every entry is checked to be a symlink before it is unlinked. A directory of symlinks
    is a thing this module made; a recursive delete of a path whose contents were not
    checked is how a harness eats a model directory.
    """
    if not catalog.exists():
        return
    for child in sorted(catalog.iterdir()):
        if not child.is_symlink():
            raise RuntimeStopError(f"oMLX catalog holds a non-symlink entry: {child}")
        child.unlink()
    catalog.rmdir()


def _remove_scratch(scratch: str | None) -> None:
    """Drop a failed start's leftovers. Never raises: it runs beside a real error."""
    if scratch is None:
        return
    root = Path(scratch)
    try:
        remove_omlx_catalog(root / OMLX_CATALOG_DIRNAME)
        shutil.rmtree(root, ignore_errors=True)
    except (OSError, RuntimeStopError):
        pass


def _await_exit(pid: int, timeout_s: float) -> bool:
    deadline = _now() + timeout_s
    while _process_alive(pid):
        if _now() >= deadline:
            return False
        _sleep(STOP_POLL_S)
    return True


def _kill_resident(pids: tuple[int, ...]) -> None:
    """Kill what a runtime's own stop command left behind, and wait for it to go.

    ``osaurus stop`` frees port 1337 and leaves the app process resident, still holding the
    weights: a freed port satisfies the one-runtime-holds-weights rule's letter and breaks
    its substance, and a grid run would leak about one such process per cell into the memory
    it is trying to measure. SIGTERM is ignored by these instances, so the escalation ladder
    that :func:`_shutdown` walks for a spawned pid would only be ten seconds of waiting for
    the same outcome.
    """
    for pid in pids:
        if not _process_alive(pid):
            continue
        _signal_process(pid, signal.SIGKILL)
        if not _await_exit(pid, KILL_GRACE_S):
            raise RuntimeStopError(
                f"process {pid} was still listening on this runtime's port and is alive "
                f"{KILL_GRACE_S:g}s after SIGKILL"
            )


def await_port_free(port: int, timeout_s: float = STOP_TIMEOUT_S) -> None:
    """Block until nothing is listening on *port*, or raise.

    A run that does not release its port has failed, whatever else it reported, so this
    is the last thing every stop does.
    """
    deadline = _now() + timeout_s
    while True:
        if _port_is_free(port):
            return
        if _now() >= deadline:
            raise RuntimeStopError(
                f"port {port} is still held {timeout_s:g}s after stopping; "
                f"check `{LSOF} -nP -iTCP:{port} -sTCP:LISTEN`"
            )
        _sleep(STOP_POLL_S)


def _shutdown(pid: int, port: int, stop_command: tuple[str, ...] = ()) -> None:
    """Take a runtime down and do not return until its port is free and its processes gone.

    The listeners are read *before* the stop command runs, because the stop command is what
    frees the port and a process it leaves behind can no longer be named by that port
    afterwards. The pid this run spawned is one candidate; every other pid listening on the
    port is a process the runtime's launcher started out of this run's spawn, and is killed
    on its own pid rather than as a group (see :func:`_signal_process`).
    """
    listeners = _listener_pids(port)
    if listeners is None and stop_command:
        raise RuntimeStopError(
            f"cannot identify listeners on port {port}; refusing handoff cleanup"
        )
    if listeners is None:
        listeners = ()
    if stop_command:
        _run(stop_command, STOP_TIMEOUT_S)
    if _process_alive(pid):
        _signal_tree(pid, signal.SIGTERM)
        if not _await_exit(pid, TERM_GRACE_S):
            _signal_tree(pid, signal.SIGKILL)
            if not _await_exit(pid, KILL_GRACE_S):
                raise RuntimeStopError(
                    f"spawned process {pid} is still alive {KILL_GRACE_S:g}s after SIGKILL"
                )
    _kill_resident(tuple(other for other in listeners if other != pid))
    await_port_free(port)


@dataclass
class Handle:
    """One running runtime.

    The pinned fields come first, and ``first_request_s`` is the last of them: the latency of
    the cold visit's first warmup request, which is where a runtime that loads its weights
    lazily pays for them. ``cold_load_s`` is only a time-to-listening for one of those, so a
    cross-runtime load comparison uses the sum. The measurement loop fills it in when that
    request lands, because the request is its to make. Everything after it is lifecycle state
    the handle needs to release its own port and to be addressed to, and carries the same
    defaults an interface-shaped construction would give it.
    """

    pid: int
    port: int
    base_url: str
    model_id: str
    version: str
    cold_load_s: float
    first_request_s: float | None = None
    # The pid to sample memory from, when the launcher that was spawned is not the process
    # that ended up holding the weights. ``None`` means the spawned pid is the server.
    serving_pid: int | None = None
    stop_command: tuple[str, ...] = ()
    scratch: str | None = None
    # The credential the runtime was started with. Measured requests must send it: oMLX
    # answers an unauthenticated /v1/chat/completions with 401, and the readiness probe
    # authenticating while the measurement did not is how that went unnoticed.
    api_key: str | None = None
    # Where this start's stdout and stderr went. It is the server's own account of itself --
    # the readiness rule already reads it for a load failure -- and it is the only place a
    # pin the runtime can silently decline is visible: OptiQ and vMLX both accept an
    # expert-streaming flag on a model they cannot stream and fall back without failing
    # anything. ``None`` on a handle built without a spawn.
    log_path: str | None = None

    @property
    def memory_pid(self) -> int:
        """The pid whose footprint is this runtime's. See :func:`_serving_pid`."""
        return self.pid if self.serving_pid is None else self.serving_pid

    def stop(self) -> None:
        """Stop the runtime. Does not return until the port is free."""
        _shutdown(self.pid, self.port, self.stop_command)
        _RUN_STARTED_PIDS.discard(self.pid)
        if self.serving_pid is not None:
            _RUN_STARTED_PIDS.discard(self.serving_pid)
        _remove_scratch(self.scratch)


@dataclass(frozen=True)
class Runtime:
    """One runtime's start command, readiness rule, stop rule and version probe."""

    name: str
    port: int

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def start_command(
        self,
        artifact_dir: str,
        model_id: str,
        *,
        cache_state: str | None = None,
        kv_quant: str | None = None,
        mtp_depth: str | None = None,
        stream_experts: str | None = None,
    ) -> tuple[str, ...]:
        raise NotImplementedError

    def stop_command(self) -> tuple[str, ...]:
        return ()

    def version_command(self) -> tuple[str, ...]:
        return ()

    def cache_state_refusal(self, cache_state: str | None) -> str | None:
        """Why this runtime cannot be measured in *cache_state*, or ``None`` when it can.

        The default is ``None``: a runtime whose prefix/KV reuse is controlled by a
        start-command flag can be driven into either state by :meth:`start_command`, and the
        absent pin (``None``) asks for no state at all. The one override is Osaurus, whose
        cache state is host settings this harness must not edit -- it refuses a state the host
        is not in rather than measuring something else and labelling it.
        """
        return None

    def kv_quant_refusal(self, kv_quant: str | None) -> str | None:
        """Why this runtime cannot be measured in *kv_quant*, or ``None`` when it can.

        The same shape as :meth:`cache_state_refusal`, one cache down: the absent pin asks for
        no codec and reaches every runtime, and the values are :data:`KV_QUANTS` -- defined
        there, codec names rather than widths. The default is ``None`` for the shape
        :class:`Optiq` has, whose own start flags drive all three values; the four runtimes
        that cannot are the four that override this.
        """
        return None

    def mtp_depth_refusal(self, mtp_depth: str | None, artifact_dir: str) -> str | None:
        """Why this runtime cannot be measured at *mtp_depth*, or ``None`` when it can.

        The default refuses every depth, the opposite of :meth:`kv_quant_refusal`'s default and
        for the opposite reason: two of the five runtimes here carry a depth to pin
        (:data:`MTP_DEPTHS` -- vMLX's in-model heads and OptiQ's bundled one), so an override is
        what accepts one. ``off`` and the absent pin reach every runtime -- ``off`` is MTP not
        running, which is what a runtime with no MTP delivers.

        *artifact_dir* is required rather than optional: both answers are decided from the
        artifact (:func:`vmlx_mtp_refusal`, :func:`optiq_mtp_refusal`), so a caller that could
        omit it could omit the check. The three runtimes that refuse every depth ignore it -- and
        each of the five overrides this method, so the reason below is the shape's floor rather
        than the answer any cell on this host gets: the per-runtime evidence is in those
        overrides and in :data:`MTP_DEPTHS`.
        """
        if mtp_depth in (None, MTP_DEPTH_OFF):
            return None
        return (
            f"mtp_depth={mtp_depth!r} asks for a native-MTP draft depth, and {self.name} has no "
            "MTP depth to pin: it carries neither a start-command flag that sets one nor a "
            "settings field one could be written into. So this cell is N/A at a depth rather "
            "than measured at one it does not hold."
        )

    def stream_experts_refusal(self, stream_experts: str | None) -> str | None:
        """Why this runtime cannot be measured in *stream_experts*, or ``None`` when it can.

        The default refuses ``on``: a runtime with no expert-streaming surface has no flag that
        turns one on, and the two that do -- OptiQ and vMLX -- are the two that override this.
        ``off`` and the absent pin reach every runtime.
        """
        if stream_experts in (None, STREAM_EXPERTS_OFF):
            return None
        return (
            f"stream_experts={stream_experts!r} asks for SSD expert streaming, and {self.name} "
            "has no start-command surface that turns it on. So this cell is N/A in this state "
            "rather than measured in another one."
        )

    def stream_experts_missing(
        self, stream_experts: str | None, log_path: str | None
    ) -> str | None:
        """Why this runtime's own log does not show expert streaming, or ``None`` when it does.

        The second half of the ``on`` pin, asked after the start and before the first request:
        see :data:`STREAM_EXPERTS` and :func:`_banner_evidence`. The default needs no evidence --
        a runtime that refuses ``on`` never reaches an ``on`` cell.
        """
        return None

    def mtp_depth_missing(self, mtp_depth: str | None, log_path: str | None) -> str | None:
        """Why this runtime's own log does not show a draft head running, or ``None`` when it is.

        The second half of the depth pin, asked with the start's log and nothing else, and the
        default needs no evidence for the same reason: the three runtimes that refuse every
        depth never reach a depth cell. The two overrides are the two runtimes a depth reaches,
        and each reads the evidence its own engine emits -- ``measure._visit`` asks this once
        the visit's measured requests have answered, which is the earliest either can have any:
        see :meth:`Optiq.mtp_depth_missing` (an engine built on the first request) and
        :meth:`Vmlx.mtp_depth_missing` (a per-request account of the depth that ran).
        """
        return None

    def version(self) -> str:
        """Provenance for this runtime's build. Never raises; absence says why."""
        command = self.version_command()
        if not command:
            return "unknown: no version command"
        result = _run(command, VERSION_TIMEOUT_S)
        if result is None:
            return "unknown: version command could not be run"
        if result.returncode != 0:
            return f"unknown: exited with code {result.returncode}"
        return self.parse_version(result.stdout)

    def parse_version(self, output: str) -> str:
        lines = output.strip().splitlines()
        return lines[0].strip() if lines else "unknown: empty version output"

    def model_id_candidates(self, artifact_dir: str, model_id: str) -> tuple[str, ...]:
        raise NotImplementedError

    def api_key(self) -> str | None:
        return None

    def check_host_state(self) -> None:
        """Refuse to start when host state this runtime cannot pin has moved."""

    def build_command(
        self,
        artifact_dir: str,
        model_id: str,
        *,
        cache_state: str | None = None,
        kv_quant: str | None = None,
        mtp_depth: str | None = None,
        stream_experts: str | None = None,
    ) -> tuple[tuple[str, ...], str | None]:
        """The argv to spawn, plus any scratch tree a stop will have to remove."""
        return (
            self.start_command(
                artifact_dir,
                model_id,
                cache_state=cache_state,
                kv_quant=kv_quant,
                mtp_depth=mtp_depth,
                stream_experts=stream_experts,
            ),
            None,
        )

    def await_ready(
        self,
        *,
        pid: int,
        log_path: Path,
        artifact_dir: str,
        model_id: str,
        timeout_s: float = READY_TIMEOUT_S,
    ) -> str:
        """Hold until the runtime answers for its model, or raise.

        The log is read before the inventory on every pass because the inventory can lie
        -- mlx-lm lists the ``--model`` path whether or not it ever loaded, oMLX lists its
        whole catalog, Osaurus lists models it refuses -- while a traceback cannot. The
        log is then read *again* once the id is there: a load that fails writes its cause
        while the model list is being answered, so a handle returned on the listing alone
        is how oMLX published a cold load for a model it had already failed to load.
        """
        candidates = self.model_id_candidates(artifact_dir, model_id)
        deadline = _now() + timeout_s
        complaint = "no inventory yet"
        while True:
            _raise_on_log_error(self.name, log_path)
            if not _process_alive(pid) and _listener_pids(self.port) == ():
                raise RuntimeStartError(
                    f"{self.name} exited before it served {candidates[0]!r} "
                    f"(log: {log_path})"
                )
            try:
                inventory = _inventory(self.base_url, api_key=self.api_key())
            except urllib.error.HTTPError as exc:
                # A rejected credential will not start working in 900 seconds.
                if exc.code in (401, 403):
                    raise RuntimeStartError(
                        f"{self.name} answered the model list with HTTP {exc.code}; "
                        "it wants a credential this run does not have"
                    ) from exc
                complaint = f"HTTPError: {exc}"
            except _TRANSIENT as exc:
                complaint = f"{exc.__class__.__name__}: {exc}"
            else:
                resolved = resolve_model_id(candidates, inventory)
                if resolved is not None:
                    _raise_on_log_error(self.name, log_path)
                    return resolved
                complaint = f"inventory has {len(inventory)} models, none of them ours"
            if _now() >= deadline:
                raise RuntimeStartError(
                    f"{self.name} did not serve {candidates[0]!r} within "
                    f"{timeout_s:g}s ({complaint}; log: {log_path})"
                )
            _sleep(READY_POLL_S)

    def start(
        self,
        artifact_dir: str,
        model_id: str,
        *,
        cache_state: str | None = None,
        kv_quant: str | None = None,
        mtp_depth: str | None = None,
        stream_experts: str | None = None,
    ) -> Handle:
        """Spawn the runtime, hold until it can answer, and return its handle.

        *cache_state* is the run's cache pin, threaded into the start command; ``None`` is the
        pin not taken and produces the command this method produced before the pin existed.
        The refusal is not made here: :meth:`cache_state_refusal` is the measurement loop's to
        ask, before it starts anything, so a state this runtime cannot be driven into is
        recorded as ``N/A`` with its reason rather than raised as a start failure. *kv_quant*,
        *mtp_depth* and *stream_experts* are the same kind of pin and are threaded the same way
        -- ``None`` is no flag at all -- and their refusals are likewise the loop's to ask.
        *stream_experts*' second half is asked by the loop as well, after this returns: see
        :meth:`stream_experts_missing`.
        """
        if not _port_is_free(self.port):
            raise RuntimeStartError(
                f"port {self.port} is already held by a listener this run did not "
                f"start; refusing to start {self.name} over it"
            )
        resident_osaurus = _resident_osaurus_pids()
        if resident_osaurus:
            raise RuntimeStartError(
                "resident Osaurus app process(es) not started by this run: "
                + ", ".join(str(pid) for pid in resident_osaurus)
            )
        self.check_host_state()
        command, scratch = self.build_command(
            artifact_dir,
            model_id,
            cache_state=cache_state,
            kv_quant=kv_quant,
            mtp_depth=mtp_depth,
            stream_experts=stream_experts,
        )
        log_path = _log_path(self.name)
        started = _now()
        pid = None
        try:
            pid = _spawn(command, log_path)
            resolved = self.await_ready(
                pid=pid,
                log_path=log_path,
                artifact_dir=artifact_dir,
                model_id=model_id,
            )
            version = self.version()
        except BaseException as start_error:
            if pid is not None:
                try:
                    _shutdown(pid, self.port, self.stop_command())
                except RuntimeLifecycleError as cleanup_error:
                    _remove_scratch(scratch)
                    raise RuntimeStopError(
                        f"start failed: {start_error}; cleanup failed: {cleanup_error}"
                    ) from start_error
            _remove_scratch(scratch)
            raise
        _RUN_STARTED_PIDS.add(pid)
        serving_pid = _serving_pid(pid, self.port)
        _RUN_STARTED_PIDS.add(serving_pid)
        return Handle(
            pid=pid,
            port=self.port,
            base_url=self.base_url,
            model_id=resolved,
            version=version,
            cold_load_s=_now() - started,
            serving_pid=_serving_pid(pid, self.port),
            stop_command=self.stop_command(),
            scratch=scratch,
            api_key=self.api_key(),
            log_path=str(log_path),
        )


def prompt_cache_flags(cache_state: str | None) -> tuple[str, ...]:
    """The mlx-lm ``LRUPromptCache`` flags for one cache state: none, off, or a pinned on.

    mlx_lm 0.31.3 keeps an LRU prompt cache and reuses the nearest prefix across requests
    (``server.py:753``, ``fetch_nearest_cache``), and ``--prompt-cache-size`` is its only
    control: "Maximum number of distinct KV caches to hold in the prompt cache"
    (``server.py:1872``, default 10). At 0 the cache holds nothing -- every insert evicts the
    entry it just added (``models/cache.py:1696-1737``), so ``fetch_nearest_cache`` always
    answers ``None`` and every request prefills its prompt whole. That is ``off``.

    ``on`` pins the value instead of relying on it: 10 is what this mlx-lm defaults to, and a
    command that claimed to pin the cache on while naming no size would be adopting whatever a
    later version's default became.

    OptiQ runs this same server -- ``optiq serve`` passes flags it does not know through to
    ``mlx_lm.server``'s own argparse (``optiq/cli.py:2571`` collecting ``ctx.args``, ``:3030``
    handing them to ``mlx_lm.server``, with ``ignore_unknown_options`` set at ``:2332``) and
    bundles the same mlx-lm 0.31.3 -- so both runtimes read one definition of what the flag
    means instead of two that would drift.
    """
    if cache_state == CACHE_STATE_OFF:
        return ("--prompt-cache-size", "0")
    if cache_state == CACHE_STATE_ON:
        return ("--prompt-cache-size", "10")
    return ()


class MlxLm(Runtime):
    """The control: stock mlx-lm's own server."""

    def start_command(
        self,
        artifact_dir: str,
        model_id: str,
        *,
        cache_state: str | None = None,
        kv_quant: str | None = None,
        mtp_depth: str | None = None,
        stream_experts: str | None = None,
    ) -> tuple[str, ...]:
        # `off` and the absent pin are one command here for all three of the codec, depth and
        # streaming pins -- there is no flag to add for any of them, which is the whole of the
        # refusals below. No codec value, no depth and no `on` reaches this method: the loop
        # asks first and skips the cell.
        return (
            "python",
            "-m",
            "mlx_lm.server",
            "--model",
            artifact_dir,
            "--port",
            str(self.port),
            *prompt_cache_flags(cache_state),
        )

    def kv_quant_refusal(self, kv_quant: str | None) -> str | None:
        """Refuse a codec value: this server has no surface that selects one.

        All four places were read rather than just the command line, because a claim that a
        runtime *cannot* do something needs the source and not a missing flag: mlx_lm.server
        0.31.3 declares 23 options and none of them is a KV codec (``server.py:1751-1886``), it
        reads no environment variable anywhere in it, it has no settings file, and it honours no
        per-request field for one -- and the cache it builds is ``make_prompt_cache``'s
        (``server.py:971``, ``models/cache.py:15-42``), which takes no bit width at all. The
        codec and its flags exist in the same package and one layer away, wired into the client
        CLIs (``generate.py:192-208``, ``cache_prompt.py:61-76``), which is not the server a cell
        is measured through.

        ``off`` is accepted with no flag change, and there is nothing to pin: it is the only
        state this server can hold, so the absence of a flag *is* the state rather than a way of
        asking for it.
        """
        if kv_quant in (None, KV_QUANT_OFF):
            return None
        return (
            f"kv_quant={kv_quant!r} asks for a KV-cache codec, and mlx_lm.server 0.31.3 has no "
            "surface that selects one: no option in its argv (server.py:1751-1886), no "
            "environment variable anywhere in it, no settings file and no per-request field, "
            "and the cache it builds is make_prompt_cache's (server.py:971, "
            "models/cache.py:15-42), which takes no bit width. The codec exists one layer away "
            "on the client CLIs (generate.py:192-208, cache_prompt.py:61-76), which is not the "
            "server this cell would be measured through. So the cell is N/A in this codec "
            "rather than measured in the server's own full-precision cache under a header pin "
            "it does not hold."
        )

    def version_command(self) -> tuple[str, ...]:
        return ("python", "-m", "mlx_lm", "--version")

    def model_id_candidates(self, artifact_dir: str, model_id: str) -> tuple[str, ...]:
        # mlx_lm.server appends str(Path(--model).resolve()) to /v1/models, and also
        # every mlx-looking repo in the HF cache.
        absolute = str(Path(os.path.abspath(artifact_dir)))
        return _ordered((absolute, model_id), name_forms(artifact_dir))

    def mtp_depth_refusal(self, mtp_depth: str | None, artifact_dir: str) -> str | None:
        """Accept ``off`` -- the only state this server has. A negative claim, so the reason
        below is made from the source and not from the absence of a flag."""
        if mtp_depth in (None, MTP_DEPTH_OFF):
            return None
        return (
            f"mtp_depth={mtp_depth!r} asks for a native-MTP draft depth, and mlx_lm.server "
            "0.31.3 has no MTP at all: its 23 options include none for MTP, no MTP cache or "
            "draft head exists in it, and the string 'mtp' does not occur in server.py. A depth "
            "on this package is a patch layer over it -- vMLX's, and OptiQ's built on its own "
            "sidecar loader -- while this server's own model code drops the head's weights at "
            "load (models/qwen3_5.py:313 filters 'mtp.' out of the weight tree), so nothing "
            "here drafts from one. This cell is N/A at a depth rather than measured at one the "
            "decode never used."
        )

    def stream_experts_refusal(self, stream_experts: str | None) -> str | None:
        """Accept ``off`` -- there is no expert-streaming path here to be off. Same negative
        claim, same standard: the reason below is read from the source."""
        if stream_experts in (None, STREAM_EXPERTS_OFF):
            return None
        return (
            f"stream_experts={stream_experts!r} asks for SSD expert streaming, and "
            "mlx_lm.server 0.31.3 has no such path: 'expert' does not occur in server.py, its "
            "expert weights are ordinary resident tensors, and nothing in it loads them from "
            "disk per token. The streaming loader is OptiQ's, patched onto this server from the "
            "outside (optiq/serve.py:1623-1633). So this cell is N/A in this state rather than "
            "measured in one this runtime cannot hold."
        )


class Osaurus(Runtime):
    """The one runtime with no tuning flags to pin, and host settings instead."""

    def start_command(
        self,
        artifact_dir: str,
        model_id: str,
        *,
        cache_state: str | None = None,
        kv_quant: str | None = None,
        mtp_depth: str | None = None,
        stream_experts: str | None = None,
    ) -> tuple[str, ...]:
        # No model and no tuning on the command line: what a cell measures is decided by
        # ~/.osaurus/config, which check_host_state refuses to run away from. All four pins are
        # more of those settings, so none adds a flag here in any state -- and the states they
        # cannot be asked for are refused by the refusals below, never faked.
        return ("osaurus", "serve", "--port", str(self.port), "--yes")

    def cache_state_refusal(self, cache_state: str | None) -> str | None:
        """Refuse a requested cache state the host's own settings disagree with.

        Osaurus takes no flag for its prefix cache in either direction: the state lives in
        ``~/.osaurus/config/server-runtime.json``, under ``cache.prefix.enabled``, and the
        harness does not edit the host's files -- editing them is the sweep script's job, with
        a byte-exact backup and a restore, because it is a change to Jason's machine rather
        than to this run.

        So a requested state is honoured only when the host is already in it, and anything
        else is ``N/A`` with this reason. A restart is not a way to turn the cache on: a
        process that just started has an empty cache, which is ``off`` whatever the settings
        say, so restarting to reach ``on`` would label an off cell as an on one.
        """
        if cache_state is None:
            return None
        live = capture_osaurus_settings().get("server-runtime.json:cache.prefix.enabled")
        wanted = cache_state == CACHE_STATE_ON
        if live is wanted:
            return None
        state = {True: "true", False: "false"}.get(live, f"unreadable ({live})")
        return (
            f"cache_state={cache_state!r} needs Osaurus's prefix cache "
            f"{'on' if wanted else 'off'}, and the host has cache.prefix.enabled "
            f"{state} in ~/.osaurus/config/server-runtime.json. Osaurus exposes no "
            "start-command flag for the cache, and the harness does not edit the host's "
            "settings, so this cell is N/A in this state rather than measured in another "
            "one. A restart is not a way to turn the cache on: a fresh process has an empty "
            "cache whatever the settings say."
        )

    def stop_command(self) -> tuple[str, ...]:
        return ("osaurus", "stop")

    def kv_quant_refusal(self, kv_quant: str | None) -> str | None:
        """Accept ``off`` only while the host's live KV codec is its engine-selected default.

        No start-command flag exists in either direction, so a codec value cannot be driven and
        is refused outright. Two routes do exist in the binary and neither delivers what these
        values name: the affine one is request-side (``kvMode: .affine`` / the legacy
        ``kvBits``) and is **not supported under batched decode** -- it logs a line and runs
        float KV instead -- and the route that does work while batching, TurboQuant, is a
        codebook codec needing both bit widths explicitly, not the affine codec ``affine8`` and
        ``affine4`` name.

        ``off`` is the state ``cache.liveKVCodec = engine_selected`` delivers, so it is honoured
        only when the host is already in it, read the way :meth:`cache_state_refusal` reads
        ``cache.prefix.enabled``: the harness does not edit ``~/.osaurus/config``, and a cell
        measured in another codec under this pin would be a number published under a header
        field it does not hold.
        """
        if kv_quant is None:
            return None
        if kv_quant != KV_QUANT_OFF:
            return (
                f"kv_quant={kv_quant!r} cannot be driven on Osaurus: it exposes no "
                "start-command flag for the KV codec in either direction, its affine route "
                "(kvMode: .affine, and the legacy kvBits) is not supported under batched "
                "decode and falls back to float KV on this host, and the codec it can deliver "
                "while batching is TurboQuant -- a codebook codec that requires both bit "
                "widths explicitly, not the affine codec this value names. So this cell is N/A "
                "in this codec rather than measured in another one."
            )
        live = capture_osaurus_settings().get("server-runtime.json:cache.liveKVCodec")
        if live == "engine_selected":
            return None
        return (
            "kv_quant='off' needs Osaurus's live KV codec at its engine-selected default, and "
            f"the host has cache.liveKVCodec {live!r} in ~/.osaurus/config/server-runtime.json. "
            "Osaurus exposes no start-command flag for the codec, and the harness does not edit "
            "the host's settings, so this cell is N/A in this state rather than measured in "
            "another codec. A restart is not a way to move it: the codec is host state, not a "
            "property of a fresh process."
        )

    def version_command(self) -> tuple[str, ...]:
        return ("osaurus", "doctor", "--json", "--redact")

    def mtp_depth_refusal(self, mtp_depth: str | None, artifact_dir: str) -> str | None:
        """Refuse a depth; accept ``off`` only where the host forces MTP off.

        Osaurus is the one runtime here with an MTP mode to be in, so its ``off`` is not a
        statement of fact the way mlx-lm's is, and both reasons are below. ``mtp.mode`` is a
        tracked key, so it is read through the same capture the drift gate attests with; the
        depth itself is the host setting ``mtp.explicitDepth``, which the harness does not edit.
        """
        if mtp_depth is None:
            return None
        if mtp_depth != MTP_DEPTH_OFF:
            return (
                f"mtp_depth={mtp_depth!r} cannot be driven on Osaurus: it exposes no "
                "start-command flag for MTP in either direction, and the depth is the host "
                "setting mtp.explicitDepth, which 'must be 1, 2, or 3' "
                "(docs/runtimes/osaurus.md:344) in ~/.osaurus/config/server-runtime.json. The "
                "harness does not edit the host's settings, so this cell is N/A at a depth "
                "rather than measured at one it does not hold."
            )
        live = capture_osaurus_settings().get("server-runtime.json:mtp.mode")
        if live == "force_off":
            return None
        return (
            "mtp_depth='off' needs Osaurus's MTP forced off, and the host has mtp.mode "
            f"{live!r} in ~/.osaurus/config/server-runtime.json. Osaurus exposes no "
            "start-command flag for MTP, and its mtp.mode 'auto' runs a draft head on any "
            "bundle that carries one (docs/runtimes/osaurus.md:307, :900-901) -- so a restart "
            "would not make this cell MTP-free and the harness does not edit the host's "
            "settings. This cell is N/A in this state rather than measured in another one."
        )

    def stream_experts_refusal(self, stream_experts: str | None) -> str | None:
        """Refuse ``on``; accept ``off`` only where the host is not changing how many experts
        are resident.

        The one setting is ``concurrency.smeltMode`` (:data:`OSAURUS_SMELT_DISABLED`), which is
        not one of ``osaurus_settings.TRACKED_KEYS`` and is therefore read here rather than
        through the drift gate. Both reasons are below.
        """
        if stream_experts is None:
            return None
        if stream_experts == STREAM_EXPERTS_ON:
            return (
                "stream_experts='on' cannot be driven on Osaurus: its expert streaming is the "
                "host setting concurrency.smeltMode, whose enum is engineSelected | disabled | "
                "flashMoE | ssdStreaming (docs/runtimes/osaurus.md:298), and no start-command "
                "flag reaches it in either direction. The harness does not edit the host's "
                "settings, so this cell is N/A in this state rather than measured in another "
                "one. A restart is not a way to turn it on: a fresh process has no expert "
                "weights cached, so restarting would label a resident cell as a streaming one."
            )
        live = osaurus_smelt_mode()
        if live == OSAURUS_SMELT_DISABLED:
            return None
        return (
            "stream_experts='off' needs Osaurus's concurrency.smeltMode at 'disabled', and the "
            f"host has {live!r} in ~/.osaurus/config/server-runtime.json. 'flashMoE' and "
            "'ssdStreaming' are this pin's `on`, and 'engineSelected' leaves the choice to the "
            "engine, which for a large MoE may be streaming -- so a cell measured now could be "
            "streaming experts under a header pin that says it is not. This cell is N/A in this "
            "state rather than measured in another one."
        )

    def parse_version(self, output: str) -> str:
        try:
            payload = json.loads(output)
        except ValueError:
            return "unknown: unparseable `osaurus doctor` output"
        apps = payload.get("apps") if isinstance(payload, dict) else None
        bundles = [entry for entry in apps or [] if isinstance(entry, dict)]
        if not bundles:
            return "unknown: no app bundles in `osaurus doctor` output"
        # doctor reports every installed bundle precisely because duplicates happen.
        # Naming an arbitrary one would make the provenance confidently wrong, so prefer
        # the bundle that is actually serving and say when there was a choice.
        running = [entry for entry in bundles if entry.get("isRunning") is True]
        entry = running[0] if running else bundles[0]
        found = entry.get("version")
        if not isinstance(found, str) or not found.strip():
            return "unknown: no version in `osaurus doctor` bundle entry"
        return found if len(bundles) == 1 else f"{found} (one of {len(bundles)} bundles)"

    def model_id_candidates(self, artifact_dir: str, model_id: str) -> tuple[str, ...]:
        # Osaurus serves from its own library, so the name a user typed need not look
        # anything like the artifact's path. It names each model after the repo,
        # lowercased, and for an artifact in hub layout that name is the only candidate
        # that is not a commit hash -- so it leads, and every other candidate follows.
        return _ordered(
            (hub_repo_name(artifact_dir),), (model_id,), name_forms(artifact_dir)
        )

    def check_host_state(self) -> None:
        """Refuse to start when the host drifted from the recorded baseline.

        No recorded baseline means no gate: a fresh checkout should not be unable to run,
        and an operator who has not recorded a baseline has not yet claimed one.
        """
        try:
            baseline = load_baseline()
        except ValueError as error:
            raise RuntimeStartError(str(error)) from error
        if baseline is None:
            return
        drift = diff_against_baseline(capture_osaurus_settings(), baseline)
        if drift:
            raise RuntimeStartError(
                "Osaurus settings drifted from the recorded baseline; these decide what "
                "a cell measures and none of them is visible in the start command:\n"
                + describe_drift(drift)
            )


class Omlx(Runtime):
    """The runtime that has to be given a model directory it cannot see past."""

    def start_command(
        self,
        artifact_dir: str,
        model_id: str,
        *,
        cache_state: str | None = None,
        kv_quant: str | None = None,
        mtp_depth: str | None = None,
        stream_experts: str | None = None,
    ) -> tuple[str, ...]:
        # `off` here is structural and adds nothing: the per-run base path this runtime is
        # handed holds no model_settings.json, so turboquant_kv_enabled sits at its False
        # default whatever the pin says -- see kv_quant_refusal below, which is also where a
        # codec value is refused, because there is no flag in this command that could carry it.
        command = (
            "omlx",
            "serve",
            "--model-dir",
            OMLX_CATALOG_TOKEN,
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "--max-concurrent-requests",
            "1",
            "--memory-guard",
            "off",
        )
        # `--no-cache` is "Disable oMLX paged SSD cache" (omlx/cli.py:1140-1143) and its
        # absence leaves the cache on, because CacheSettings.enabled defaults True
        # (omlx/settings.py:331) and the SSD directory defaults to <base-path>/cache
        # (settings.py:387-399) -- which for a run is the per-run scratch this runtime is
        # given, removed with it at stop. So `off` is the flag that is already there, `on`
        # is dropping it, and the absent pin keeps today's command byte for byte.
        if cache_state != CACHE_STATE_ON:
            command += ("--no-cache",)
        return command

    def kv_quant_refusal(self, kv_quant: str | None) -> str | None:
        """Refuse a codec value: oMLX's codec is TurboQuant, and no flag selects it.

        ``off`` is accepted with no flag change, and it is stronger than a pin: it is a property
        of the scratch the harness already creates. oMLX reads its per-model settings from
        ``<base-path>/model_settings.json`` (``model_settings.py:433-435``, constructed with
        ``global_settings.base_path`` at ``server.py:1928-1929``), and the base path a run hands
        it is the empty per-run directory :func:`create_omlx_scratch` made -- so
        ``turboquant_kv_enabled`` is at its ``False`` default (``model_settings.py:235``) and the
        delivered state is the model's native cache.

        A codec value is refused for two reasons at once. What oMLX quantizes its KV cache with
        is TurboQuant, not the affine codec these values name: a codebook codec that derives two
        widths from the one value it is given (``key_bits = floor``, ``value_bits = ceil``,
        ``turboquant_kv.py:70-92``) and whose validator only accepts its own bit widths
        (``mlx_vlm/turboquant.py:3498-3508``). And there is no start-command surface for it at
        all -- it is a per-model settings field, HTTP-settable and otherwise read from the
        scratch's file -- so driving it here would mean writing that file or calling the admin
        route, which is a second variable beside this pin rather than the pin itself.
        """
        if kv_quant in (None, KV_QUANT_OFF):
            return None
        return (
            f"kv_quant={kv_quant!r} asks for the affine codec, and oMLX's KV codec is not "
            "affine: it is TurboQuant, a codebook codec that splits one value into "
            "key_bits=floor/value_bits=ceil (turboquant_kv.py:70-92) and accepts only its own "
            "bit widths (mlx_vlm/turboquant.py:3498-3508). It is also not drivable from a start "
            "command: turboquant_kv_enabled is a per-model settings field read from "
            "<base-path>/model_settings.json (model_settings.py:235, :433-435) and settable over "
            "HTTP, and no flag in omlx/cli.py mentions it -- so this cell is N/A in this codec "
            "rather than measured in a neighbouring one. `off` needs no flag: the per-run base "
            "path holds no model_settings.json, which leaves turboquant_kv_enabled False."
        )

    def version_command(self) -> tuple[str, ...]:
        return ("omlx", "--version")

    def mtp_depth_refusal(self, mtp_depth: str | None, artifact_dir: str) -> str | None:
        """Refuse a depth; accept ``off`` with no flag change.

        ``off`` is structural rather than a pin, like the codec above: the per-run base path
        holds no ``model_settings.json``, so ``mtp_enabled`` sits at its default. The reason
        below is the whole of the depth side.
        """
        if mtp_depth in (None, MTP_DEPTH_OFF):
            return None
        return (
            f"mtp_depth={mtp_depth!r} cannot be driven on oMLX: MTP is the per-model settings "
            "field mtp_num_draft_tokens (model_settings.py:308) with no flag in omlx/cli.py at "
            "all, and the field is not even a fixed depth -- an adaptive controller picks 1..max "
            "per sequence from rolling acceptance and latency estimates "
            "(model_settings.py:304-307). Reaching it would mean writing the scratch's "
            "model_settings.json or calling the admin route, which is a second variable beside "
            "this pin. So this cell is N/A at a depth rather than measured at one the decode "
            "may never have used. `off` needs no flag: the per-run base path holds no "
            "model_settings.json, which leaves mtp_enabled False."
        )

    def stream_experts_refusal(self, stream_experts: str | None) -> str | None:
        """Refuse ``on`` -- oMLX has no expert-streaming surface, and the reason below names
        the mechanism that is easy to mistake for one."""
        if stream_experts in (None, STREAM_EXPERTS_OFF):
            return None
        return (
            f"stream_experts={stream_experts!r} asks for SSD expert streaming, and oMLX has no "
            "such surface: no option in omlx/cli.py names experts, no module in the package "
            "mentions expert streaming, and expert weights are resident tensors to its engine. "
            "The mechanism it does have that resembles this one is burst decode -- "
            "server.burst_decode_mode -> OMLX_DECODE_BURST_* (settings.py:148-162, exported by "
            "cli.py:179-182, read at engine construction engine_core.py:176-188) -- and that "
            "sets how many decode steps are coalesced before a delta is emitted, not where the "
            "expert weights live (docs/runtimes/omlx.md:798-841). It is a different mechanism, "
            "so this cell is N/A in this state rather than measured under a pin it does not "
            "hold."
        )

    def api_key(self) -> str | None:
        return OMLX_API_KEY

    def model_id_candidates(self, artifact_dir: str, model_id: str) -> tuple[str, ...]:
        # oMLX serves the catalog entry names, and the entry is named here.
        return _ordered(
            (omlx_link_name(artifact_dir, model_id),), name_forms(artifact_dir), (model_id,)
        )

    def build_command(
        self,
        artifact_dir: str,
        model_id: str,
        *,
        cache_state: str | None = None,
        kv_quant: str | None = None,
        mtp_depth: str | None = None,
        stream_experts: str | None = None,
    ) -> tuple[tuple[str, ...], str | None]:
        scratch = create_omlx_scratch(artifact_dir, model_id)
        command = tuple(
            str(scratch.catalog) if part == OMLX_CATALOG_TOKEN else part
            for part in self.start_command(
                artifact_dir,
                model_id,
                cache_state=cache_state,
                kv_quant=kv_quant,
                mtp_depth=mtp_depth,
                stream_experts=stream_experts,
            )
        )
        return command + (
            "--base-path",
            str(scratch.base),
            "--api-key",
            OMLX_API_KEY,
        ), str(scratch.root)


class Optiq(Runtime):
    """The fork whose expert-streaming heuristic silently costs 5x on large artifacts."""

    def start_command(
        self,
        artifact_dir: str,
        model_id: str,
        *,
        cache_state: str | None = None,
        kv_quant: str | None = None,
        mtp_depth: str | None = None,
        stream_experts: str | None = None,
    ) -> tuple[str, ...]:
        # The KV-codec pin, in the flags OptiQ consumes itself -- these are its own options and
        # are not forwarded to the mlx_lm.server underneath it. `off` is the absence of both
        # flags: there is no `--kv-bits none` and no `--no-kv-quant`, so `off` and an absent pin
        # build the same command, and that state is the production default (`_effective_kv_bits`
        # returns None for neither flag, optiq/cli.py:2332-2347). The group size is pinned
        # explicitly rather than inherited, because it is a second variable and 64 is only
        # today's default (optiq/cli.py:2504).
        kv = ()
        if kv_quant == KV_QUANT_AFFINE8:
            kv = ("--kv-bits", "8", "--kv-group-size", "64")
        elif kv_quant == KV_QUANT_AFFINE4:
            kv = ("--kv-bits", "4", "--kv-group-size", "64")
        # Both states are explicit rather than an absence, because OptiQ's own default is
        # `auto` -- never leave it there (`STREAM_EXPERTS`). `on` is the flag that asks for
        # streaming, and the flag is not the evidence: see `stream_experts_missing`.
        stream = ("--no-stream-experts",)
        if stream_experts == STREAM_EXPERTS_ON:
            stream = ("--stream-experts",)
        # The depth pin. `--mtp` is `is_flag=True, default=False` and `--mtp-depth` defaults to
        # 2 (cli.py:2554-2563), so `off` and the absent pin pass neither flag -- OptiQ's own off
        # *is* the absence of the pair -- and a depth passes both. Nothing pins a policy beside
        # it because there is none to pin: the cycle's K is the depth for the whole request
        # (engine.py:920). Whether a head is really driving the decode is not this method's
        # question: see `optiq_mtp_refusal` and `mtp_depth_missing`.
        mtp = ("--mtp", "--mtp-depth", mtp_depth) if mtp_depth in MTP_DEPTHS[1:] else ()
        # NOT moved by this pin: enabling KV quantization also installs OptiQ's fused
        # streaming-KV path unless `--no-fused-kv` is passed (optiq/cli.py:2729-2739) -- one
        # layer converted at a time, plus a FlashAttention-2 SDPA the runtime's own header
        # documents as the reason a quantized cell does not OOM. That is the runtime as
        # shipped, and an affine cell is therefore not stock-mlx-lm-with-a-quantized-cache.
        return (
            "optiq",
            "serve",
            "--model",
            artifact_dir,
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "--no-anthropic",
            "--no-responses",
            "--no-auth",
            # An integer cap installs a RotatingKVCache that silently rotates a longer prompt
            # instead of refusing it. Qwen3.5 and LFM2 bring their own make_cache and ignore
            # it, so 8192 never capped anything measured -- but a start command claiming a cap
            # that is not there contradicts a 32k figure beside it. `off` is what is true.
            "--max-context",
            "off",
            "--max-concurrent",
            "1",
            "--idle-timeout",
            "0",
            "--context-scale",
            "1.0",
            *mtp,
            *stream,
            "--temp",
            "0",
            "--top-p",
            "1",
            "--top-k",
            "0",
            "--min-p",
            "0",
            # The cache pin, under the same flag stock mlx-lm takes: optiq serve forwards
            # what it does not know to the mlx_lm.server underneath it.
            *prompt_cache_flags(cache_state),
            *kv,
        )

    def version_command(self) -> tuple[str, ...]:
        return ("optiq", "--version")

    def mtp_depth_refusal(self, mtp_depth: str | None, artifact_dir: str) -> str | None:
        """The second runtime a depth can be driven into, decided from the artifact.

        ``off`` and the absent pin pass no flag at all, and that is this runtime's own off
        rather than a stand-in for one: ``--mtp`` is an opt-in flag defaulting to False
        (``cli.py:2554-2558``), so a command without the pair is a command that never drafts.
        A depth is driven by ``--mtp --mtp-depth N`` (:meth:`start_command`) and then decided
        from the files, through :func:`optiq_mtp_refusal` -- the same artifact-shaped answer
        vMLX's depths get, and the same reason: a flag in the command is not a head on disk.
        """
        if mtp_depth in (None, MTP_DEPTH_OFF):
            return None
        return optiq_mtp_refusal(artifact_dir)

    def mtp_depth_missing(self, mtp_depth: str | None, log_path: str | None) -> str | None:
        """A depth is only MTP if the engine says it built one, and OptiQ says so late.

        ``--mtp --mtp-depth N`` is accepted and echoed at startup (``cli.py:3057-3060``), but the
        engine that line names is created on the **first request** -- ``_get_engine`` runs from
        the patched ``stream_generate`` (``serve.py:443-471``) -- so the line that settles it,
        ``[optiq.serve] MTP engine ready (depth=N).`` (``serve.py:465``), cannot exist before one
        has been made. That is the one place this check departs from
        :meth:`Runtime.stream_experts_missing`'s timing, and it is why ``measure._visit`` asks it
        after the visit's measured requests rather than before the first request.

        The required line carries the pinned depth, because ``serve.py:465`` interpolates it:
        a cell that asked for 3 and got an engine built at 2 is a FAIL here rather than a number
        published under a depth the decode did not hold. The fallback lines are the engine's own
        account of attaching without a head (``engine.py:297-304``); the error that follows is
        answered to the client as HTTP 404 and never logged (``serve.py:459-464``,
        ``mlx_lm/server.py:1424-1427``), so the warning is what the log holds.
        """
        if mtp_depth not in MTP_DEPTHS[1:]:
            return None
        return _banner_evidence(
            self.name,
            log_path,
            claim=f"mtp_depth={mtp_depth!r}",
            required=(f"[optiq.serve] MTP engine ready (depth={mtp_depth}).",),
            fallback=("MTP head not attached", "MTP injection failed"),
            banner_why=(
                "the runtime's own banner is the evidence that a draft head is driving the "
                "decode rather than an engine that attached without one"
            ),
            fallback_why="the engine attached without a draft head",
        )

    def stream_experts_refusal(self, stream_experts: str | None) -> str | None:
        """Accept both values: OptiQ is the runtime this pin was written for.

        ``off`` is its own flag, needed because the flag's default is ``auto``
        (:data:`STREAM_EXPERTS`); ``on``'s truth is settled from the log rather than from the
        flag, in :meth:`stream_experts_missing`.
        """
        return None

    def stream_experts_missing(
        self, stream_experts: str | None, log_path: str | None
    ) -> str | None:
        """``on`` is only streaming if the log says so, twice -- the mode banner alone is
        printed before the model is even inspected (``optiq/cli.py:3095-3101``).

        OptiQ accepts ``--stream-experts`` on a model it cannot stream and takes the resident
        path without failing anything (``optiq/serve.py:1641-1643``, ``:1688-1692``), which is
        why the flag is not evidence. What the two required lines mean, and every fallback line
        quoted when they are absent, is the tuple below; :func:`_stream_evidence` reads them.
        """
        if stream_experts != STREAM_EXPERTS_ON:
            return None
        return _stream_evidence(
            self.name,
            log_path,
            required=(
                "[optiq.serve] SSD expert streaming: on",
                "[optiq.serve] SSD expert streaming: pre-loaded",
            ),
            fallback=(
                "expert streaming failed",
                "streaming pre-load failed",
                "SSD expert streaming: auto",
            ),
        )

    def parse_version(self, output: str) -> str:
        """`optiq --version` answers `mlx-optiq, version 0.5.6`, not a bare `0.5.6`.

        The recorded string is what the grid's join guard compares across run directories to
        decide whether one runtime appeared at two versions, and it compares it exactly. The
        prose is uniform today, so the guard does not misfire -- but it is the runtime's
        phrasing rather than its version, and a release that reworded its own `--version`
        output would read as a version change and refuse a legal join. The version is the
        part that means something, so the version is what gets recorded.

        Anything that does not look like `..., version X` is passed through whole rather than
        guessed at: an unrecognised shape is better recorded verbatim than parsed into
        something that looks like a version and is not.
        """
        first = super().parse_version(output)
        _, separator, version = first.rpartition(", version ")
        return version.strip() if separator and version.strip() else first

    def model_id_candidates(self, artifact_dir: str, model_id: str) -> tuple[str, ...]:
        # OptiQ lists the absolute --model path. The :no-think variant is the one whose
        # streams put visible text in delta.content instead of delta.reasoning.
        forms = name_forms(artifact_dir)
        return _ordered(
            (f"{str(Path(os.path.abspath(artifact_dir)))}:no-think", model_id),
            tuple(f"{form}:no-think" for form in forms),
            tuple(f"optiq/{form}" for form in forms),
            forms,
        )


def vmlx_served_name(artifact_dir: str) -> str:
    """The name vMLX will expose these weights under.

    Ported from its ``_normalize_model_name`` (docs/runtimes/vmlx.md §9.5): an HF cache path
    collapses to ``org/repo``, any other path to its last two components, and a name with no
    separator is left alone. ``name_forms`` cannot spell the first of those, so the start
    command pins the served name to this rather than leaving readiness to a guess.
    """
    if os.path.sep not in artifact_dir and not artifact_dir.startswith("/"):
        return artifact_dir
    parts = artifact_dir.rstrip("/").split("/")
    for part in parts:
        found = _hub_repo_parts(part)
        if found is not None:
            return f"{found[0]}/{found[1]}"
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return parts[-1]


class Vmlx(Runtime):
    """The only runtime here that loads JANG, and the one whose real settings are 438
    environment variables no start command mentions.

    Deliberately absent from the command line: ``--api-key`` (unset means no authentication
    at all), ``--enable-disk-cache`` and ``--use-paged-cache`` (both off by default, both
    would make request 1 differ from requests 2+), and ``--kv-cache-quantization`` -- which is
    passed now for the one value that can be honoured, ``off``, and left off for the absent
    pin. That flag is not neutral either way: passing it at all disables loader-level
    TurboQuant (``cli.py:1509-1517``), so the pin's ``off`` is a substitution rather than a
    default spelled out -- but in 1.6.59 omitting it disables loader-level TurboQuant too
    (``cli.py:60-91``), so the two differ only in ``kv_cache_quantization_explicit`` and pinning
    ``none`` is strictly the more explicit of two identical states. A codec value is refused
    rather than passed: see :meth:`kv_quant_refusal`.

    No stop subcommand exists, so the base class's empty ``stop_command`` stands and SIGTERM
    to the spawned pid is the stop -- shutdown can take up to ~10s to flush disk caches, which
    :func:`_shutdown` already waits out. With no ``--api-key`` its ``verify_api_key`` returns
    True for everyone, so the base class's ``api_key`` of ``None`` stands and measured requests
    carry no credential, the opposite of oMLX, where an unauthenticated request 401s.
    """

    def start_command(
        self,
        artifact_dir: str,
        model_id: str,
        *,
        cache_state: str | None = None,
        kv_quant: str | None = None,
        mtp_depth: str | None = None,
        stream_experts: str | None = None,
    ) -> tuple[str, ...]:
        # The KV-codec pin's one explicit off in this set, and the only value of the three this
        # runtime can be driven into: `--kv-cache-quantization none` is a real accepted value
        # (cli.py:3864-3882) and the production default, so passing it takes the last way the
        # storage codec could move underneath a run. It is passed for `off` alone -- an absent
        # pin omits it, which is what keeps every recorded command byte-identical -- and a
        # codec value never reaches here: kv_quant_refusal refuses it first.
        kv = ("--kv-cache-quantization", "none") if kv_quant == KV_QUANT_OFF else ()
        # The prefix cache is `--enable-prefix-cache`, default True (cli.py:3659) against
        # `--disable-prefix-cache` for the explicit off (cli.py:3667), and `on` pins the
        # enable rather than leaving the default to speak for itself.
        #
        # The block-disk tier stays off in BOTH states, and that is the single-variable rule
        # rather than tidiness: when neither block-disk flag is passed the engine turns the
        # SSD L2 on by itself the moment continuous batching and prefix caching are both
        # active (`_apply_paged_block_disk_default`, cli.py:661-701), writing to
        # ~/.cache/vmlx-engine/block-cache/<model_hash> -- state that survives restarts, is
        # not this run's, and would make an `on` cell's prefix possibly another run's. One
        # flag moves between the two states, and it is the prefix cache.
        prefix = ("--enable-prefix-cache",)
        if cache_state != CACHE_STATE_ON:
            prefix = ("--disable-prefix-cache",)
        # JIT is off unless a run asks for it. Left alone the artifact decides — JIT turns
        # itself on for a JANG affine bundle — so the default pins it off and every command
        # recorded before this toggle existed is byte-identical. The one run that measures JIT
        # as its variable (the vMLX JIT A/B) sets OHYESMLX_VMLX_ENABLE_JIT=1 to move this flag
        # and nothing else.
        jit = ("--no-jit",)
        if os.environ.get("OHYESMLX_VMLX_ENABLE_JIT") == "1":
            jit = ("--enable-jit",)
        # The absent pin and `off` pass the kill switch, which is what keeps their command
        # byte-identical to the recorded ones; the depths and their fixed policy are
        # `MTP_DEPTHS`'. The policy is not the whole of a fixed depth on this release: two
        # controllers it does not turn off still move depth, and `VMLX_MTP_FIXED_ENV` is the
        # pair of variables that disables them -- carried as an `env` prefix so the recorded
        # command says the depth was pinned rather than leaving it to the ambient environment.
        # Whether a depth is honest on this artifact is not this method's question: see
        # `vmlx_mtp_refusal`.
        mtp = ("--disable-native-mtp",)
        mtp_env: tuple[str, ...] = ()
        if mtp_depth in MTP_DEPTHS[1:]:
            mtp = (
                "--native-mtp-depth",
                mtp_depth,
                "--native-mtp-depth-policy",
                "fixed",
            )
            mtp_env = ("env", *VMLX_MTP_FIXED_ENV)
        # Off by default and opt-in (`STREAM_EXPERTS`), so the absent pin and `off` pass nothing
        # while `on` is the flag -- and the flag is not the evidence: see
        # `stream_experts_missing`.
        flash = ("--flash-moe",) if stream_experts == STREAM_EXPERTS_ON else ()
        return (
            *mtp_env,
            "vmlx",
            "serve",
            # Positional and first, which is the one interface difference from every other
            # runtime here: there is no --model flag to pass.
            artifact_dir,
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            # /v1/models answers to this, so readiness resolves a name this run chose
            # instead of one derived from the path. It leads model_id_candidates.
            "--served-model-name",
            vmlx_served_name(artifact_dir),
            # 8 is the default, and it batches tokens before the harness can count deltas.
            # Pinning the interval only means anything with batching on: without it the
            # runtime forces the interval to 1 and the command would say otherwise.
            "--stream-interval",
            "1",
            "--continuous-batching",
            "--max-num-seqs",
            "1",
            *jit,
            *mtp,
            *prefix,
            # A cache hit is invisible to Observation, which carries no cached_tokens, so it
            # would publish as prefill throughput. The block disk cache also survives restarts
            # and is trimmed synchronously inside cold load, on a 22 GB cache that is not ours.
            "--disable-block-disk-cache",
            *flash,
            *kv,
        )

    def kv_quant_refusal(self, kv_quant: str | None) -> str | None:
        """Refuse a codec value: vMLX's codec is storage-only, and inert in this command.

        `--kv-cache-quantization q4|q8` quantizes the prefix cache's **stored copy** and nothing
        else -- "Quantization is applied at the storage/retrieval boundary of the prefix cache,
        NOT at model.make_cache() level. ... During generation: full-precision KVCache (no
        quality loss)" (``scheduler.py:2444-2458``) -- so a cell pinned to it would decode at
        full precision and the pin would name a codec the generation path never used. It also
        does not fire at all unless the prefix cache is on: the scheduler skips the codec and
        logs its own no-op warning instead (``scheduler.py:1393-1404``, and the same shape at
        ``mllm_scheduler.py:1165-1177``), while this harness's start command passes
        ``--disable-prefix-cache`` unless the run asked for ``cache_state="on"``. Reaching the
        codec would mean enabling the prefix cache and changing the codec in one run, which is
        two variables and not a pin.

        ``off`` is a real flag here and :meth:`start_command` passes it; the absent pin passes
        nothing.
        """
        if kv_quant in (None, KV_QUANT_OFF):
            return None
        return (
            f"kv_quant={kv_quant!r} cannot be measured on vMLX: its codec quantizes only the "
            "prefix cache's stored copy and generation stays full precision -- 'Quantization "
            "is applied at the storage/retrieval boundary of the prefix cache, NOT at "
            "model.make_cache() level ... During generation: full-precision KVCache' "
            "(scheduler.py:2444-2458) -- and it is a no-op under this command, which passes "
            "--disable-prefix-cache unless the run pinned cache_state='on' (scheduler.py:1393"
            "-1404 skips the codec and logs the no-op). Reaching it would enable the prefix "
            "cache and move the codec in the same run, which is two variables rather than one. "
            "So this cell is N/A in this codec; `off` is passed as "
            "--kv-cache-quantization none, which is this runtime's real explicit off."
        )

    def version_command(self) -> tuple[str, ...]:
        # `vmlx --version` is not a flag: the parser rejects it and exits 2. Read the engine's
        # own constant out of the shipped source instead of importing it — the import pulls in
        # the whole engine and measured 9.2s, which start() times as part of cold load, and
        # cold load is a published metric that must not carry harness overhead.
        return ("sed", "-n", VMLX_VERSION_SED, VMLX_ENGINE_INIT)

    def mtp_depth_refusal(self, mtp_depth: str | None, artifact_dir: str) -> str | None:
        """The one runtime a depth can be driven into, and the one whose refusal is about the
        *artifact* rather than a missing flag: a depth is decided by :func:`vmlx_mtp_refusal`,
        which names the check that failed. ``off`` and the absent pin pass the kill switch and
        need no artifact check.
        """
        if mtp_depth in (None, MTP_DEPTH_OFF):
            return None
        return vmlx_mtp_refusal(artifact_dir)

    def mtp_depth_missing(self, mtp_depth: str | None, log_path: str | None) -> str | None:
        """Whether the requests really drafted at the pinned depth, read off the runtime's log.

        The depth pin's second half, and on this runtime it carries more of the pin than OptiQ's
        does: :data:`VMLX_MTP_FIXED_ENV` is what makes ``fixed`` fixed, and this is the reading
        that says the visit ran that way. Both mechanisms the env pin disables leave their own
        line, and either one is a FAIL here:

        * ``finish=fallback_to_ar`` -- the request ended in plain autoregressive decode, the
          AR-safety valve's handoff (``mllm_batch_generator.py:7029-7047``, ``:18387-18402``).
          The neighbouring ``finish=ar_calibration`` is deliberately not read: it is a winning
          phase's bounded re-measure, not a demotion (``:18383-18391``).
        * ``start rung D<k>`` with ``k`` below the pin -- the previous request's demotion was
          inherited as this request's start rung (``:17275-17286``), the sticky behaviour
          ``VMLX_NATIVE_MTP_AR_REENTRY`` gates.

        The positive half is the same reading: the log has to show at least one
        ``accept_by_depth`` line with a non-zero denominator at ``d<N>`` (``:5821-5838``), which
        is the head actually drafting the Nth token in some request of the visit. A depth is not
        the depth just because the flag said so -- measured 2026-09-25, five of the 104
        ``accept_by_depth`` rows in ``results/logs/vmlx-20260925T063452-16321.log`` show any
        ``d3`` draft at all under the policy alone.

        Depth 1 has no rung to fall below and no fallback below it, so only the positive half
        applies to it. ``off`` and the absent pin claim no depth a log could contradict and
        answer before the log is opened.

        The evidence is per request, so it is a property of the whole log and it is read after
        the visit's measured requests -- see :func:`_read_log_all` for the window and
        ``measure._visit`` for the point it is asked at. The markers are the runtime's own
        words, taken from its source and from ``results/logs/vmlx-20260925T062816-11233.log``
        and ``-20260925T063452-16321.log``: of their 49 and 45 depth-3 requests, 47 and 40
        carry a ``start rung D1`` line, 15 and 15 carry ``finish=fallback_to_ar``, and 0 and 5
        ``accept_by_depth`` rows have a non-zero denominator at ``d3``.
        """
        if mtp_depth not in MTP_DEPTHS[1:]:
            return None
        claim = f"mtp_depth={mtp_depth!r}"
        if log_path is None:
            return (
                f"{claim} cannot be verified on {self.name}: this run was started without a log "
                "path, and the runtime's own log is the only evidence that the requests drafted "
                "at the pinned depth rather than being demoted underneath it. This cell is FAIL "
                "rather than a number published under a pin nothing checked."
            )
        text = _read_log_all(Path(log_path))
        lines = text.splitlines()

        if mtp_depth in MTP_DEPTHS[2:]:
            quoted = next(
                (line.strip() for line in lines if "finish=fallback_to_ar" in line), None
            )
            if quoted is not None:
                return (
                    f"{claim} was not delivered: {self.name}'s own log never printed a cell "
                    "whose requests all finished on the draft head, and it says "
                    f"{quoted!r} instead. The flag was accepted and the AR-safety valve fell "
                    "back to plain autoregressive decode -- the mechanism "
                    "VMLX_NATIVE_MTP_AR_SAFETY=0 disables -- so this cell is FAIL rather than a "
                    f"number published under a pin it does not hold (log: {log_path})."
                )
            quoted = next(
                (
                    line.strip()
                    for line in lines
                    if (rung := _VMLX_START_RUNG.search(line)) is not None
                    and int(rung.group(1)) < int(mtp_depth)
                ),
                None,
            )
            if quoted is not None:
                return (
                    f"{claim} was not delivered: {self.name}'s own log never printed a cell "
                    f"whose requests all started at D{mtp_depth}, and it says {quoted!r} "
                    "instead. The flag was accepted and the previous request's demotion was "
                    "inherited as the start rung -- the mechanism VMLX_NATIVE_MTP_AR_REENTRY=0 "
                    "disables -- so this cell is FAIL rather than a number published under a "
                    f"pin it does not hold (log: {log_path})."
                )

        drafts = (
            int(drafted)
            for bracket in _VMLX_ACCEPT_BY_DEPTH.findall(text)
            for _accepted, drafted in re.findall(rf"\bd{mtp_depth}=(\d+)/(\d+)", bracket)
        )
        if not any(drafts):
            return (
                f"{claim} was not delivered: {self.name}'s own log never printed an "
                f"accept_by_depth line with a non-zero denominator at d{mtp_depth}, and it "
                "says nothing about why. The flag was accepted, so this cell is FAIL rather "
                f"than a number published under a pin nothing confirmed (log: {log_path})."
            )
        return None

    def stream_experts_refusal(self, stream_experts: str | None) -> str | None:
        """Accept both values: ``--flash-moe`` is a real flag and its default is off
        (:data:`STREAM_EXPERTS`).

        The two side effects are the runtime's own and stay out of the pin's way: the flag is
        mutually exclusive with ``--smelt`` and ``--distributed`` (cli.py:2565-2573), neither of
        which this command passes, and the engine skips ``mx.compile`` while it is active
        (server.py:6565-6568) -- the command passes ``--no-jit`` unconditionally, so both states
        are un-JITed and this flag is the only thing that moves. What it cannot be trusted to be
        is *on*: see :meth:`stream_experts_missing`.
        """
        return None

    def stream_experts_missing(
        self, stream_experts: str | None, log_path: str | None
    ) -> str | None:
        """``on`` is only streaming if the log shows the layers were patched.

        vMLX accepts ``--flash-moe`` on a model it cannot stream and carries on -- every such
        outcome logs one line and loads resident, and those lines are the ``fallback`` tuple
        below. The line printed only when layers were patched is among the runtime's own
        (``server.py:8996-9002``), and it is in the log before the runtime can answer: the
        patching is applied at the readiness barrier, ahead of the yield that opens the port
        (``server.py:6176-6177``, :6199).
        """
        if stream_experts != STREAM_EXPERTS_ON:
            return None
        return _stream_evidence(
            self.name,
            log_path,
            required=("Flash MoE enabled:",),
            fallback=(
                "Flash MoE: model has no MoE layers, skipping",
                "Flash MoE: no MoE layers found to patch",
                "--flash-moe is not supported on JANGTQ",
                "Flash MoE: could not find raw model in engine",
                "Flash MoE: refusing to patch",
                "Flash MoE setup failed",
            ),
        )

    def model_id_candidates(self, artifact_dir: str, model_id: str) -> tuple[str, ...]:
        # vMLX strips a path to its last two components, or to org/repo for an HF cache path.
        return _ordered((vmlx_served_name(artifact_dir), model_id), name_forms(artifact_dir))


RUNTIMES: dict[str, Runtime] = {
    "mlxlm": MlxLm(name="mlxlm", port=8081),
    "osaurus": Osaurus(name="osaurus", port=1337),
    "omlx": Omlx(name="omlx", port=8100),
    "optiq": Optiq(name="optiq", port=8080),
    "vmlx": Vmlx(name="vmlx", port=8000),
}
