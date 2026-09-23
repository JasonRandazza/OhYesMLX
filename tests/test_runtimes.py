"""Checks for ohyesmlx.runtimes.

No model server is started here. Every runtime is exercised through fakes for the seams
this module reaches outside itself with -- spawn, inventory, signals, clock -- plus checks
that run the real binaries those rules rest on: `/usr/sbin/lsof` against a real listening
socket, because the port-free rule is the one thing a fake cannot be trusted to prove, and
`sed` against a module shaped like the one vMLX ships.

The load-failure text below is captured verbatim from mlx-lm 0.31.3 on this host; see
docs/research/2026-09-14-oq-portability-spike.md. The oMLX text is captured the same way
from this repo's own results/logs, which is where a probe's runtime output lands.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from ohyesmlx import runtimes
from ohyesmlx import osaurus_settings
from ohyesmlx.runtimes import (
    OMLX_API_KEY,
    READY_POLL_S,
    READY_TIMEOUT_S,
    RUNTIMES,
    Handle,
    RuntimeStartError,
    RuntimeStopError,
    await_port_free,
    create_omlx_scratch,
    log_load_error,
    name_forms,
    remove_omlx_catalog,
    resolve_model_id,
)

# Verbatim from the spike: the load thread raised, and the server went on to bind its port
# and log `Starting httpd` anyway.
MLX_LM_DEAD_LOAD_LOG = """\
Starting httpd at 127.0.0.1 on port 8081...
Exception in thread Thread-1 (_generate):
Traceback (most recent call last):
  File "/private/tmp/mlxspike/lib/python3.14/site-packages/mlx_lm/utils.py", line 188, in _get_classes
    arch = importlib.import_module(f"mlx_lm.models.{model_type}")
ModuleNotFoundError: No module named 'mlx_lm.models.gemma4_unified'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/private/tmp/mlxspike/lib/python3.14/site-packages/mlx_lm/server.py", line 695, in _generate
    self.model_provider.load_default()
  File "/private/tmp/mlxspike/lib/python3.14/site-packages/mlx_lm/utils.py", line 334, in load_model
    model_class, model_args_class = get_model_classes(config=config)
ValueError: Model type gemma4_unified not supported.
"""

MLX_LM_HEALTHY_LOG = """\
Fetching 12 files: 100%|##########| 12/12 [00:19<00:00,  1.62s/it]
Starting httpd at 127.0.0.1 on port 8081...
"""

# oMLX 0.6.4, from results/logs/omlx-20260915T135626-71559.log. It serves /v1/models from
# a scan of its catalog and only then starts loading, so a start logs the load it began and
# then either the load it finished -- or the failure, which is what this JANG artifact got
# while a 2.15 s cold load was being recorded for it.
OMLX_HASH = "4567967a46cd9e9bf26d3bb491ddd422ad607775"

OMLX_STARTING_LOG = """\
2026-09-15 13:56:28,838 - omlx.server - INFO - Application startup complete.
2026-09-15 13:56:28,967 - omlx.engine_pool - INFO - Loading model: {model_id}
"""

OMLX_FAILED_LOAD_LOG = """\
2026-09-15 13:56:29,130 - omlx.engine_pool - WARNING - VLM loading failed for {model_id}, falling back to LLM: Received 1221 parameters not in model:
model.language_model.embed_tokens.biases,
model.language_model.embed_tokens.scales,
model.language_model.embed_tokens.weight,
Traceback (most recent call last):
RuntimeError: VLM load failed: Received 1221 parameters not in model: 
"""

ARTIFACT = "/Users/jrazz/.cache/huggingface/hub/mlx-community/gemma-4-12B-it-qat-OptiQ-4bit"
HF_ID = "mlx-community/gemma-4-12B-it-qat-OptiQ-4bit"


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=(), returncode=returncode, stdout=stdout, stderr=stderr
    )


def listener_probe(port):
    """The lsof invocation a stop makes to name the process holding the port."""
    return (runtimes.LSOF, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t")


class FakeClock:
    """Monotonic time that only moves when something sleeps or spawns."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += float(seconds)


def _sequence(values):
    """A callable yielding each value once, then repeating the last one forever."""
    remaining = list(values)

    def next_value():
        if len(remaining) > 1:
            return remaining.pop(0)
        return remaining[0] if remaining else ()

    return next_value


class Rig:
    """Fakes for every seam runtimes.py reaches outside itself with."""

    def __init__(self, monkeypatch, tmp_path):
        self.clock = FakeClock()
        self.log_file = tmp_path / "runtime.log"
        self.log = MLX_LM_HEALTHY_LOG
        self.inventory = ()
        self.listeners = set()
        self.free_after = {}
        self.busy_from = {}
        self.probes = {}
        self.alive = {}
        self.signals = []
        self.killed = []
        self.commands = []
        self.ran = []
        self.results = {}
        self.inventory_calls = 0
        self.api_keys = []
        self.spawn_seconds = 0.0
        self.spawn_alive = True
        self.term_kills = True
        self.kill_works = True
        self.run_unavailable = False
        self.next_pid = 4242
        self.tmp_path = tmp_path

        monkeypatch.setattr(runtimes, "_now", self.clock)
        monkeypatch.setattr(runtimes, "_sleep", self.clock.advance)
        monkeypatch.setattr(runtimes, "_spawn", self.spawn)
        monkeypatch.setattr(runtimes, "_inventory", self.inventory_response)
        monkeypatch.setattr(runtimes, "_port_is_free", self.port_is_free)
        monkeypatch.setattr(runtimes, "_process_alive", self.process_is_alive)
        monkeypatch.setattr(runtimes, "_signal_tree", self.signal_tree)
        monkeypatch.setattr(runtimes, "_signal_process", self.signal_process)
        monkeypatch.setattr(runtimes, "_run", self.run)
        monkeypatch.setattr(runtimes, "_log_path", lambda name: self.log_file)

    def spawn(self, command, log_path):
        self.commands.append(command)
        self.clock.advance(self.spawn_seconds)
        self.next_pid += 1
        self.alive[self.next_pid] = self.spawn_alive
        log_path.write_text(self.log)
        return self.next_pid

    def inventory_response(self, base_url, *, api_key=None):
        self.inventory_calls += 1
        self.api_keys.append(api_key)
        source = self.inventory
        value = source() if callable(source) else source
        if isinstance(value, BaseException):
            raise value
        return tuple(value)

    def port_is_free(self, port):
        """Free, unless a countdown says the port lingers -- `busy_from` skips a probe."""
        self.probes[port] = self.probes.get(port, 0) + 1
        if self.probes[port] <= self.busy_from.get(port, 0):
            return True
        remaining = self.free_after.get(port)
        if remaining is not None:
            if remaining > 0:
                self.free_after[port] = remaining - 1
                return False
            return True
        return port not in self.listeners

    def process_is_alive(self, pid):
        return self.alive.get(pid, False)

    def signal_tree(self, pid, sig):
        self.signals.append((pid, sig))
        if sig == signal.SIGKILL or self.term_kills:
            self.alive[pid] = False

    def signal_process(self, pid, sig):
        """The single-pid signal a recovered listener gets, never the process group."""
        self.killed.append((pid, sig))
        if self.kill_works:
            self.alive[pid] = False

    def run(self, command, timeout_s):
        self.ran.append(command)
        if self.run_unavailable:
            return None
        return self.results.get(command, _completed())


@pytest.fixture
def rig(monkeypatch, tmp_path):
    return Rig(monkeypatch, tmp_path)


@pytest.fixture
def artifact(tmp_path):
    """A real artifact directory: the oMLX catalog symlinks to it for real."""
    model = tmp_path / "hub" / "mlx-community" / "gemma-4-12B-it-qat-4bit"
    model.mkdir(parents=True)
    (model / "config.json").write_text("{}")
    return str(model)


@pytest.fixture
def hub_artifact(tmp_path):
    """A real artifact in hub layout, which is how a downloaded model is actually stored."""
    snapshot = (
        tmp_path / "hub" / "models--JANGQ-AI--Qwen3.5-4B-JANG_4S" / "snapshots" / OMLX_HASH
    )
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}")
    return str(snapshot)


# --------------------------------------------------------------------------------------
# The pinned interface
# --------------------------------------------------------------------------------------


def test_handle_carries_the_seven_pinned_fields_in_order():
    names = [field for field in Handle.__dataclass_fields__][:7]
    assert names == [
        "pid",
        "port",
        "base_url",
        "model_id",
        "version",
        "cold_load_s",
        "first_request_s",
    ]
    handle = Handle(
        pid=1,
        port=8081,
        base_url="http://127.0.0.1:8081/v1",
        model_id="m",
        version="0.31.3",
        cold_load_s=12.5,
    )
    assert handle.stop_command == () and handle.scratch is None
    # Nothing here makes a request, so nothing here can fill this in: the cold visit's first
    # warmup is the measurement loop's request to make and to time.
    assert handle.first_request_s is None


def test_runtimes_are_registered_by_name_on_the_ports_the_ticket_pins():
    assert {name: runtime.port for name, runtime in RUNTIMES.items()} == {
        "mlxlm": 8081,
        "osaurus": 1337,
        "omlx": 8100,
        "optiq": 8080,
        "vmlx": 8000,
    }
    assert all(name == runtime.name for name, runtime in RUNTIMES.items())
    assert RUNTIMES["omlx"].base_url == "http://127.0.0.1:8100/v1"
    ports = [runtime.port for runtime in RUNTIMES.values()]
    assert len(ports) == len(set(ports)), "two runtimes on one port is a run that cannot happen"


def test_module_imports_nothing_outside_the_standard_library():
    tree = ast.parse(Path(runtimes.__file__).read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= sys.stdlib_module_names


# --------------------------------------------------------------------------------------
# Flag tuples
# --------------------------------------------------------------------------------------


def test_mlxlm_start_command_is_pinned():
    assert RUNTIMES["mlxlm"].start_command(ARTIFACT, HF_ID) == (
        "python",
        "-m",
        "mlx_lm.server",
        "--model",
        ARTIFACT,
        "--port",
        "8081",
    )


def test_osaurus_start_command_is_pinned_and_takes_no_tuning_flags():
    osaurus = RUNTIMES["osaurus"]
    assert osaurus.start_command(ARTIFACT, HF_ID) == (
        "osaurus",
        "serve",
        "--port",
        "1337",
        "--yes",
    )
    assert osaurus.stop_command() == ("osaurus", "stop")


def test_optiq_start_command_is_pinned():
    assert RUNTIMES["optiq"].start_command(ARTIFACT, HF_ID) == (
        "optiq",
        "serve",
        "--model",
        ARTIFACT,
        "--host",
        "127.0.0.1",
        "--port",
        "8080",
        "--no-anthropic",
        "--no-responses",
        "--no-auth",
        "--max-context",
        "off",
        "--max-concurrent",
        "1",
        "--idle-timeout",
        "0",
        "--context-scale",
        "1.0",
        "--no-stream-experts",
        "--temp",
        "0",
        "--top-p",
        "1",
        "--top-k",
        "0",
        "--min-p",
        "0",
    )


def test_optiq_pins_expert_streaming_off_rather_than_leaving_it_auto():
    """Above 0.70 * RAM, OptiQ turns --stream-experts on by itself and decode drops ~5x."""
    command = RUNTIMES["optiq"].start_command(ARTIFACT, HF_ID)
    assert "--no-stream-experts" in command
    assert "--stream-experts" not in command
    assert "auto" not in command


def test_omlx_catalog_token_is_in_the_command_and_carried_through_the_scratch(artifact):
    command = RUNTIMES["omlx"].start_command(artifact, "gemma-4-12B-it-qat-4bit")
    assert command.count(runtimes.OMLX_CATALOG_TOKEN) == 1
    assert command[:6] == (
        "omlx",
        "serve",
        "--model-dir",
        runtimes.OMLX_CATALOG_TOKEN,
        "--host",
        "127.0.0.1",
    )
    assert command[-3:] == ("--memory-guard", "off", "--no-cache")


def test_create_omlx_scratch_removes_partial_root_on_failure(monkeypatch, artifact, tmp_path):
    root = tmp_path / "scratch-root"

    def make_root(**kwargs):
        root.mkdir()
        return str(root)

    monkeypatch.setattr(runtimes.tempfile, "mkdtemp", make_root)

    def fail_link(*args, **kwargs):
        raise OSError("symlink failed")

    monkeypatch.setattr(Path, "symlink_to", fail_link)

    with pytest.raises(OSError, match="symlink failed"):
        create_omlx_scratch(artifact, "gemma-4-12B-it-qat-4bit")

    assert not root.exists()


def test_omlx_injects_a_per_run_catalog_a_base_path_and_a_key(artifact):
    command, scratch = RUNTIMES["omlx"].build_command(artifact, "gemma-4-12B-it-qat-4bit")

    root = Path(scratch)
    catalog = root / runtimes.OMLX_CATALOG_DIRNAME
    base = root / runtimes.OMLX_BASE_DIRNAME
    assert command[command.index("--model-dir") + 1] == str(catalog)
    assert command[command.index("--base-path") + 1] == str(base)
    assert command[command.index("--api-key") + 1] == OMLX_API_KEY
    assert runtimes.OMLX_CATALOG_TOKEN not in command
    # A base path under the run's own scratch, never the user's configuration.
    assert base.is_dir() and Path.home() not in base.parents

    entries = list(catalog.iterdir())
    assert len(entries) == 1
    assert entries[0].is_symlink()
    assert entries[0].resolve() == Path(artifact).resolve()

    remove_omlx_catalog(catalog)
    assert not catalog.exists()
    shutil.rmtree(root, ignore_errors=True)


def test_omlx_link_name_avoids_the_slash_the_hf_id_has(artifact):
    link_name = runtimes.omlx_link_name(artifact, HF_ID)
    assert "/" not in link_name
    assert link_name == "gemma-4-12B-it-qat-4bit"


def test_vmlx_start_command_is_pinned():
    assert RUNTIMES["vmlx"].start_command(ARTIFACT, HF_ID) == (
        "vmlx",
        "serve",
        ARTIFACT,
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--served-model-name",
        HF_ID,
        "--stream-interval",
        "1",
        "--continuous-batching",
        "--max-num-seqs",
        "1",
        "--no-jit",
        "--disable-native-mtp",
        "--disable-prefix-cache",
        "--disable-block-disk-cache",
    )


def test_vmlx_takes_the_model_as_a_positional_argument_not_a_flag():
    """The one interface difference from every other runtime here
    (docs/runtimes/vmlx.md §2.2.1)."""
    command = RUNTIMES["vmlx"].start_command(ARTIFACT, HF_ID)
    assert command[:2] == ("vmlx", "serve")
    assert command[2] == ARTIFACT
    assert "--model" not in command


def test_vmlx_pins_off_the_two_things_a_bundle_turns_on_by_itself():
    """JIT defaults on for a JANG affine bundle and MTP for a bundle carrying MTP heads."""
    command = RUNTIMES["vmlx"].start_command(ARTIFACT, HF_ID)
    assert "--no-jit" in command and "--enable-jit" not in command
    assert "--disable-native-mtp" in command
    assert "--speculative-model" not in command


def test_vmlx_start_command_honors_enable_jit_env_var(monkeypatch):
    """The JIT A/B is a run-level pin and not a second start command: `1` moves the one flag
    JIT owns, and every other byte is still the command recorded before the toggle existed, so
    the two columns of that experiment differ in the variable under test and nothing else."""
    monkeypatch.setenv("OHYESMLX_VMLX_ENABLE_JIT", "1")
    jit_on = RUNTIMES["vmlx"].start_command(ARTIFACT, HF_ID)
    assert "--enable-jit" in jit_on
    assert "--no-jit" not in jit_on
    assert jit_on == tuple(
        "--enable-jit" if part == "--no-jit" else part for part in TODAY["vmlx"]
    )

    monkeypatch.setenv("OHYESMLX_VMLX_ENABLE_JIT", "0")
    assert RUNTIMES["vmlx"].start_command(ARTIFACT, HF_ID) == TODAY["vmlx"]

    monkeypatch.delenv("OHYESMLX_VMLX_ENABLE_JIT", raising=False)
    assert RUNTIMES["vmlx"].start_command(ARTIFACT, HF_ID) == TODAY["vmlx"]


def test_vmlx_pins_the_stream_interval_the_batching_flag_would_otherwise_overrule():
    """Without --continuous-batching the runtime forces the interval to 1 (cli.py:2892)."""
    command = RUNTIMES["vmlx"].start_command(ARTIFACT, HF_ID)
    assert command[command.index("--stream-interval") + 1] == "1"
    assert "--continuous-batching" in command
    assert "--no-continuous-batching" not in command


def test_vmlx_pins_the_caches_off_so_a_hit_cannot_publish_as_prefill():
    command = RUNTIMES["vmlx"].start_command(ARTIFACT, HF_ID)
    assert "--disable-prefix-cache" in command
    assert "--disable-block-disk-cache" in command
    assert "--enable-disk-cache" not in command


def test_no_pinned_command_carries_a_predecessor_placeholder():
    for runtime in RUNTIMES.values():
        command = " ".join(runtime.start_command(ARTIFACT, HF_ID))
        assert "LMRE" not in command
        assert "{" not in command.replace(runtimes.OMLX_CATALOG_TOKEN, "")


# --------------------------------------------------------------------------------------
# The cache pin (plan 06-02)
# --------------------------------------------------------------------------------------
#
# The five start commands with no cache pin: what every runtime ran before the pin existed.
# Written out rather than recomputed, because the claim is about bytes -- the way to check a
# command did not change is to compare it against the command that was recorded, not against
# the expression that produced it.

TODAY = {
    "mlxlm": ("python", "-m", "mlx_lm.server", "--model", ARTIFACT, "--port", "8081"),
    "osaurus": ("osaurus", "serve", "--port", "1337", "--yes"),
    "omlx": (
        "omlx", "serve", "--model-dir", runtimes.OMLX_CATALOG_TOKEN, "--host", "127.0.0.1",
        "--port", "8100", "--max-concurrent-requests", "1", "--memory-guard", "off",
        "--no-cache",
    ),
    "optiq": (
        "optiq", "serve", "--model", ARTIFACT, "--host", "127.0.0.1", "--port", "8080",
        "--no-anthropic", "--no-responses", "--no-auth", "--max-context", "off",
        "--max-concurrent", "1", "--idle-timeout", "0", "--context-scale", "1.0",
        "--no-stream-experts", "--temp", "0", "--top-p", "1", "--top-k", "0",
        "--min-p", "0",
    ),
    "vmlx": (
        "vmlx", "serve", ARTIFACT, "--host", "127.0.0.1", "--port", "8000",
        "--served-model-name", HF_ID, "--stream-interval", "1", "--continuous-batching",
        "--max-num-seqs", "1", "--no-jit", "--disable-native-mtp", "--disable-prefix-cache",
        "--disable-block-disk-cache",
    ),
}


def test_no_cache_pin_leaves_every_start_command_byte_identical_to_today():
    """Absent is not `off` and not `on`: the pin was never taken, so no runtime's command gains
    a cache flag, and every one of the five is the tuple this module built before the pin
    existed. An absent pin read as `off` would have added `--prompt-cache-size 0` to two of
    these commands and claimed a cache state nobody asked for."""
    assert set(TODAY) == set(RUNTIMES)
    for name, runtime in RUNTIMES.items():
        assert runtime.start_command(ARTIFACT, HF_ID) == TODAY[name]
        assert runtime.start_command(ARTIFACT, HF_ID, cache_state=None) == TODAY[name]


def test_mlxlm_and_optiq_pin_the_prompt_cache_size_in_both_states():
    """`--prompt-cache-size` is the LRUPromptCache's only control (mlx_lm/server.py:1872,
    default 10), and at 0 the cache holds nothing: every insert evicts the entry it just added
    (models/cache.py:1696-1737), so no later request can fetch a prefix. OptiQ runs the same
    server and takes the same flag through it."""
    for name in ("mlxlm", "optiq"):
        off = RUNTIMES[name].start_command(ARTIFACT, HF_ID, cache_state="off")
        on = RUNTIMES[name].start_command(ARTIFACT, HF_ID, cache_state="on")

        assert off == TODAY[name] + ("--prompt-cache-size", "0")
        assert on == TODAY[name] + ("--prompt-cache-size", "10")
        assert "--prompt-cache-size" not in TODAY[name]


def test_omlx_off_is_the_flag_it_already_passed_and_on_is_omitting_it():
    """`--no-cache` is "Disable oMLX paged SSD cache" (omlx/cli.py:1140-1143) and is already in
    the start command; `on` drops it, which leaves CacheSettings.enabled at its True default
    (settings.py:331) with the SSD directory under the per-run scratch base path
    (settings.py:387-399)."""
    off = RUNTIMES["omlx"].start_command(ARTIFACT, HF_ID, cache_state="off")
    on = RUNTIMES["omlx"].start_command(ARTIFACT, HF_ID, cache_state="on")

    assert off == TODAY["omlx"] and "--no-cache" in off
    assert "--no-cache" not in on
    assert tuple(part for part in off if part != "--no-cache") == on


def test_vmlx_moves_one_flag_between_its_states_and_holds_the_disk_tier_off_in_both():
    """The prefix cache is `--enable-prefix-cache`, default True (cli.py:3659), against
    `--disable-prefix-cache` (cli.py:3667). The SSD L2 stays disabled in both states: left unset
    it turns itself on the moment continuous batching and prefix caching are active
    (_apply_paged_block_disk_default, cli.py:661-701) and persists under the user's cache, which
    would make the two states differ in two things instead of one and put another run's prefix
    in an `on` cell."""
    off = RUNTIMES["vmlx"].start_command(ARTIFACT, HF_ID, cache_state="off")
    on = RUNTIMES["vmlx"].start_command(ARTIFACT, HF_ID, cache_state="on")

    assert off == TODAY["vmlx"]
    assert "--disable-prefix-cache" in off and "--enable-prefix-cache" not in off
    assert "--enable-prefix-cache" in on and "--disable-prefix-cache" not in on
    assert off.count("--disable-block-disk-cache") == 1
    assert on.count("--disable-block-disk-cache") == 1
    # Exactly one flag differs between the states, and it is the prefix cache's.
    assert [part for part in off if part != "--disable-prefix-cache"] == [
        part for part in on if part != "--enable-prefix-cache"
    ]


def test_osaurus_takes_no_cache_flag_in_either_state():
    """No flag in either direction: its cache state is host settings, so both states produce
    the one command, and a state the host is not in is refused rather than faked."""
    for state in (None, "off", "on"):
        assert RUNTIMES["osaurus"].start_command(ARTIFACT, HF_ID, cache_state=state) == (
            TODAY["osaurus"]
        )


def host_prefix_cache(monkeypatch, value):
    """The live ``cache.prefix.enabled`` the runtime reads, without touching the host's files."""
    monkeypatch.setattr(
        runtimes,
        "capture_osaurus_settings",
        lambda: {"server-runtime.json:cache.prefix.enabled": value},
    )


def test_osaurus_refuses_the_cache_state_the_host_is_not_in(monkeypatch):
    """The harness does not edit ~/.osaurus/config, so a requested state is honoured only when
    the host is already in it -- and the refusal says which setting disagreed, because that is
    the script's to change and not this runtime's."""
    osaurus = RUNTIMES["osaurus"]

    host_prefix_cache(monkeypatch, True)
    assert osaurus.cache_state_refusal("on") is None
    refusal = osaurus.cache_state_refusal("off")
    assert "cache.prefix.enabled" in refusal
    assert "true" in refusal
    assert "restart" in refusal, "a restart is not a way to turn a cache on"

    host_prefix_cache(monkeypatch, False)
    assert osaurus.cache_state_refusal("off") is None
    refusal = osaurus.cache_state_refusal("on")
    assert "cache.prefix.enabled" in refusal and "false" in refusal


def test_osaurus_refuses_a_host_it_cannot_read_rather_than_assuming_a_state(monkeypatch):
    osaurus = RUNTIMES["osaurus"]

    for sentinel in (osaurus_settings.UNREADABLE, osaurus_settings.MISSING):
        host_prefix_cache(monkeypatch, sentinel)
        for state in ("off", "on"):
            assert "unreadable" in osaurus.cache_state_refusal(state)


def test_the_absent_cache_pin_is_never_refused_and_the_flag_runtimes_never_refuse_either(
    monkeypatch,
):
    """The absent pin asks for no state, so nothing can refuse it; and the four runtimes whose
    cache state is a start flag can be driven into both states."""
    host_prefix_cache(monkeypatch, True)
    for runtime in RUNTIMES.values():
        assert runtime.cache_state_refusal(None) is None
    for name in ("mlxlm", "omlx", "optiq", "vmlx"):
        assert RUNTIMES[name].cache_state_refusal("off") is None
        assert RUNTIMES[name].cache_state_refusal("on") is None


# --------------------------------------------------------------------------------------
# Model-id aliasing
# --------------------------------------------------------------------------------------


def test_name_forms_cover_every_spelling_seen_between_these_runtimes():
    forms = name_forms(ARTIFACT)
    assert HF_ID in forms
    assert "mlx-community__gemma-4-12B-it-qat-OptiQ-4bit" in forms
    assert "omlx/gemma-4-12B-it-qat-OptiQ-4bit" in forms
    assert ARTIFACT in forms
    assert len(forms) == len(set(forms))


def test_each_runtime_asks_for_the_name_it_actually_serves_under():
    assert RUNTIMES["mlxlm"].model_id_candidates(ARTIFACT, HF_ID)[0] == ARTIFACT
    assert RUNTIMES["osaurus"].model_id_candidates(ARTIFACT, HF_ID)[0] == HF_ID
    assert RUNTIMES["omlx"].model_id_candidates(ARTIFACT, HF_ID)[0] == (
        "gemma-4-12B-it-qat-OptiQ-4bit"
    )
    assert RUNTIMES["optiq"].model_id_candidates(ARTIFACT, HF_ID)[0] == (
        f"{ARTIFACT}:no-think"
    )
    assert RUNTIMES["vmlx"].model_id_candidates(ARTIFACT, HF_ID)[0] == HF_ID


def test_osaurus_asks_for_the_name_the_hub_hides_the_repo_behind(hub_artifact):
    """Osaurus names a model after its repo, lowercased, and every spelling name_forms
    derives from a cache path is the commit hash -- which Osaurus never answers to. Its
    live inventory lists `qwen3.5-4b-jang_4s`, not `4567967a...`."""
    candidates = RUNTIMES["osaurus"].model_id_candidates(hub_artifact, "osaurus/stock4bit")

    assert candidates[0] == "qwen3.5-4b-jang_4s"
    assert runtimes.hub_repo_name(hub_artifact) == "qwen3.5-4b-jang_4s"
    # Every candidate the list had before, one place further back and none dropped.
    assert candidates[1:] == ("osaurus/stock4bit", *runtimes.name_forms(hub_artifact))


def test_a_path_that_is_not_a_hub_cache_is_unchanged(artifact):
    """A plain directory still leads with the model id the caller gave it."""
    assert runtimes.hub_repo_name(artifact) is None
    assert runtimes.hub_repo_name(ARTIFACT) is None
    assert RUNTIMES["osaurus"].model_id_candidates(artifact, HF_ID) == (
        HF_ID,
        *runtimes.name_forms(artifact),
    )


def test_vmlx_strips_a_path_to_the_name_it_actually_serves_under():
    """The three cases of its own normaliser (docs/runtimes/vmlx.md §9.5), including the one
    name_forms cannot spell: the flat hub layout, which is how an artifact is really cached."""
    hub = (
        "/Users/jrazz/.cache/huggingface/hub/"
        "models--JANGQ-AI--Qwen3.5-27B-JANG_4S/snapshots/3f9c1a2b"
    )
    candidates = RUNTIMES["vmlx"].model_id_candidates(hub, "Qwen3.5-27B-JANG_4S")

    assert candidates[0] == "JANGQ-AI/Qwen3.5-27B-JANG_4S"
    assert hub in candidates
    assert runtimes.vmlx_served_name("qwen3-4bit") == "qwen3-4bit"
    assert runtimes.vmlx_served_name("/Users/jrazz/models/qwen3-4bit") == "models/qwen3-4bit"


def test_every_runtimes_candidates_include_all_four_spellings():
    for runtime in RUNTIMES.values():
        candidates = runtime.model_id_candidates(ARTIFACT, HF_ID)
        assert HF_ID in candidates
        assert f"{ARTIFACT}:no-think" in candidates or ARTIFACT in candidates
        assert "mlx-community__gemma-4-12B-it-qat-OptiQ-4bit" in candidates


def test_resolve_model_id_answers_with_the_runtimes_own_spelling():
    candidates = name_forms(ARTIFACT)
    assert resolve_model_id(candidates, ("mlx-community__gemma-4-12B-it-qat-OptiQ-4bit",)) == (
        "mlx-community__gemma-4-12B-it-qat-OptiQ-4bit"
    )
    assert resolve_model_id(candidates, ("some-other-model",)) is None
    assert resolve_model_id(candidates, ()) is None


def test_resolve_model_id_prefers_the_order_it_was_given():
    assert resolve_model_id(("b", "a"), ("a", "b")) == "b"


# --------------------------------------------------------------------------------------
# The log-readiness parser
# --------------------------------------------------------------------------------------


def test_log_parser_finds_the_cause_of_a_dead_load():
    assert log_load_error(MLX_LM_DEAD_LOAD_LOG) == (
        "ValueError: Model type gemma4_unified not supported."
    )


def test_log_parser_does_not_mistake_starting_httpd_for_health():
    """The whole trap: this line appears after the load thread has already died."""
    assert "Starting httpd" in MLX_LM_DEAD_LOAD_LOG
    assert log_load_error("Starting httpd at 127.0.0.1 on port 8081...\n") is None
    assert log_load_error(MLX_LM_HEALTHY_LOG) is None


@pytest.mark.parametrize(
    "line",
    [
        "Address already in use",
        "error: model directory is empty",
        "[ERROR] failed to start engine",
        "unable to load weights from /tmp/model",
        "Segmentation fault: 11",
        "RuntimeError: memory guard refused the load",
    ],
)
def test_log_parser_catches_the_other_ways_a_runtime_dies(line):
    assert log_load_error(f"banner\n{line}\n") == line


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Fetching 12 files: 100%|##########| 12/12 [00:19<00:00,  1.62s/it]\n",
        "INFO: serving on 127.0.0.1:1337\nINFO: cache warm\n",
        "warning: top_p default differs between runtimes\n",
    ],
)
def test_log_parser_leaves_a_healthy_log_alone(text):
    assert log_load_error(text) is None


def test_log_parser_returns_the_last_failure_in_the_log():
    text = "ValueError: first\nRuntimeError: second\n"
    assert log_load_error(text) == "RuntimeError: second"


# --------------------------------------------------------------------------------------
# Readiness
# --------------------------------------------------------------------------------------


def test_start_returns_a_handle_only_after_the_model_id_appears(rig):
    rig.spawn_seconds = 12.5
    rig.inventory = _sequence([(), ("default_model",), (HF_ID,)])
    rig.results[("python", "-m", "mlx_lm", "--version")] = _completed(stdout="0.31.3\n")

    handle = RUNTIMES["mlxlm"].start(ARTIFACT, HF_ID)

    assert handle.model_id == HF_ID
    assert handle.port == 8081
    assert handle.base_url == "http://127.0.0.1:8081/v1"
    assert handle.version == "0.31.3"
    assert handle.cold_load_s == pytest.approx(12.5 + 2 * READY_POLL_S)
    assert rig.commands == [
        ("python", "-m", "mlx_lm.server", "--model", ARTIFACT, "--port", "8081")
    ]


def test_start_refuses_a_server_whose_load_died_even_though_the_model_is_listed(rig):
    """mlx-lm lists the --model path off disk, so the inventory cannot be the gate."""
    rig.log = MLX_LM_DEAD_LOAD_LOG
    rig.inventory = (ARTIFACT,)

    with pytest.raises(RuntimeStartError) as raised:
        RUNTIMES["mlxlm"].start(ARTIFACT, HF_ID)

    message = str(raised.value)
    assert "ValueError: Model type gemma4_unified not supported." in message
    assert str(rig.log_file) in message
    # The failed start does not leave a process behind holding 8081.
    assert rig.signals == [(rig.next_pid, signal.SIGTERM)]
    assert rig.inventory_calls == 0


def test_start_gives_a_35b_the_full_budget_before_giving_up(rig):
    rig.inventory = ()
    with pytest.raises(RuntimeStartError) as raised:
        RUNTIMES["mlxlm"].start(ARTIFACT, HF_ID)

    assert READY_TIMEOUT_S == 900.0
    assert "within 900s" in str(raised.value)
    assert rig.clock.t == pytest.approx(1000.0 + READY_TIMEOUT_S)


def test_start_fails_when_the_process_exits_before_it_is_ready(rig):
    rig.spawn_alive = False
    rig.inventory = ()

    with pytest.raises(RuntimeStartError) as raised:
        RUNTIMES["mlxlm"].start(ARTIFACT, HF_ID)

    assert "exited before it served" in str(raised.value)


def test_start_keeps_polling_through_connection_refused(rig):
    rig.inventory = _sequence([ConnectionRefusedError("refused"), (HF_ID,)])
    handle = RUNTIMES["mlxlm"].start(ARTIFACT, HF_ID)
    assert handle.model_id == HF_ID
    assert rig.inventory_calls == 2


def test_start_refuses_a_port_this_run_does_not_own(rig):
    """Another job holding a 20 GB model must not be started over, or killed."""
    rig.listeners.add(8081)

    with pytest.raises(RuntimeStartError) as raised:
        RUNTIMES["mlxlm"].start(ARTIFACT, HF_ID)

    assert "8081 is already held" in str(raised.value)
    assert rig.commands == []


def test_start_refuses_when_process_inspection_is_unavailable(rig):
    rig.results[("ps", "-axo", "pid=,args=")] = None

    with pytest.raises(RuntimeStartError, match="could not inspect running processes"):
        RUNTIMES["mlxlm"].start(ARTIFACT, HF_ID)

    assert rig.commands == []


def test_start_refuses_stale_osaurus_app_by_full_executable_path(rig, monkeypatch):
    app = "/Applications/osaurus.app/Contents/MacOS/osaurus"
    rig.results[("ps", "-axo", "pid=,args=")] = _completed(
        stdout=f"111 {app} --serve\n222 osaurus mcp\n333 /tmp/osaurus\n"
    )
    monkeypatch.setattr(runtimes, "_process_alive", lambda pid: pid == 111)

    with pytest.raises(RuntimeStartError) as raised:
        RUNTIMES["mlxlm"].start(ARTIFACT, HF_ID)

    assert "111" in str(raised.value)
    assert "222" not in str(raised.value)
    assert rig.commands == []
    assert ("ps", "-axo", "pid=,args=") in rig.ran


def test_start_does_not_match_osaurus_mcp_or_other_binary(rig, monkeypatch):
    rig.results[("ps", "-axo", "pid=,args=")] = _completed(
        stdout="222 osaurus mcp\n333 /tmp/osaurus\n"
    )
    monkeypatch.setattr(runtimes, "_process_alive", lambda pid: pid > 4242)
    rig.inventory = (HF_ID,)

    handle = RUNTIMES["mlxlm"].start(ARTIFACT, HF_ID)

    assert handle.model_id == HF_ID
    assert rig.commands


def test_start_surfaces_cleanup_failure_chained_from_start_error(rig, monkeypatch):
    start_error = RuntimeStartError("readiness failed")

    def fail_ready(self, **kwargs):
        raise start_error

    monkeypatch.setattr(runtimes.Runtime, "await_ready", fail_ready)

    def fail_shutdown(*args, **kwargs):
        raise RuntimeStopError("cleanup failed")

    monkeypatch.setattr(runtimes, "_shutdown", fail_shutdown)

    with pytest.raises(RuntimeStopError) as raised:
        RUNTIMES["mlxlm"].start(ARTIFACT, HF_ID)

    assert "cleanup failed" in str(raised.value)
    assert "readiness failed" in str(raised.value)
    assert raised.value.__cause__ is start_error


def test_start_reports_the_servers_error_and_still_frees_the_port(rig):
    rig.log = "Traceback (most recent call last):\nOSError: disk full\n"
    # Free at the ownership probe, then lingering while the killed server lets go.
    rig.busy_from[8081] = 1
    rig.free_after[8081] = 3

    with pytest.raises(RuntimeStartError):
        RUNTIMES["mlxlm"].start(ARTIFACT, HF_ID)

    assert rig.signals and rig.signals[0][1] == signal.SIGTERM
    assert rig.free_after[8081] == 0


def test_a_model_that_failed_to_load_as_the_list_answered_is_not_a_started_runtime(
    rig, hub_artifact
):
    """Live: oMLX served /v1/models from a scan of its catalog, listed this JANG artifact,
    and the VLM path had already failed on it when the list answered
    (results/logs/omlx-20260915T135626-71559.log). The harness returned a handle and
    published cold_load_s = 2.15 for weights that were never in memory."""
    rig.log = OMLX_STARTING_LOG.format(model_id=OMLX_HASH)

    def listed_as_the_load_died():
        rig.log_file.write_text(OMLX_FAILED_LOAD_LOG.format(model_id=OMLX_HASH))
        return (OMLX_HASH,)

    rig.inventory = listed_as_the_load_died

    with pytest.raises(RuntimeStartError) as raised:
        RUNTIMES["omlx"].start(hub_artifact, "osaurus/stock4bit")

    assert "RuntimeError: VLM load failed" in str(raised.value)
    assert str(rig.log_file) in str(raised.value)
    assert rig.clock.t == pytest.approx(1000.0), "the log failed it, not the 900 s budget"
    assert rig.inventory_calls == 1
    assert rig.signals == [(rig.next_pid, signal.SIGTERM)]


def test_a_failure_is_still_visible_behind_the_parameter_dump_that_explains_it(tmp_path):
    """The dump is one parameter name per line and oMLX prints it three times. Live, a
    4B dump put the fatal line 1.4 KB inside a 64 KB tail -- and past it by the next read
    (results/logs/omlx-20260915T135626-71559.log)."""
    log = tmp_path / "omlx.log"
    dump = "".join(f"model.language_model.layers.{index}.weight,\n" for index in range(8000))
    log.write_text(OMLX_FAILED_LOAD_LOG.format(model_id=OMLX_HASH) + dump)

    assert log.stat().st_size > 256 * 1024, "the dump has to outgrow a 64 KB tail"
    assert log_load_error(runtimes._read_log(log)) == (
        "RuntimeError: VLM load failed: Received 1221 parameters not in model:"
    )


def test_vmlx_readiness_is_gated_on_the_log_and_not_on_the_model_list(rig):
    """The shared gate, and the reason it is shared: a load that died is fatal however
    healthy the inventory looks. vMLX's own readiness marker is on stderr, which _spawn
    merges into the same log, so a traceback here is read the same way as anywhere else."""
    rig.log = "Traceback (most recent call last):\nOSError: weights missing at ...\n"
    rig.inventory = (HF_ID,)

    with pytest.raises(RuntimeStartError) as raised:
        RUNTIMES["vmlx"].start(ARTIFACT, HF_ID)

    assert "OSError: weights missing at ..." in str(raised.value)
    assert rig.inventory_calls == 0


def test_vmlx_starts_without_a_key_and_records_the_version_it_read(rig):
    rig.inventory = (HF_ID,)
    rig.results[RUNTIMES["vmlx"].version_command()] = _completed(stdout="1.6.59\n")

    handle = RUNTIMES["vmlx"].start(ARTIFACT, HF_ID)

    assert handle.model_id == HF_ID
    assert handle.version == "1.6.59"
    assert handle.port == 8000
    assert handle.base_url == "http://127.0.0.1:8000/v1"
    # No --api-key in the start command, so the readiness poll and the measurement both
    # send nothing and the server accepts both.
    assert handle.api_key is None
    assert rig.api_keys == [None]


# --------------------------------------------------------------------------------------
# Stop, and the port-free rule
# --------------------------------------------------------------------------------------


def test_stop_does_not_return_while_the_port_is_still_held(rig):
    rig.free_after = {8081: 2 * 3}
    handle = Handle(
        pid=rig.next_pid,
        port=8081,
        base_url="http://127.0.0.1:8081/v1",
        model_id=HF_ID,
        version="0.31.3",
        cold_load_s=1.0,
    )
    rig.alive[rig.next_pid] = True

    handle.stop()

    assert rig.free_after[8081] == 0
    assert rig.clock.t > 1000.0
    assert rig.signals == [(rig.next_pid, signal.SIGTERM)]


def test_stop_raises_if_spawned_pid_survives_sigkill(rig, monkeypatch):
    rig.alive[777] = True
    monkeypatch.setattr(runtimes, "_signal_tree", lambda pid, sig: None)
    monkeypatch.setattr(runtimes, "_await_exit", lambda pid, timeout_s: False)
    handle = Handle(
        pid=777,
        port=8081,
        base_url="http://127.0.0.1:8081/v1",
        model_id=HF_ID,
        version="0.31.3",
        cold_load_s=1.0,
    )

    with pytest.raises(RuntimeStopError, match="777.*SIGKILL"):
        handle.stop()


def test_stop_escalates_to_sigkill_when_sigterm_is_ignored(rig):
    rig.term_kills = False
    handle = Handle(
        pid=777,
        port=8081,
        base_url="http://127.0.0.1:8081/v1",
        model_id=HF_ID,
        version="0.31.3",
        cold_load_s=1.0,
    )
    rig.alive[777] = True

    handle.stop()

    assert [sig for _pid, sig in rig.signals] == [signal.SIGTERM, signal.SIGKILL]
    assert rig.alive[777] is False


def test_stop_refuses_handoff_cleanup_when_listener_probe_is_unavailable(rig):
    handle = osaurus_handle()
    rig.run_unavailable = True

    with pytest.raises(RuntimeStopError) as raised:
        handle.stop()

    assert "cannot identify listeners" in str(raised.value)
    assert rig.ran == [listener_probe(1337)]


def test_stop_runs_the_runtimes_own_stop_command(rig):
    handle = Handle(
        pid=777,
        port=1337,
        base_url="http://127.0.0.1:1337/v1",
        model_id="ornith-1.0-35b-jang_4m",
        version="0.25.3",
        cold_load_s=90.0,
        stop_command=("osaurus", "stop"),
    )
    rig.alive[777] = True

    handle.stop()

    # The listeners are read first: the stop command is what frees the port, and a process it
    # leaves behind can no longer be named by that port afterwards.
    assert rig.ran == [listener_probe(1337), ("osaurus", "stop")]


def test_vmlx_stop_is_a_signal_because_there_is_no_stop_subcommand(rig):
    assert RUNTIMES["vmlx"].stop_command() == ()
    handle = Handle(
        pid=777,
        port=8000,
        base_url="http://127.0.0.1:8000/v1",
        model_id=HF_ID,
        version="1.6.59",
        cold_load_s=1.0,
        stop_command=RUNTIMES["vmlx"].stop_command(),
    )
    rig.alive[777] = True

    handle.stop()

    assert rig.ran == [listener_probe(8000)], "nothing to run: the signal is the stop"
    assert rig.signals == [(777, signal.SIGTERM)]


def test_stop_raises_when_the_port_never_comes_free(rig):
    rig.free_after = {8081: 10**6}
    handle = Handle(
        pid=1,
        port=8081,
        base_url="http://127.0.0.1:8081/v1",
        model_id=HF_ID,
        version="0.31.3",
        cold_load_s=1.0,
    )

    with pytest.raises(RuntimeStopError) as raised:
        handle.stop()

    assert "8081 is still held" in str(raised.value)


def test_stop_verifies_the_port_even_when_the_process_already_exited(rig):
    handle = Handle(
        pid=1,
        port=8081,
        base_url="http://127.0.0.1:8081/v1",
        model_id=HF_ID,
        version="0.31.3",
        cold_load_s=1.0,
    )

    handle.stop()

    assert rig.signals == []


# --- the process a stop command leaves behind ---------------------------------------------

# Live 2026-09-15: `osaurus stop` frees port 1337, the app process the launcher started keeps
# running, and a five-format probe plus two manual tests left seven of them resident for ~50
# minutes -- each holding weights and contending for the memory a run is trying to measure.
OSAURUS_APP_PID = 93777


def listener_probe(port):
    """The lsof invocation a stop makes to name the process holding the port."""
    return (runtimes.LSOF, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t")


def launcher_handed_off(rig, *, port=1337, app_pid=OSAURUS_APP_PID):
    """The live shape: the launcher exits once the app answers, and the app holds the port."""
    rig.alive[app_pid] = True
    rig.results[listener_probe(port)] = _completed(stdout=f"{app_pid}\n")


def osaurus_handle(**kwargs):
    fields = {
        "pid": 777,
        "port": 1337,
        "base_url": "http://127.0.0.1:1337/v1",
        "model_id": "ornith-1.0-35b-jang_4m",
        "version": "0.25.3",
        "cold_load_s": 90.0,
        "stop_command": ("osaurus", "stop"),
    }
    fields.update(kwargs)
    return Handle(**fields)


def test_stop_kills_the_process_the_launcher_left_holding_the_weights(rig):
    """A freed port is not a stopped runtime: the launcher is gone, the app is not."""
    handle = osaurus_handle()
    launcher_handed_off(rig)

    handle.stop()

    assert rig.ran == [listener_probe(1337), ("osaurus", "stop")]
    # One pid, killed directly -- never its process group, and never anything found by name:
    # `osaurus mcp` is a long-running user process on this machine.
    assert rig.killed == [(OSAURUS_APP_PID, signal.SIGKILL)]
    assert rig.alive[OSAURUS_APP_PID] is False
    assert rig.signals == [], "the launcher was already gone; it is not signalled again"


def test_stop_does_not_return_while_that_process_still_lives(rig):
    rig.kill_works = False
    handle = osaurus_handle()
    launcher_handed_off(rig)

    with pytest.raises(RuntimeStopError) as raised:
        handle.stop()

    assert str(OSAURUS_APP_PID) in str(raised.value)
    assert "still listening on this runtime's port" in str(raised.value)
    assert rig.alive[OSAURUS_APP_PID] is True


def test_a_listener_that_is_the_spawned_pid_is_not_signalled_twice(rig):
    """mlx-lm's server *is* the pid this run spawned, so the group signal owns it already."""
    rig.alive[777] = True
    rig.results[listener_probe(8081)] = _completed(stdout="777\n")
    handle = osaurus_handle(port=8081, stop_command=())

    handle.stop()

    assert rig.signals == [(777, signal.SIGTERM)]
    assert rig.killed == []


def test_listener_pids_name_the_process_holding_the_port():
    """Against the real lsof, because this is the one thing a fake cannot be trusted to
    prove: the pid it names is what a stop has to kill."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        assert os.getpid() in runtimes._listener_pids(port)

    assert runtimes._listener_pids(port) == ()


def test_listener_pids_of_an_unrunnable_lsof_is_unknown(monkeypatch):
    monkeypatch.setattr(runtimes, "_run", lambda command, timeout_s: None)
    assert runtimes._listener_pids(8081) is None


def test_serving_pid_keeps_spawned_pid_when_listener_probe_is_unavailable(monkeypatch):
    monkeypatch.setattr(runtimes, "_listener_pids", lambda port: None)
    assert runtimes._serving_pid(4242, 8081) == 4242


def test_await_port_free_returns_immediately_when_nothing_listens(rig):
    await_port_free(8081, timeout_s=1.0)
    assert rig.clock.t == 1000.0


def test_stop_removes_the_omlx_scratch_it_created(artifact, rig):
    scratch = create_omlx_scratch(artifact, "gemma-4-12B-it-qat-4bit")
    handle = Handle(
        pid=1,
        port=8100,
        base_url="http://127.0.0.1:8100/v1",
        model_id="gemma-4-12B-it-qat-4bit",
        version="0.6.4",
        cold_load_s=1.0,
        scratch=str(scratch.root),
    )

    handle.stop()

    assert not scratch.root.exists()
    assert Path(artifact).exists(), "the artifact is not the harness's to delete"


def test_a_catalog_holding_something_we_did_not_create_is_not_deleted(tmp_path):
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "someone-elses-weights").mkdir()

    with pytest.raises(RuntimeStopError):
        remove_omlx_catalog(catalog)

    assert (catalog / "someone-elses-weights").exists()


# --------------------------------------------------------------------------------------
# The port probe, against the real lsof
# --------------------------------------------------------------------------------------


def test_port_probe_follows_a_real_listener():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        assert runtimes._port_is_free(port) is False

    assert runtimes._port_is_free(port) is True


def test_port_probe_treats_an_unrunnable_lsof_as_busy(monkeypatch):
    monkeypatch.setattr(runtimes, "_run", lambda command, timeout_s: None)
    assert runtimes._port_is_free(8081) is False


# --------------------------------------------------------------------------------------
# Osaurus settings attestation
# --------------------------------------------------------------------------------------

CONFIG_SERVER = {
    "backlog": 256,
    "modelEvictionPolicy": "Strict (One Model)",
    "modelIdleResidencyPolicy": {"mode": "after_seconds", "seconds": 900},
    "modelLoadRAMHardThreshold": 0.9,
    "modelLoadRAMSoftThreshold": 0.8,
    "numberOfThreads": 12,
}
CONFIG_RUNTIME = {
    "cache": {
        "blockDisk": {"enabled": True, "maxSizePercent": 10},
        "defaultMaxKVSize": 65536,
        "liveKVCodec": "engine_selected",
        "longPromptMultiplier": 2,
        "pagedKV": {"enabled": False},
        "prefix": {"enabled": True},
        "storedKVCodec": "auto",
    },
    "concurrency": {"continuousBatching": True, "maxConcurrentSequences": 1},
    "generation": {"streamInterval": 1},
    "memorySafety": {"mode": "safe_auto", "slider": 2},
    "mtp": {"mode": "auto"},
    "performance": {"compiledDecode": False, "tiedHeadCodec": "q6"},
}


@pytest.fixture
def osaurus_config(tmp_path):
    root = tmp_path / "config"
    root.mkdir()
    (root / "server.json").write_text(json.dumps(CONFIG_SERVER))
    (root / "server-runtime.json").write_text(json.dumps(CONFIG_RUNTIME))
    return root


def test_capture_reads_every_tracked_measurement_key(osaurus_config):
    settings = osaurus_settings.capture_osaurus_settings(osaurus_config)

    assert set(settings) == {
        f"{filename}:{dotted}"
        for filename, dotted in osaurus_settings.TRACKED_KEYS
    }
    assert settings["server.json:numberOfThreads"] == 12
    assert settings["server-runtime.json:concurrency.maxConcurrentSequences"] == 1
    assert settings["server-runtime.json:cache.prefix.enabled"] is True
    assert osaurus_settings.MISSING not in settings.values()
    assert osaurus_settings.UNREADABLE not in settings.values()


def test_capture_marks_a_host_it_cannot_read_instead_of_raising(tmp_path):
    settings = osaurus_settings.capture_osaurus_settings(tmp_path / "absent")

    assert set(settings.values()) == {osaurus_settings.UNREADABLE}


def test_capture_marks_absent_keys_as_missing(osaurus_config):
    (osaurus_config / "server.json").write_text(json.dumps({"backlog": 256}))
    settings = osaurus_settings.capture_osaurus_settings(osaurus_config)

    assert settings["server.json:numberOfThreads"] == osaurus_settings.MISSING
    assert settings["server.json:backlog"] == 256


def test_diff_reports_changed_added_and_removed_keys():
    drift = osaurus_settings.diff_against_baseline(
        {"a": 1, "b": 2},
        {"a": 9, "c": 3},
    )

    assert drift == (
        ("a", 9, 1),
        ("b", osaurus_settings.MISSING, 2),
        ("c", 3, osaurus_settings.MISSING),
    )
    assert osaurus_settings.diff_against_baseline({"a": 1}, {"a": 1}) == ()


def test_describe_drift_names_the_key_the_baseline_and_the_host():
    text = osaurus_settings.describe_drift((("cache.prefix.enabled", True, False),))
    assert "cache.prefix.enabled" in text
    assert "baseline True" in text
    assert "host False" in text


def test_baseline_missing_returns_none_but_existing_invalid_data_raises_value_error(tmp_path):
    absent = tmp_path / "absent.json"
    assert osaurus_settings.load_baseline(absent) is None

    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json")
    with pytest.raises(ValueError, match=str(invalid)):
        osaurus_settings.load_baseline(invalid)

    wrong_shape = tmp_path / "wrong-shape.json"
    wrong_shape.write_text('{"settings": []}')
    with pytest.raises(ValueError, match=str(wrong_shape)):
        osaurus_settings.load_baseline(wrong_shape)


def test_baseline_round_trips_through_a_file(tmp_path, osaurus_config):
    path = tmp_path / "baseline.json"
    written = osaurus_settings.write_baseline(path, osaurus_config)

    assert osaurus_settings.load_baseline(path) == written
    assert osaurus_settings.load_baseline(tmp_path / "absent.json") is None


def test_the_checked_in_baseline_is_readable_and_complete():
    baseline = osaurus_settings.load_baseline()

    assert baseline is not None, "config/osaurus-settings-baseline.json is missing"
    assert set(baseline) == {
        f"{filename}:{dotted}"
        for filename, dotted in osaurus_settings.TRACKED_KEYS
    }
    assert osaurus_settings.UNREADABLE not in baseline.values()


def test_osaurus_refuses_to_start_when_existing_baseline_is_invalid(rig, monkeypatch, tmp_path):
    baseline = tmp_path / "baseline.json"
    baseline.write_text("not json")
    monkeypatch.setattr(runtimes, "load_baseline", lambda: osaurus_settings.load_baseline(baseline))

    with pytest.raises(RuntimeStartError, match=str(baseline)):
        RUNTIMES["osaurus"].start(ARTIFACT, "ornith-1.0-35b-jang_4m")

    assert rig.commands == []


def test_osaurus_refuses_to_start_when_the_host_drifted_from_the_baseline(
    rig, monkeypatch
):
    monkeypatch.setattr(
        runtimes, "load_baseline", lambda: {"server.json:numberOfThreads": 12}
    )
    monkeypatch.setattr(
        runtimes,
        "capture_osaurus_settings",
        lambda: {"server.json:numberOfThreads": 8},
    )

    with pytest.raises(RuntimeStartError) as raised:
        RUNTIMES["osaurus"].start(ARTIFACT, "ornith-1.0-35b-jang_4m")

    assert "drifted from the recorded baseline" in str(raised.value)
    assert "server.json:numberOfThreads: baseline 12, host 8" in str(raised.value)
    assert rig.commands == []


def test_osaurus_starts_when_the_settings_match_the_baseline(rig, monkeypatch):
    monkeypatch.setattr(
        runtimes, "load_baseline", lambda: {"server.json:numberOfThreads": 12}
    )
    monkeypatch.setattr(
        runtimes,
        "capture_osaurus_settings",
        lambda: {"server.json:numberOfThreads": 12},
    )
    rig.inventory = ("ornith-1.0-35b-jang_4m",)
    rig.results[("osaurus", "doctor", "--json", "--redact")] = _completed(
        stdout=json.dumps({"apps": [{"version": "0.25.3", "isRunning": True}]})
    )

    handle = RUNTIMES["osaurus"].start(ARTIFACT, "ornith-1.0-35b-jang_4m")

    assert handle.version == "0.25.3"
    assert handle.model_id == "ornith-1.0-35b-jang_4m"
    assert handle.stop_command == ("osaurus", "stop")


def test_baseline_missing_file_returns_none_but_existing_unreadable_file_raises(tmp_path, monkeypatch):
    absent = tmp_path / "absent.json"
    assert osaurus_settings.load_baseline(absent) is None

    unreadable = tmp_path / "unreadable.json"
    unreadable.write_text('{}')
    original_read_text = Path.read_text

    def read_text(path, *args, **kwargs):
        if path == unreadable:
            raise PermissionError("denied")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)
    with pytest.raises(ValueError, match=str(unreadable)):
        osaurus_settings.load_baseline(unreadable)


def test_osaurus_starts_when_no_baseline_has_been_recorded(rig, monkeypatch):
    monkeypatch.setattr(runtimes, "load_baseline", lambda: None)
    rig.inventory = ("ornith-1.0-35b-jang_4m",)

    handle = RUNTIMES["osaurus"].start(ARTIFACT, "ornith-1.0-35b-jang_4m")

    assert handle.model_id == "ornith-1.0-35b-jang_4m"
    assert handle.version.startswith("unknown:")


def test_osaurus_samples_the_app_the_launcher_handed_the_port_to(rig, monkeypatch):
    """`osaurus serve` exits once the app answers: its footprint is 4.7 MB of nothing."""
    monkeypatch.setattr(runtimes, "load_baseline", lambda: None)
    rig.inventory = ("ornith-1.0-35b-jang_4m",)
    rig.results[listener_probe(1337)] = _completed(stdout=f"{OSAURUS_APP_PID}\n")

    handle = RUNTIMES["osaurus"].start(ARTIFACT, "ornith-1.0-35b-jang_4m")

    assert handle.pid != OSAURUS_APP_PID, "the launcher is what this run spawned"
    assert handle.memory_pid == OSAURUS_APP_PID
    # The pid signalled on stop is still the spawned one; only the sampler moved.
    assert handle.serving_pid == OSAURUS_APP_PID


def test_a_port_that_names_nothing_leaves_the_sampler_on_the_spawned_pid(rig):
    rig.inventory = (HF_ID,)
    rig.results[("python", "-m", "mlx_lm", "--version")] = _completed(stdout="0.31.3\n")

    handle = RUNTIMES["mlxlm"].start(ARTIFACT, HF_ID)

    assert handle.memory_pid == handle.pid


def test_an_ambiguous_port_samples_the_spawned_pid_rather_than_a_stranger(rig):
    """Two listeners is not a resolution: never publish a stranger's footprint as ours."""
    rig.inventory = (HF_ID,)
    rig.results[listener_probe(8081)] = _completed(stdout="900\n901\n")

    handle = RUNTIMES["mlxlm"].start(ARTIFACT, HF_ID)

    assert handle.memory_pid == handle.pid


def test_osaurus_version_prefers_the_bundle_that_is_serving():
    osaurus = RUNTIMES["osaurus"]
    output = json.dumps(
        {
            "apps": [
                {"version": "0.24.0", "isRunning": False},
                {"version": "0.25.3", "isRunning": True},
            ]
        }
    )
    assert osaurus.parse_version(output) == "0.25.3 (one of 2 bundles)"
    assert osaurus.parse_version("not json").startswith("unknown:")
    assert osaurus.parse_version(json.dumps({"apps": []})).startswith("unknown:")


def test_version_absence_says_why(rig):
    rig.results[("omlx", "--version")] = _completed(returncode=2, stdout="")
    assert RUNTIMES["omlx"].version() == "unknown: exited with code 2"


def test_vmlx_version_does_not_come_from_a_flag_that_errors(rig):
    """`vmlx --version` exits 2 with 'unrecognized arguments', so provenance is the engine's
    own constant read out of the source the bundle ships (docs/runtimes/vmlx.md §9.4)."""
    command = RUNTIMES["vmlx"].version_command()
    assert "--version" not in command
    rig.results[command] = _completed(stdout="1.6.59\n")
    assert RUNTIMES["vmlx"].version() == "1.6.59"


def test_vmlx_reads_the_constant_instead_of_importing_the_engine():
    """start() times cold load across version(), and importing the engine measured 9.2s.
    That would have been published as vMLX's cold load, which is a harness artifact."""
    command = RUNTIMES["vmlx"].version_command()
    assert command[:2] == ("sed", "-n")
    assert command[-1] == runtimes.VMLX_ENGINE_INIT
    assert "python" not in " ".join(command)


def test_vmlx_version_sed_reads_the_constant_and_nothing_else(tmp_path):
    """The real sed program, against a module shaped like the one in the bundle."""
    module = tmp_path / "__init__.py"
    module.write_text('"""vMLX engine."""\n\n__version__ = "1.6.59"\nOTHER = "0.0.0"\n')

    result = subprocess.run(
        ("sed", "-n", runtimes.VMLX_VERSION_SED, str(module)),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == "1.6.59\n"


def test_vmlx_version_absence_says_which_way_it_was_absent(rig):
    command = RUNTIMES["vmlx"].version_command()
    rig.results[command] = _completed(returncode=2, stdout="")
    assert RUNTIMES["vmlx"].version() == "unknown: exited with code 2"
    rig.results[command] = _completed(stdout="")
    assert RUNTIMES["vmlx"].version() == "unknown: empty version output"


def test_omlx_polls_with_its_own_key(rig):
    rig.inventory = ("gemma-4-12B-it-qat-OptiQ-4bit",)
    rig.alive[1] = True
    RUNTIMES["omlx"].await_ready(
        pid=1, log_path=rig.log_file, artifact_dir=ARTIFACT, model_id=HF_ID
    )
    assert rig.api_keys == [OMLX_API_KEY]


def test_mlxlm_polls_without_a_key(rig):
    rig.inventory = (ARTIFACT,)
    rig.alive[1] = True
    RUNTIMES["mlxlm"].await_ready(
        pid=1, log_path=rig.log_file, artifact_dir=ARTIFACT, model_id=HF_ID
    )
    assert rig.api_keys == [None]


def test_optiq_records_the_version_and_not_the_sentence_around_it():
    """`optiq --version` answers `mlx-optiq, version 0.5.6`.

    The grid's join guard compares this string exactly across run directories to decide
    whether one runtime appeared at two versions. Recording the runtime's phrasing rather
    than its version means a release that reworded its own --version output would read as a
    version change and refuse a legal join.
    """
    optiq = runtimes.RUNTIMES["optiq"]

    assert optiq.parse_version("mlx-optiq, version 0.5.6\n") == "0.5.6"
    assert optiq.parse_version("mlx-optiq, version 0.6.0") == "0.6.0"
    # An unrecognised shape is recorded verbatim rather than parsed into a plausible lie.
    assert optiq.parse_version("0.5.6") == "0.5.6"
    assert optiq.parse_version("optiq v0.5.6") == "optiq v0.5.6"
    assert optiq.parse_version("") == "unknown: empty version output"
