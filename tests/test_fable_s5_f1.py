"""S5-F1: `_engine_env` prefixes *every* engine's lab bin to PATH, not the one being started.

The claim: this Mac's lab-paths.json names only OptiQ's lab bin, so every spawn and every
helper run -- including the mlx-lm control cell's `python -m mlx_lm.server` and its
`python -m mlx_lm --version` -- gets `PATH = <optiq lab bin>:<ambient>`. `python` therefore
resolves inside OptiQ's venv, which carries mlx-lm 0.31.3 on mlx 0.32.4, while the control
venv AGENTS.md names (`~/.local/share/ohyesmlx/mlx-lm-0.31.3/bin`) carries mlx 0.32.2.
Both print 0.31.3, so the version stamp cannot tell the two apart.

No server is started here. The environment is built from scratch files and inspected.
"""

from __future__ import annotations

import json
import os

import pytest

from ohyesmlx import runtimes
from ohyesmlx.engines import LAB_ENGINES


def write_manifest(tmp_path):
    """The shipped manifest's shape: every engine present, no lab_path committed."""
    payload = {
        name: {
            "version": "0.0.0",
            "verified": "2026-10-29",
            "lab_path": None,
            "canary": None,
        }
        for name in ("mlxlm", "osaurus", "omlx", "optiq", "vmlx")
    }
    path = tmp_path / "engines-tested.json"
    path.write_text(json.dumps(payload))
    return path


def test_the_mlx_lm_control_does_not_get_another_engines_lab_bin_on_path(
    tmp_path, monkeypatch
):
    """This machine's exact shape: lab-paths.json names `optiq` and nothing else.

    `MlxLm.start_command` begins with the bare name `python` and `MlxLm.version_command`
    with `python -m mlx_lm --version`, so whichever `python` PATH names first is the
    interpreter that runs both -- and OptiQ's venv has a `python`.
    """
    optiq_bin = tmp_path / "engines" / "optiq-0.5.13" / "bin"
    optiq_bin.mkdir(parents=True)
    assert (optiq_bin / "python").exists() is False  # nothing but the directory here

    lab_paths = tmp_path / "lab-paths.json"
    lab_paths.write_text(json.dumps({"optiq": str(optiq_bin)}))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    env = runtimes._engine_env(write_manifest(tmp_path), lab_paths)

    assert os.path.expanduser(str(optiq_bin)) not in env["PATH"].split(os.pathsep), (
        "_engine_env put OptiQ's lab bin on PATH for every runtime, so the mlx-lm control "
        "cell's bare `python` resolves there instead of its own venv: "
        f"{env['PATH']}"
    )


def test_a_lab_path_for_one_engine_is_not_prefixed_for_another_engine(
    tmp_path, monkeypatch
):
    """The general form, with both lab-able engines named so neither is special-cased.

    Whatever `_engine_env` grows into, the environment for engine A must not carry engine
    B's lab bin: the two are separate builds and PATH is what picks between them.
    """
    mlxlm_bin = tmp_path / "mlx-lm-0.31.3" / "bin"
    mlxlm_bin.mkdir(parents=True)
    optiq_bin = tmp_path / "optiq-0.5.13" / "bin"
    optiq_bin.mkdir(parents=True)

    lab_paths = tmp_path / "lab-paths.json"
    lab_paths.write_text(
        json.dumps({"mlxlm": str(mlxlm_bin), "optiq": str(optiq_bin)})
    )
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    env = runtimes._engine_env(write_manifest(tmp_path), lab_paths)
    entries = env["PATH"].split(os.pathsep)
    # Coordinator 2026-11-16 (05-07): the ambient PATH is split into entries above, so the
    # filter compares entries, not the joined string, which counted /usr/bin and /bin as prefixes.
    prefixes = [entry for entry in entries if entry not in ("/usr/bin", "/bin")]

    if len(prefixes) > 1:
        pytest.fail(
            "one environment carries both engines' lab bins, so a command from one engine "
            f"can resolve a program from the other: {prefixes}"
        )
    assert len(prefixes) <= 1


def test_the_control_command_and_the_ambient_python_agree_on_the_lab_free_machine(
    tmp_path, monkeypatch
):
    """On a machine with no lab paths the control command is unchanged, which is the
    baseline the manifest's `lab_path: null` promises and `_engine_env`'s docstring states.
    """
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    env = runtimes._engine_env(write_manifest(tmp_path), tmp_path / "absent.json")
    assert env["PATH"] == "/usr/bin:/bin"


def test_only_the_two_lab_able_engines_can_carry_a_prefix():
    """`LAB_ENGINES` is the whole set a lab path may name, so the leak is bounded to two."""
    assert set(LAB_ENGINES) == {"mlxlm", "optiq"}
