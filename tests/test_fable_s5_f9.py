"""S5-F9: two host settings that change what an Osaurus cell measures are outside the
attestation -- the app plist's per-model ``disableThinking``, and ``concurrency.smeltMode`` on
any cell with no ``stream_experts`` pin.

Both are host state that isn't in a start command, so the only things that could name them are
the drift gate (``osaurus_settings.TRACKED_KEYS``, read by ``Osaurus.check_host_state``) or the
row itself. The claim is that neither does:

(a) ``~/Library/Preferences/com.dinoki.osaurus.plist`` -> ``model_options_<modelID>`` ->
    ``disableThinking`` decides whether a model emits reasoning tokens at all
    (docs/runtimes/osaurus.md:498-528, repeated at :876-880 and :1234-1235). Flipping it changes
    TTFT -- reasoning is not content -- ``completion_tokens``, and which channel Decision 119
    times, with the drift gate green. AGENTS.md:92 names "an app plist" as something the
    harness must snapshot and diff against a baseline before every run.

(b) ``concurrency.smeltMode`` (``engineSelected | disabled | flashMoE | ssdStreaming``) decides
    how many experts are resident -- Osaurus's twin of OptiQ's ``--stream-experts auto``
    (AGENTS.md:90). It is read only inside ``Osaurus.stream_experts_refusal``, which returns at
    ``if stream_experts is None: return None`` (runtimes.py:2642-2643) before reading it, and it
    is not a tracked key, so a cell with no ``stream_experts`` pin -- which is what every grid
    script except ``run_sweep_streaming.sh`` runs -- is measured and published with nothing
    gating or recording it.

The two ``RED``-marked tests below assert what a working attestation would do; they fail on the
code as reviewed. The rest are characterisations that pass *because* the defect is present, and
they exist so the mechanism is pinned down rather than merely asserted.

No server, no engine, no app. Every assertion is over scratch files and the shipped modules.
"""

from __future__ import annotations

import json
import plistlib

import pytest

from ohyesmlx import osaurus_settings, runtimes
from ohyesmlx.measure import CellResult, write_jsonl

MODEL_ID = "OsaurusAI/Qwen3.6-35B-A3B-MXFP4-MTP"

CONFIG = {
    "server-runtime.json": {
        "cache": {"blockDisk": {"enabled": False}, "prefix": {"enabled": False}},
        "concurrency": {
            "continuousBatching": True,
            "maxConcurrentSequences": 1,
            "smeltMode": "disabled",
        },
    },
    "server.json": {"numberOfThreads": 8},
}


def write_config(root, *, smelt_mode="disabled"):
    """The two config files ``osusaurus_settings`` attests, at a scratch location."""
    root.mkdir(parents=True, exist_ok=True)
    document = json.loads(json.dumps(CONFIG))
    document["server-runtime.json"]["concurrency"]["smeltMode"] = smelt_mode
    for name, payload in document.items():
        (root / name).write_text(json.dumps(payload))
    return root


def write_plist(path, *, disable_thinking, model_id=MODEL_ID):
    """The shape this host writes: ``model_options_<modelID>`` holding a JSON ``bytes`` blob."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        plistlib.dumps(
            {
                f"model_options_{model_id}": json.dumps(
                    {
                        "options": {"disableThinking": {"bool": {"_0": disable_thinking}}},
                        "version": 1,
                    }
                ).encode()
            }
        )
    )
    return path


# ======================================================================================
# (b) smeltMode
# ======================================================================================


def test_RED_the_capture_attests_concurrency_smelt_mode(tmp_path):
    """RED. The finding's own test idea.

    ``capture_osaurus_settings`` is what both the drift gate and ``quickbench``'s check read;
    whatever it does not hold can neither be attested nor compared. A host at ``ssdStreaming``
    -- Osaurus's twin of OptiQ's ``--stream-experts auto``, which AGENTS.md:90 requires be
    pinned explicitly -- must appear in the capture.
    """
    root = write_config(tmp_path / "config", smelt_mode="ssdStreaming")

    captured = osaurus_settings.capture_osaurus_settings(root)

    assert "server-runtime.json:concurrency.smeltMode" in captured, (
        "smeltMode decides how many experts are resident and the capture holds no key for it, "
        f"so the drift gate cannot refuse a host whose expert behaviour changed: {sorted(captured)}"
    )
    assert captured["server-runtime.json:concurrency.smeltMode"] == "ssdStreaming"


def test_the_gate_reports_disabled_to_ssd_streaming_drift(tmp_path):
    """A baseline at ``disabled`` reports drift on ``ssdStreaming``."""
    root = write_config(tmp_path / "config", smelt_mode="disabled")
    baseline = osaurus_settings.capture_osaurus_settings(root)

    write_config(root, smelt_mode="ssdStreaming")
    live = osaurus_settings.capture_osaurus_settings(root)

    drift = osaurus_settings.diff_against_baseline(live, baseline)

    assert any("smeltMode" in str(change) for change in drift)
    assert baseline["server-runtime.json:concurrency.smeltMode"] == "disabled"


def test_an_unpinned_osaurus_cell_never_asks_the_host_its_expert_mode(monkeypatch):
    """``stream_experts_refusal(None)`` returns before the host is read.

    A cell started with no ``--stream-experts`` is the ordinary case: every grid runner below
    leaves the pin out. Such a cell's expert behaviour is neither gated nor recorded.
    """
    asked: list[str] = []
    monkeypatch.setattr(
        runtimes, "osaurus_smelt_mode", lambda: asked.append("read") or "ssdStreaming"
    )
    osaurus = runtimes.RUNTIMES["osaurus"]

    assert osaurus.stream_experts_refusal(None) is None
    assert asked == [], (
        "the None early return means an ssdStreaming host measures and publishes the cell with "
        "nothing asking what the expert mode is"
    )

    assert osaurus.stream_experts_refusal("off") is not None, (
        "control: the same host does refuse an explicit `off` pin, so the reader works and the "
        "absence above is the early return, not a dead code path"
    )
    assert asked == ["read"], "control: the explicit pin is what reads the host"


def test_the_grid_runners_leave_the_pin_out():
    """The default path is the ordinary one, so ``None`` is what most Osaurus rows carry."""
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    for name in ("run_grid.sh", "run_grid_35b.sh", "run_grid_moe.sh"):
        text = (repo / "scripts" / name).read_text()
        assert "osaurus" in text, f"{name} is expected to run an Osaurus column"
        assert "--stream-experts" not in text, (
            f"{name} pins no expert-streaming state, so its Osaurus cells take the None path"
        )
    assert "--stream-experts" in (
        repo / "scripts" / "run_sweep_streaming.sh"
    ).read_text(), "control: the one script whose subject is this pin does name it"


def test_smelt_mode_is_tracked_with_the_other_concurrency_settings():
    """The expert-residency setting is part of the attested concurrency surface."""
    tracked = {(name, dotted) for name, dotted in osaurus_settings.TRACKED_KEYS}
    assert ("server-runtime.json", "concurrency.continuousBatching") in tracked
    assert ("server-runtime.json", "concurrency.maxConcurrentSequences") in tracked
    assert ("server-runtime.json", "concurrency.smeltMode") in tracked


# ======================================================================================
# (a) the app plist's per-model disableThinking
# ======================================================================================


@pytest.mark.xfail(
    strict=True, reason="S5-F9 plist disableThinking: deferred to Jason at 05-07 UNIFY"
)
def test_RED_the_gate_refuses_a_host_whose_per_model_thinking_switch_differs(tmp_path, monkeypatch):
    """RED. Two hosts identical in every attested file, differing only in the plist.

    ``disableThinking`` decides whether the measured model emits reasoning tokens at all. Two
    rows that differ only in this switch differ by the entire reasoning run: TTFT (reasoning is
    not content), ``completion_tokens``, and the channel Decision 119 times. AGENTS.md:92 says
    to snapshot and diff the app plist before every run; the gate must therefore refuse, and
    today it does not.

    The product path is driven with paths patched rather than functions replaced, so the
    refusal is ``check_host_state``'s own.
    """
    root = write_config(tmp_path / "config")
    monkeypatch.setattr(osaurus_settings, "DEFAULT_CONFIG_DIR", root)

    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "settings": osaurus_settings.capture_osaurus_settings(root),
                # What a fix would add: the per-model options for the cell's model.
                "model_options": {MODEL_ID: {"disableThinking": False}},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    monkeypatch.setattr(osaurus_settings, "BASELINE_PATH", baseline_path)

    write_plist(tmp_path / "host.plist", disable_thinking=True)

    with pytest.raises(runtimes.RuntimeStartError):
        runtimes.RUNTIMES["osaurus"].check_host_state()


def test_the_two_json_captures_are_identical_across_a_flipped_thinking_switch(tmp_path):
    """Characterisation of the gap: the switch moves nothing the capture holds.

    A real plist, decoded with the stdlib, holding this host's own shape for a model it has
    ``disableThinking`` on. The capture of a host configured identically except for that switch
    is byte-identical, so no gate, no baseline and no row can distinguish the two.
    """
    root = write_config(tmp_path / "config")
    thinking_on = write_plist(tmp_path / "on.plist", disable_thinking=False)
    thinking_off = write_plist(tmp_path / "off.plist", disable_thinking=True)

    for path, expected in ((thinking_on, False), (thinking_off, True)):
        blob = json.loads(plistlib.loads(path.read_bytes())[f"model_options_{MODEL_ID}"])
        assert blob["options"]["disableThinking"]["bool"]["_0"] is expected

    captured = osaurus_settings.capture_osaurus_settings(root)

    assert not any("disableThinking" in key for key in captured)
    assert not any(MODEL_ID in key for key in captured), (
        "no captured key names the model, so a per-model switch has nothing to attach to"
    )


def test_no_osaurus_module_reads_the_app_plist():
    """AGENTS.md:92's "and an app plist" has no code behind it anywhere in the package."""
    import inspect

    from ohyesmlx import osaurus_settings as module

    source = inspect.getsource(module)
    assert "com.dinoki.osaurus" not in source
    assert "Library/Preferences" not in source

    tracked_files = {name for name, _dotted in module.TRACKED_KEYS}
    assert tracked_files == {"server-runtime.json", "server.json"}
    assert not any("plist" in name for name in tracked_files)


def test_a_row_carries_no_host_setting_and_no_thinking_state(tmp_path):
    """The other half of "nothing in the artifact names why": the row.

    Written through the real writer, so the field list is the record's own.
    """
    from ohyesmlx import measure

    cell = measure.Cell(
        id="osaurus__stub",
        runtime="osaurus",
        artifact_dir=str(tmp_path / "artifact"),
        label="stub",
    )
    result = CellResult(
        cell=cell,
        workload_id="w1",
        status="PASS",
        reason=None,
        observations=[],
        batch_spans=[],
        warmup_observations=[],
        warmup_plateau=True,
        cold_load_s=1.0,
        first_request_s=None,
        first_request_workload_id=None,
        memory={},
        runtime_version="0.25.18",
        disk_bytes=1,
        request_seed=None,
    )
    path = tmp_path / "results.jsonl"
    write_jsonl([result], path, run={"temperature": 0.0})
    header, row = [json.loads(line) for line in path.read_text().splitlines()]

    for document in (row, header):
        text = json.dumps(document)
        for needle in ("smeltMode", "disableThinking", "plist", "model_options_"):
            assert needle not in text, f"the record carries {needle!r}"


if __name__ == "__main__":  # pragma: no cover - a runnable check without pytest
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as temporary:
        root = write_config(Path(temporary) / "config", smelt_mode="ssdStreaming")
        captured = osaurus_settings.capture_osaurus_settings(root)
        present = "server-runtime.json:concurrency.smeltMode" in captured
        print(f"smeltMode in the capture: {present}  (claim is False)")
        print(
            "a default cell asks the host: "
            f"{runtimes.RUNTIMES['osaurus'].stream_experts_refusal(None) is not None}"
        )
