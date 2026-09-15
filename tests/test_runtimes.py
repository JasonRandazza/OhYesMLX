"""Checks for ohyesmlx.runtimes.

No model server is started here. Every runtime is exercised through fakes for the seams
this module reaches outside itself with -- spawn, inventory, signals, clock -- plus checks
that run the real binaries those rules rest on: `/usr/sbin/lsof` against a real listening
socket, because the port-free rule is the one thing a fake cannot be trusted to prove, and
`sed` against a module shaped like the one vMLX ships.

The load-failure text below is captured verbatim from mlx-lm 0.31.3 on this host; see
docs/research/2026-09-14-oq-portability-spike.md.
"""

from __future__ import annotations

import ast
import json
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

ARTIFACT = "/Users/jrazz/.cache/huggingface/hub/mlx-community/gemma-4-12B-it-qat-OptiQ-4bit"
HF_ID = "mlx-community/gemma-4-12B-it-qat-OptiQ-4bit"


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=(), returncode=returncode, stdout=stdout, stderr=stderr
    )


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
        self.commands = []
        self.ran = []
        self.results = {}
        self.inventory_calls = 0
        self.api_keys = []
        self.spawn_seconds = 0.0
        self.spawn_alive = True
        self.term_kills = True
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


# --------------------------------------------------------------------------------------
# The pinned interface
# --------------------------------------------------------------------------------------


def test_handle_carries_the_six_pinned_fields_in_order():
    names = [field for field in Handle.__dataclass_fields__][:6]
    assert names == [
        "pid",
        "port",
        "base_url",
        "model_id",
        "version",
        "cold_load_s",
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
        "8192",
        "--max-concurrent",
        "1",
        "--idle-timeout",
        "0",
        "--context-scale",
        "1.0",
        "--no-stream-experts",
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


def test_start_reports_the_servers_error_and_still_frees_the_port(rig):
    rig.log = "Traceback (most recent call last):\nOSError: disk full\n"
    # Free at the ownership probe, then lingering while the killed server lets go.
    rig.busy_from[8081] = 1
    rig.free_after[8081] = 3

    with pytest.raises(RuntimeStartError):
        RUNTIMES["mlxlm"].start(ARTIFACT, HF_ID)

    assert rig.signals and rig.signals[0][1] == signal.SIGTERM
    assert rig.free_after[8081] == 0


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

    assert rig.ran[0] == ("osaurus", "stop")


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

    assert rig.ran == []
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


def test_osaurus_starts_when_no_baseline_has_been_recorded(rig, monkeypatch):
    monkeypatch.setattr(runtimes, "load_baseline", lambda: None)
    rig.inventory = ("ornith-1.0-35b-jang_4m",)

    handle = RUNTIMES["osaurus"].start(ARTIFACT, "ornith-1.0-35b-jang_4m")

    assert handle.model_id == "ornith-1.0-35b-jang_4m"
    assert handle.version.startswith("unknown:")


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
