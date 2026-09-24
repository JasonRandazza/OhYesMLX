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


def host_live_kv_codec(monkeypatch, value):
    """The live ``cache.liveKVCodec`` the runtime reads, without touching the host's files."""
    monkeypatch.setattr(
        runtimes,
        "capture_osaurus_settings",
        lambda: {"server-runtime.json:cache.liveKVCodec": value},
    )


def host_mtp_mode(monkeypatch, value):
    """The live ``mtp.mode`` the runtime reads -- a tracked key, read through the same capture."""
    monkeypatch.setattr(
        runtimes,
        "capture_osaurus_settings",
        lambda: {"server-runtime.json:mtp.mode": value},
    )


def host_smelt_mode(monkeypatch, value):
    """The live ``concurrency.smeltMode``. Not a tracked key, so it has its own reader."""
    monkeypatch.setattr(runtimes, "osaurus_smelt_mode", lambda: value)


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
# The KV-quantization pin (study 03-05)
# --------------------------------------------------------------------------------------
#
# The codec a runtime's KV cache is held in, one cache down from `cache_state` and built the
# same way. The values name a codec rather than a width, and `fp8` is not one of them: nothing
# in this set has an FP8 KV codec, and the earlier study's "FP8" arms were `mx.quantize` affine
# 8-bit. Per-runtime evidence: docs/research/2026-09-24-kv-quant-surface.md §2.3, §9, §11.


def test_the_kv_quant_values_name_a_codec_and_fp8_is_not_one_of_them():
    """`fp8` reads as a float8 codec and there is none here, so the value is retired rather than
    aliased onto `affine8`; `int4` is not used either, because it is true of the affine path and
    false of the TurboQuant codebook codecs two of these runtimes carry."""
    assert runtimes.KV_QUANTS == ("off", "affine8", "affine4")
    assert "fp8" not in runtimes.KV_QUANTS
    assert "int4" not in runtimes.KV_QUANTS
    assert "int8" not in runtimes.KV_QUANTS


def test_no_kv_quant_pin_leaves_every_start_command_byte_identical_to_today():
    """Absent is not `off`: the pin was never taken, so no runtime's command gains a flag and
    every one of the five is the tuple this module built before the pin existed. An absent pin
    read as `off` would have added `--kv-cache-quantization none` to vMLX's command and claimed
    a codec nobody asked about."""
    assert set(TODAY) == set(RUNTIMES)
    for name, runtime in RUNTIMES.items():
        assert runtime.start_command(ARTIFACT, HF_ID) == TODAY[name]
        assert runtime.start_command(ARTIFACT, HF_ID, kv_quant=None) == TODAY[name]


def test_optiq_drives_all_three_values_and_pins_the_group_size_with_each_codec():
    """`--kv-bits` is OptiQ's own flag (`optiq/cli.py:2502-2503`) and, because OptiQ consumes
    it, it is not forwarded to the mlx_lm.server underneath. `off` is the *absence* of the flag:
    there is no `--kv-bits none` and no `--no-kv-quant`, so `off` and an absent pin build one
    command, and that is the state OptiQ defaults to (`cli.py:2332-2347`). The group size is
    pinned with each codec rather than inherited, because it is a second variable and 64 is only
    today's default (`cli.py:2504`)."""
    off = RUNTIMES["optiq"].start_command(ARTIFACT, HF_ID, kv_quant="off")
    eight = RUNTIMES["optiq"].start_command(ARTIFACT, HF_ID, kv_quant="affine8")
    four = RUNTIMES["optiq"].start_command(ARTIFACT, HF_ID, kv_quant="affine4")

    assert off == TODAY["optiq"]
    assert eight == TODAY["optiq"] + ("--kv-bits", "8", "--kv-group-size", "64")
    assert four == TODAY["optiq"] + ("--kv-bits", "4", "--kv-group-size", "64")
    assert "--kv-config" not in eight + four, "the per-layer recipe is not this pin"
    for value in runtimes.KV_QUANTS:
        assert RUNTIMES["optiq"].kv_quant_refusal(value) is None


def test_vmlx_passes_its_explicit_off_only_when_the_pin_is_off():
    """vMLX is the one runtime here with a real `off` flag: `--kv-cache-quantization none` is an
    accepted value and the production default (`vmlx_engine/cli.py:3864-3882`). It is passed for
    `off` alone -- an absent pin omits it, which is what keeps every recorded command
    byte-identical -- and a codec value never reaches the command, because the refusal is asked
    first."""
    off = RUNTIMES["vmlx"].start_command(ARTIFACT, HF_ID, kv_quant="off")

    assert off == TODAY["vmlx"] + ("--kv-cache-quantization", "none")
    assert "--kv-cache-quantization" not in TODAY["vmlx"]
    assert RUNTIMES["vmlx"].kv_quant_refusal("off") is None


def test_the_runtimes_with_no_way_to_reach_a_codec_refuse_it_rather_than_approximating():
    """Each refusal names what was read, because what would have to change is the runtime and
    not this run: mlx-lm's server has no surface for a codec at all, oMLX's codec is TurboQuant
    rather than affine, vMLX's codec is storage-only and inert under this harness's own
    `--disable-prefix-cache`, and Osaurus's affine route is inert under batched decode."""
    mlxlm = RUNTIMES["mlxlm"].kv_quant_refusal("affine8")
    assert "make_prompt_cache" in mlxlm and "server.py" in mlxlm

    omlx = RUNTIMES["omlx"].kv_quant_refusal("affine4")
    assert "TurboQuant" in omlx and "model_settings.json" in omlx

    vmlx = RUNTIMES["vmlx"].kv_quant_refusal("affine8")
    assert "scheduler.py:2444-2458" in vmlx and "--disable-prefix-cache" in vmlx

    osaurus = RUNTIMES["osaurus"].kv_quant_refusal("affine8")
    assert "batched decode" in osaurus and "TurboQuant" in osaurus

    for name in ("mlxlm", "omlx", "osaurus", "vmlx"):
        for value in ("affine8", "affine4"):
            reason = RUNTIMES[name].kv_quant_refusal(value)
            assert value in reason, f"{name} names the value it refused"
            assert "N/A" in reason, f"{name} says the cell is not measured"


def test_off_is_accepted_by_every_runtime_that_can_hold_it(monkeypatch):
    """`off` is the full-precision state, and on four of the five it is the state the runtime
    already delivers: mlx-lm and oMLX with no flag surface at all, OptiQ by omitting two flags,
    vMLX by its own explicit `none`. The fifth is read from the host rather than assumed."""
    host_live_kv_codec(monkeypatch, "engine_selected")

    for name in RUNTIMES:
        assert RUNTIMES[name].kv_quant_refusal("off") is None, name
        assert RUNTIMES[name].kv_quant_refusal(None) is None, name


def test_the_absent_kv_pin_is_never_refused_even_on_a_host_in_another_codec(monkeypatch):
    """The absent pin asks for no codec, so nothing can refuse it -- including the host whose
    live codec is not the default, which refuses the `off` *pin* rather than the absence of
    one."""
    host_live_kv_codec(monkeypatch, "turboquant")

    for runtime in RUNTIMES.values():
        assert runtime.kv_quant_refusal(None) is None
    for name in ("mlxlm", "omlx", "optiq", "vmlx"):
        assert RUNTIMES[name].kv_quant_refusal("off") is None, name


def test_osaurus_accepts_the_off_pin_only_while_the_host_is_at_its_default_codec(monkeypatch):
    """No flag exists in either direction, so `off` is host state this harness reads and does
    not edit -- the same shape as `cache.prefix.enabled`, read the same way, and refused with
    the setting named when the host disagrees. A restart is not a way to move it: the codec is
    host state rather than a property of a fresh process."""
    osaurus = RUNTIMES["osaurus"]

    host_live_kv_codec(monkeypatch, "engine_selected")
    assert osaurus.kv_quant_refusal("off") is None

    host_live_kv_codec(monkeypatch, "turboquant")
    refusal = osaurus.kv_quant_refusal("off")
    assert "cache.liveKVCodec" in refusal
    assert "turboquant" in refusal
    assert "restart" in refusal, "a restart is not a way to move a host codec"

    for sentinel in (osaurus_settings.UNREADABLE, osaurus_settings.MISSING):
        host_live_kv_codec(monkeypatch, sentinel)
        assert "cache.liveKVCodec" in osaurus.kv_quant_refusal("off")


# --------------------------------------------------------------------------------------
# The MTP-depth pin (study 03-06) and the expert-streaming pin (study 03-03)
# --------------------------------------------------------------------------------------
#
# One decode-side and one load-side, built the same way as the two cache pins and each with a
# second question: a depth is only MTP if the artifact on disk carries MTP heads the runtime
# will wire (`vmlx_mtp_refusal`), and `on` is only streaming if the server's own log says so
# (`Runtime.stream_experts_missing`). Both runtimes that accept the streaming flag fall back
# to a resident load silently, so neither flag is evidence of the state it names.


def test_the_mtp_depth_values_are_the_depths_and_vmlx_s_own_off():
    """`off` beside `1`/`2`/`3`, as strings: the set is one word and three numbers and the
    header value is compared exactly. They are a draft depth and not a count of tokens, and the
    ceiling is vMLX's own -- `--native-mtp-depth` must be 1..3 by default
    (cli.py:1668-1678, native_mtp.py:28-44)."""
    assert runtimes.MTP_DEPTHS == ("off", "1", "2", "3")
    assert runtimes.MTP_DEPTH_OFF == "off"
    assert "4" not in runtimes.MTP_DEPTHS
    assert "auto" not in runtimes.MTP_DEPTHS


def test_the_streaming_values_are_off_and_on_and_nothing_else():
    """`auto` is not one of them on purpose: it is OptiQ's own default (`--stream-experts`
    defaults to `None` -> `auto`, optiq/cli.py:2607-2615, :3095-3096) and the thing this pin
    exists to take away from the runtime."""
    assert runtimes.STREAM_EXPERTS == ("off", "on")
    assert "auto" not in runtimes.STREAM_EXPERTS


def test_no_pin_at_all_leaves_every_start_command_byte_identical_to_today():
    """Both new pins are absent here, and an absent pin is not a value: vMLX keeps
    `--disable-native-mtp` and gains nothing, OptiQ keeps `--no-stream-experts`, and the other
    three commands are the tuples recorded before either pin existed. Reading an absent
    streaming pin as `off` would have been invisible on OptiQ -- its `off` is the same flag --
    but reading an absent depth as `off` on vMLX would have claimed a state nobody asked for,
    and reading either as a value on the other four would have claimed a state they cannot
    hold."""
    assert set(TODAY) == set(RUNTIMES)
    for name, runtime in RUNTIMES.items():
        assert runtime.start_command(ARTIFACT, HF_ID) == TODAY[name]
        assert runtime.start_command(ARTIFACT, HF_ID, mtp_depth=None) == TODAY[name]
        assert runtime.start_command(ARTIFACT, HF_ID, stream_experts=None) == TODAY[name]
        assert runtime.start_command(
            ARTIFACT, HF_ID, mtp_depth=None, stream_experts=None
        ) == TODAY[name]
        # `off` is the same command on all five for the same reason the absent pin is: it is
        # either the runtime's own kill switch (vMLX), a default the command already holds
        # (OptiQ's `--mtp` is off unless passed), or a state the runtime is in because no flag
        # could take it out of one.
        assert runtime.start_command(ARTIFACT, HF_ID, mtp_depth="off") == TODAY[name]


def test_vmlx_drops_the_kill_switch_for_a_depth_and_pins_the_fixed_policy_with_it(tmp_path):
    """`--disable-native-mtp` is vMLX's own off and stays for `off` and the absent pin; a depth
    replaces it. The policy is not a second pin: vMLX's default is `adaptive`, which "may also
    lower the depth on measured acceptance and tries depth 1 once against the configured depth's
    measured cost" (cli.py:4324-4331) -- depth moving inside one request is not a cell at depth
    N, so `fixed` travels with every depth."""
    runtime = RUNTIMES["vmlx"]
    bundle = mtp_bundle(tmp_path)

    off = runtime.start_command(ARTIFACT, HF_ID, mtp_depth="off")
    assert off == TODAY["vmlx"]
    assert "--disable-native-mtp" in off

    for depth in ("1", "2", "3"):
        command = runtime.start_command(ARTIFACT, HF_ID, mtp_depth=depth)
        assert "--disable-native-mtp" not in command
        start = command.index("--native-mtp-depth")
        assert command[start : start + 4] == (
            "--native-mtp-depth",
            depth,
            "--native-mtp-depth-policy",
            "fixed",
        ), command
        assert runtime.mtp_depth_refusal(depth, bundle) is None, "vMLX drives every depth"


def test_optiq_adds_the_mtp_pair_for_a_depth_and_moves_nothing_else(tmp_path):
    """`--mtp` is `is_flag=True, default=False` and `--mtp-depth` defaults to `2`
    (optiq/cli.py:2554-2563), so `off` and the absent pin pass neither flag -- a command without
    the pair is OptiQ's own off rather than a stand-in for one -- and a depth is exactly the
    pair. No policy flag travels with it because there is no policy to pin: the cycle takes
    `cycle_K = depth` once and holds it for the whole request (optiq/runtime/engine.py:920)."""
    runtime = RUNTIMES["optiq"]
    bundle = optiq_bundle(tmp_path)

    assert "--mtp" not in TODAY["optiq"], "the recorded command is the MTP-free one"
    assert runtime.start_command(ARTIFACT, HF_ID, mtp_depth="off") == TODAY["optiq"]

    for depth in ("1", "2", "3"):
        command = runtime.start_command(ARTIFACT, HF_ID, mtp_depth=depth)
        start = command.index("--mtp")
        assert command[start : start + 3] == ("--mtp", "--mtp-depth", depth), command
        assert command.count("--mtp") == 1, "the pair appears once"
        # A depth changes this command and nothing else about it.
        assert command[:start] + command[start + 3 :] == TODAY["optiq"]
        assert runtime.mtp_depth_refusal(depth, bundle) is None, "OptiQ drives every depth"


def test_only_the_two_mtp_runtimes_have_a_depth_and_the_other_three_refuse_every_value():
    """Each refusal names its own evidence, because what would have to change is the runtime and
    not this run: mlx-lm's server has no MTP at all -- its model code drops the head's weights
    at load -- oMLX's MTP is a per-model settings field that is adaptive even when set, and
    Osaurus's depth is host state. Three of the five refuse every depth, so their ``off`` is a
    statement of fact -- Osaurus is the exception and is read from its host instead -- and the
    two that drive a depth (vMLX, OptiQ) decide it from the artifact rather than from the value,
    which is why their refusal is tested with a bundle and not here."""
    for name in ("mlxlm", "omlx", "osaurus"):
        runtime = RUNTIMES[name]
        assert runtime.mtp_depth_refusal(None, ARTIFACT) is None, name
        for depth in ("1", "2", "3"):
            reason = runtime.mtp_depth_refusal(depth, ARTIFACT)
            assert depth in reason, f"{name} names the value it refused"
            assert "N/A" in reason, f"{name} says the cell is not measured"

    for name in ("mlxlm", "optiq", "omlx"):
        assert RUNTIMES[name].mtp_depth_refusal("off", ARTIFACT) is None, name

    assert "0.31.3" in RUNTIMES["mlxlm"].mtp_depth_refusal("3", ARTIFACT)
    assert "model_settings.py" in RUNTIMES["omlx"].mtp_depth_refusal("3", ARTIFACT)
    assert "adaptive" in RUNTIMES["omlx"].mtp_depth_refusal("3", ARTIFACT)
    assert "mtp.explicitDepth" in RUNTIMES["osaurus"].mtp_depth_refusal("3", ARTIFACT)


def test_osaurus_accepts_the_off_depth_only_while_the_host_forces_mtp_off(monkeypatch):
    """`mtp.mode` is a tracked key, so the drift gate already attests it -- but it is not `off`
    at `auto`, under which Osaurus runs a draft head on any bundle that carries one
    (docs/runtimes/osaurus.md:307, :900-901). A cell labelled MTP-free has to be MTP-free."""
    osaurus = RUNTIMES["osaurus"]

    host_mtp_mode(monkeypatch, "force_off")
    assert osaurus.mtp_depth_refusal("off", ARTIFACT) is None

    host_mtp_mode(monkeypatch, "auto")
    refusal = osaurus.mtp_depth_refusal("off", ARTIFACT)
    assert "mtp.mode" in refusal and "auto" in refusal
    assert "restart" in refusal, "a restart is not a way to make a cell MTP-free"

    for sentinel in (osaurus_settings.UNREADABLE, osaurus_settings.MISSING):
        host_mtp_mode(monkeypatch, sentinel)
        assert "mtp.mode" in osaurus.mtp_depth_refusal("off", ARTIFACT)


def test_optiq_drives_both_streaming_states_and_neither_claims_to_be_a_default():
    """`off` is OptiQ's own `--no-stream-experts` -- a complete opt-out, not a partial one
    (`mode == "off"` returns before anything is installed, optiq/serve.py:1629-1630) -- and it
    is passed explicitly because the flag's default is `auto`. `on` is `--stream-experts`, and
    exactly one of the two is ever in the command."""
    runtime = RUNTIMES["optiq"]

    off = runtime.start_command(ARTIFACT, HF_ID, stream_experts="off")
    on = runtime.start_command(ARTIFACT, HF_ID, stream_experts="on")

    assert off == TODAY["optiq"]
    expected_on = tuple(
        "--stream-experts" if part == "--no-stream-experts" else part for part in TODAY["optiq"]
    )
    assert on == expected_on
    assert "--no-stream-experts" in off and "--stream-experts" not in off
    assert "--stream-experts" in on and "--no-stream-experts" not in on
    assert runtime.stream_experts_refusal("off") is None
    assert runtime.stream_experts_refusal("on") is None


def test_vmlx_drives_both_streaming_states_through_its_own_opt_in_flag():
    """`--flash-moe` is `default=False` (vmlx_engine/cli.py:3966) and `FlashMoEConfig.enabled:
    bool = False` -- "Default False (opt-in)" (flash_moe_config.py:29) -- so `off` adds nothing
    and `on` is the flag."""
    runtime = RUNTIMES["vmlx"]

    assert runtime.start_command(ARTIFACT, HF_ID, stream_experts="off") == TODAY["vmlx"]
    on = runtime.start_command(ARTIFACT, HF_ID, stream_experts="on")
    assert on == TODAY["vmlx"] + ("--flash-moe",)
    assert "--smelt" not in on, "--flash-moe and --smelt are mutually exclusive (cli.py:2565)"
    assert runtime.stream_experts_refusal("off") is None
    assert runtime.stream_experts_refusal("on") is None


def test_the_runtimes_with_no_streaming_surface_refuse_on_and_accept_off():
    """mlx-lm has no expert-loading path at all, oMLX's nearest mechanism is burst decode --
    which sets how many decode steps are coalesced before a delta is emitted, not where expert
    weights live (docs/runtimes/omlx.md:798-841) -- and Osaurus's is host state with no start
    flag in either direction."""
    for name in ("mlxlm", "optiq", "omlx", "vmlx"):
        assert RUNTIMES[name].stream_experts_refusal(None) is None, name
        assert RUNTIMES[name].stream_experts_refusal("off") is None, name

    for name in ("mlxlm", "omlx"):
        reason = RUNTIMES[name].stream_experts_refusal("on")
        assert "on" in reason and "N/A" in reason

    assert "expert" in RUNTIMES["mlxlm"].stream_experts_refusal("on")
    assert "burst decode" in RUNTIMES["omlx"].stream_experts_refusal("on")
    assert "smeltMode" in RUNTIMES["osaurus"].stream_experts_refusal("on")


def test_osaurus_accepts_the_off_streaming_state_only_where_the_host_is_not_streaming(
    monkeypatch,
):
    """`concurrency.smeltMode` is the one place Osaurus's expert behaviour is decided, its enum
    is `engineSelected | disabled | flashMoE | ssdStreaming` (docs/runtimes/osaurus.md:298), and
    it is host state -- not one of `TRACKED_KEYS`, so it is read directly. `disabled` is the
    only value under which nothing about experts is being changed underneath the cell."""
    osaurus = RUNTIMES["osaurus"]

    host_smelt_mode(monkeypatch, "disabled")
    assert osaurus.stream_experts_refusal("off") is None

    for live in ("engineSelected", "flashMoE", "ssdStreaming"):
        host_smelt_mode(monkeypatch, live)
        refusal = osaurus.stream_experts_refusal("off")
        assert "concurrency.smeltMode" in refusal
        assert live in refusal, "the refusal names the value that disagreed"

    for sentinel in (osaurus_settings.UNREADABLE, osaurus_settings.MISSING):
        host_smelt_mode(monkeypatch, sentinel)
        assert "concurrency.smeltMode" in osaurus.stream_experts_refusal("off")


# --- the artifact half of the depth pin -------------------------------------------------


def mtp_bundle(tmp_path, *, family="qwen3_5", layers=1, keys=("mtp.layers.0.mlp.down_proj.weight",),
               config_extra=None, jang=None, name="bundle"):
    """A directory shaped like the files vMLX reads: config.json and a safetensors index."""
    root = tmp_path / name
    root.mkdir()
    config = {"model_type": family, "num_nextn_predict_layers": layers}
    config.update(config_extra or {})
    (root / "config.json").write_text(json.dumps(config))
    if keys is not None:
        (root / "model.safetensors.index.json").write_text(
            json.dumps({"weight_map": {key: "model.safetensors" for key in keys}})
        )
    if jang is not None:
        (root / "jang_config.json").write_text(json.dumps(jang))
    return str(root)


def test_a_bundle_with_mtp_heads_the_runtime_wires_accepts_a_depth(tmp_path):
    """The one case a depth cell is honest: MTP tensors on disk, a config that declares the
    layers, a family vMLX wires a draft/verify path for (native_mtp.py:64-79), and nothing
    saying the bundle dropped them."""
    bundle = mtp_bundle(tmp_path)

    assert runtimes.vmlx_mtp_refusal(bundle) is None
    assert RUNTIMES["vmlx"].mtp_depth_refusal("3", bundle) is None


def test_a_bundle_with_no_mtp_tensors_refuses_a_depth(tmp_path):
    """vMLX accepts `--native-mtp-depth` on a bundle with no MTP heads and decodes plain
    autoregressive without saying so -- its banner is suppressed entirely for a
    `not_configured` bundle (cli.py:2441) -- so the depth cell is refused up front, from the
    artifact, with the check that failed named."""
    bundle = mtp_bundle(tmp_path, keys=("model.layers.0.mlp.down_proj.weight",))

    reason = runtimes.vmlx_mtp_refusal(bundle)

    assert "no mtp.* tensors" in reason
    assert "autoregressive" in reason
    assert RUNTIMES["vmlx"].mtp_depth_refusal("1", bundle) == reason


def test_a_bundle_whose_config_declares_no_mtp_layer_refuses_a_depth(tmp_path):
    """Both halves of the declaration are required. An index full of MTP tensors under a config
    that asks for no MTP layer is `metadata_inconsistent` to vMLX (`native_mtp.py:987-988`) and
    its decode carries no draft head -- so tensors alone must not pass this check. The reverse
    -- a config that asks for MTP over an index with none -- is the other `issues` line at
    `:983-986`, covered by the tensors test beside this one."""
    bundle = mtp_bundle(tmp_path, layers=None)

    reason = runtimes.vmlx_mtp_refusal(bundle)

    assert "declares no MTP layer" in reason or "metadata_inconsistent" in reason


def test_a_bundle_that_drops_its_mtp_refuses_a_depth(tmp_path):
    """`jang_config.drop_mtp`, the sidecar's own `enabled`/`kept`, the stamped `mtp_mode` and
    `runtime.bundle_has_mtp` are the four routes `native_mtp_status` reads as dropped
    (native_mtp.py:883-925)."""
    for index, jang in enumerate(
        (
            {"drop_mtp": True},
            {"mtp": {"enabled": False}},
            {"mtp": {"kept": False}},
            {"mtp": {"mtp_mode": "absent"}},
            {"runtime": {"bundle_has_mtp": False}},
        )
    ):
        bundle = mtp_bundle(tmp_path, jang=jang, name=f"bundle-dropped-{index}")
        reason = runtimes.vmlx_mtp_refusal(bundle)
        assert "dropped" in reason, jang


def test_a_bundle_in_a_family_vmlx_does_not_wire_refuses_a_depth(tmp_path):
    """An artifact can carry MTP heads in a family outside vMLX's support map, and its own
    status for one is `weights_present_runtime_unwired` (native_mtp.py:1110-1117) -- the
    decode would run without a draft head however the flag is spelled."""
    bundle = mtp_bundle(tmp_path, family="gemma4")

    reason = runtimes.vmlx_mtp_refusal(bundle)

    assert "gemma4" in reason
    assert "weights_present_runtime_unwired" in reason


def test_the_family_aliases_vmlx_normalises_are_read_the_same_way_here(tmp_path):
    """`qwen3_6` is `qwen3_5` to vMLX (native_mtp.py:49-55), and a family stated only under
    `text_config` counts -- a bundle refused for its spelling would be a false refusal."""
    for family in ("qwen3_6", "qwen3_5_text", "qwen3_5_moe"):
        bundle = mtp_bundle(tmp_path, family=family, name=f"bundle-{family}")
        assert runtimes.vmlx_mtp_refusal(bundle) is None, family

    nested = mtp_bundle(tmp_path, family="text_only", name="bundle-nested")
    config = json.loads((Path(nested) / "config.json").read_text())
    # `_bundle_family` reads the config's own model_type first, so the fallback to text_config
    # is only reached on a config that does not state one at all.
    config.pop("model_type")
    config["text_config"] = {"model_type": "qwen3_5_text"}
    (Path(nested) / "config.json").write_text(json.dumps(config))
    assert runtimes.vmlx_mtp_refusal(nested) is None


def test_an_artifact_that_cannot_be_enumerated_refuses_a_depth_rather_than_assuming(tmp_path):
    """No index means the tensors cannot be enumerated without a dependency this harness does
    not carry, and a depth the artifact cannot be shown to support is not one to publish."""
    bundle = mtp_bundle(tmp_path, keys=None)

    assert "model.safetensors.index.json" in runtimes.vmlx_mtp_refusal(bundle)

    missing = str(tmp_path / "nothing-here")
    assert "config.json" in runtimes.vmlx_mtp_refusal(missing)


# --- the artifact half of the depth pin, on OptiQ -----------------------------------------


def optiq_bundle(tmp_path, *, layers=1, head="optiq/mtp.safetensors", named=None,
                 config_extra=None, name="optiq-bundle"):
    """A directory shaped like an OptiQ quant: a config that declares an MTP layer, and the head
    sidecar where OptiQ's own resolver looks for one."""
    root = tmp_path / name
    root.mkdir()
    config = {"model_type": "qwen3_5"}
    if layers is not None:
        config["text_config"] = {"mtp_num_hidden_layers": layers}
    if named is not None:
        config["mlx_lm_extra_tensors"] = {"mtp_file": named}
    config.update(config_extra or {})
    (root / "config.json").write_text(json.dumps(config))
    if head is not None:
        sidecar = root / head
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        sidecar.write_bytes(b"")
    return str(root)


def test_an_artifact_with_the_sidecar_and_the_layer_accepts_a_depth(tmp_path):
    """The one case a depth cell is honest on OptiQ: the head is where its resolver looks and
    the config declares the layer it would build the head against (mtp/artifacts.py:104-115,
    mtp_patch.py:69-76). Both of the OptiQ quants on this host look exactly like this, with
    `optiq/mtp.safetensors` named in `mlx_lm_extra_tensors.mtp_file`."""
    bundle = optiq_bundle(tmp_path)

    assert runtimes.optiq_mtp_refusal(bundle) is None
    assert RUNTIMES["optiq"].mtp_depth_refusal("3", bundle) is None


def test_an_artifact_with_no_head_where_optiq_looks_refuses_a_depth(tmp_path):
    """`--mtp` is accepted on an artifact with no head, and the failure is loud but late: the
    engine is built on the first request, warns that it attached without one, and answers HTTP
    404 (serve.py:459-464, engine.py:297-304, mlx_lm/server.py:1424-1427). Read here instead, the
    cell costs no model load and says which paths were looked in."""
    bundle = optiq_bundle(tmp_path, head=None)

    reason = runtimes.optiq_mtp_refusal(bundle)

    assert "optiq/mtp.safetensors" in reason, "the paths looked in are named"
    assert "HTTP 404" in reason
    assert RUNTIMES["optiq"].mtp_depth_refusal("1", bundle) == reason


def test_the_config_s_own_answer_wins_and_the_four_spellings_are_the_fallback(tmp_path):
    """`expected_mtp_file` returns the path the config names, and only tries the four spellings
    when it names none (mtp/artifacts.py:104-115). So a config naming a file that is not there is
    a refusal even with a sidecar at the root -- the runtime would not read it either, it would
    fall through to the embedded route -- and the legacy root spelling is a legal artifact."""
    named = optiq_bundle(tmp_path, head=None, named="optiq/mtp.safetensors", name="named-missing")
    assert "optiq/mtp.safetensors" in runtimes.optiq_mtp_refusal(named)

    legacy = optiq_bundle(tmp_path, head="mtp.safetensors", name="legacy-root")
    assert runtimes.optiq_mtp_refusal(legacy) is None


def test_an_artifact_whose_config_declares_no_mtp_layer_refuses_a_depth(tmp_path):
    """Both halves are required. OptiQ's injector returns before it looks for a head when the
    config's layer count is zero (mtp_patch.py:382-385), so a sidecar on disk under a config
    that asks for no MTP layer is a cell whose decode would never draft."""
    bundle = optiq_bundle(tmp_path, layers=None)

    reason = runtimes.optiq_mtp_refusal(bundle)

    assert "mtp_num_hidden_layers" in reason
    assert "no config.json" not in reason
    assert RUNTIMES["optiq"].mtp_depth_refusal("2", bundle) == reason

    missing = str(tmp_path / "nothing-here")
    assert "config.json" in runtimes.optiq_mtp_refusal(missing)


# --- the log half of the streaming pin ---------------------------------------------------


def write_log(tmp_path, text, name="runtime.log"):
    path = tmp_path / name
    path.write_text(text)
    return str(path)


def test_optiq_requires_both_of_its_own_lines_before_an_on_cell_is_believed(tmp_path):
    """The mode banner alone is printed before the model is even inspected, so on a model it
    cannot stream it appears and nothing streams (optiq/cli.py:3095-3101, serve.py:1641-1643);
    the pre-load line is the one that says the model was built through `load_streaming`
    (serve.py:1654-1662). Both are required."""
    runtime = RUNTIMES["optiq"]
    banner = "[optiq.serve] SSD expert streaming: on\n"
    # Verbatim from results/logs/optiq-20260920T023332-73621.log, a probe run that really
    # streamed: the mode line, then the pre-load line naming the model.
    preloaded = (
        "[optiq.serve] SSD expert streaming: pre-loaded /Users/jrazz/.cache/huggingface/hub/"
        "models--mlx-community--Qwen3.6-35B-A3B-4bit/snapshots/38740b847e4cb78f352aba30aa"
        "41c76e08e6eb46\n"
    )

    assert runtime.stream_experts_missing(None, None) is None
    assert runtime.stream_experts_missing("off", None) is None

    both = write_log(tmp_path, banner + preloaded)
    assert runtime.stream_experts_missing("on", both) is None

    only_banner = write_log(tmp_path, banner, name="banner-only.log")
    reason = runtime.stream_experts_missing("on", only_banner)
    assert "pre-loaded" in reason
    assert only_banner in reason, "the log path is named"

    failed = write_log(
        tmp_path,
        banner + "  [optiq.serve] expert streaming failed (no index); falling back to resident "
        "load\n",
        name="failed.log",
    )
    reason = runtime.stream_experts_missing("on", failed)
    assert "expert streaming failed" in reason, "the fallback line is quoted"
    assert "falling back to resident load" in reason


def test_vmlx_requires_the_line_that_says_the_layers_were_patched(tmp_path):
    """Every other outcome logs something else: no MoE layers (server.py:8981-8982), a JANGTQ
    bundle refused by name (server.py:8964-8973), nothing patched (server.py:9003-9005), or a
    setup that raised (server.py:9006-9008)."""
    runtime = RUNTIMES["vmlx"]

    # Verbatim from results/logs/vmlx-20260920T023513-73621.log, a probe run that really did
    # stream 40 MoE layers: the success line, with the two lines above it that are *not* the
    # evidence (`Flash MoE: patched ...`, `Flash MoE: freed ...`).
    good = write_log(
        tmp_path,
        "INFO:vmlx_engine.models.flash_moe_integration:Flash MoE: patched 40 MoE layers\n"
        "INFO:vmlx_engine.models.flash_moe_integration:Flash MoE: freed ~18.12 GB expert "
        "weights\n"
        "INFO:vmlx_engine.server:Flash MoE enabled: 40 layers patched, 18.12 GB freed, "
        "slot bank=64, io_workers=4\n",
    )
    assert runtime.stream_experts_missing("on", good) is None

    no_layers = write_log(
        tmp_path,
        "INFO:vmlx_engine.server:Flash MoE: model has no MoE layers, skipping\n",
        name="no-layers.log",
    )
    reason = runtime.stream_experts_missing("on", no_layers)
    assert "Flash MoE enabled:" in reason, "the line that was required is named"
    assert "model has no MoE layers, skipping" in reason, "the log line is quoted"


def test_optiq_requires_the_engine_s_own_ready_line_at_the_depth_that_was_pinned(tmp_path):
    """`--mtp --mtp-depth N` is echoed at startup, but the engine that line names is built on the
    first request (serve.py:443-471), so the echo is not evidence and the check reads the line
    printed once the engine exists -- `[optiq.serve] MTP engine ready (depth=N).` (serve.py:465).
    The depth is interpolated into that line, so a cell at 3 whose engine says 2 is a FAIL."""
    runtime = RUNTIMES["optiq"]

    assert runtime.mtp_depth_missing(None, None) is None
    assert runtime.mtp_depth_missing("off", None) is None

    startup_echo = write_log(
        tmp_path,
        "[optiq.serve] MTP speculation enabled (depth=3, model=/models/qwen3.5-4b)\n"
        "[optiq.serve] server is starting at http://127.0.0.1:8080\n",
        name="echo-only.log",
    )
    reason = runtime.mtp_depth_missing("3", startup_echo)
    assert "MTP engine ready (depth=3)." in reason, "the line that was required is named"
    assert startup_echo in reason, "the log path is named"

    ready = write_log(
        tmp_path,
        "[optiq.serve] MTP speculation enabled (depth=3, model=/models/qwen3.5-4b)\n"
        "[optiq.serve] attaching MTP engine to loaded model (/models/qwen3.5-4b)...\n"
        "[optiq.serve] MTP engine ready (depth=3).\n",
    )
    assert runtime.mtp_depth_missing("3", ready) is None

    reason = runtime.mtp_depth_missing("2", ready)
    assert "MTP engine ready (depth=2)." in reason, "the depth is part of the evidence"

    # The engine's own account of attaching without a draft head is quoted when it is there.
    fell_back = write_log(
        tmp_path,
        "[optiq.serve] MTP speculation enabled (depth=3, model=/models/x)\n"
        "WARNING:optiq.runtime.engine:MTP head not attached (MTP injection failed for /models/x); "
        "continuing without MTP\n",
        name="no-head.log",
    )
    reason = runtime.mtp_depth_missing("3", fell_back)
    assert "MTP head not attached" in reason, "the fallback line is quoted"
    assert "continuing without MTP" in reason


def test_a_handle_with_no_log_path_is_a_failure_to_verify_rather_than_a_pass():
    """The evidence is a file, and a start that left no file cannot be checked -- which is a
    FAIL with that reason, not a silent pass. Nothing in production reaches it: every handle a
    real spawn returns carries the path its output went to."""
    for name in ("optiq", "vmlx"):
        reason = RUNTIMES[name].stream_experts_missing("on", None)
        assert "log path" in reason
        assert "FAIL" in reason

    # The depth pin's log half reads the same window and fails the same way.
    reason = RUNTIMES["optiq"].mtp_depth_missing("3", None)
    assert "log path" in reason
    assert "FAIL" in reason


def test_the_log_window_the_evidence_reads_is_the_head_not_the_tail(tmp_path):
    """A banner scrolls out of a tail and a failure line scrolls out of a head, so the two
    windows are not interchangeable: across the 781 recorded logs the lines this check reads sit
    in the first 8,088 bytes, while the largest log is 3,552,989 bytes. A log longer than the
    window keeps its head."""
    runtime = RUNTIMES["vmlx"]
    banner = "INFO:vmlx_engine.server:Flash MoE enabled: 4 layers patched, 1.00 GB freed\n"
    padding = "INFO:vmlx_engine.server:request handled\n" * 200_000
    long_log = write_log(tmp_path, banner + padding, name="long.log")

    assert len(padding) > runtimes.LOG_HEAD_BYTES
    assert runtime.stream_experts_missing("on", long_log) is None


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
