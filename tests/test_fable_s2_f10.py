"""Reproduction for Fable 5.2 S2-F10: a raising restore after a pin that did not take is silent.

The claim: ``quickbench.measure_cell`` (``quickbench.py:707-717``) sets
``restored = False if pinned else None`` when ``restore`` raises. If ``pin`` itself raised
part-way -- a backup written, one settings file already changed, then an error -- ``pinned``
stays False and the cell is SKIPPED. A ``restore`` that then also raises leaves ``restored``
``None``, so neither the ``is True`` nor the ``is False`` branch runs: no
``summary["osaurus"]["restored"]``, no ``reason``, no ``restore_failed`` event, and the user is
told nothing while Osaurus may be left on harness settings with the original bytes in
``backup_dir``.

``osaurus_settings.pin`` can raise after it has written: the two config files are parsed before
either is replaced (``osaurus_settings.py:267-268``), but the backups and both writes happen
after that (``:270-286``), so a failure in either write leaves a partial pin and a backup on
disk.

The pin and restore here are the fakes ``tests/test_quickbench.py`` already uses for the
restoring-but-pinned case; only the pin's own failure is added.
"""

from __future__ import annotations

from test_quickbench import WITH_OSAURUS, a_run


def test_a_raising_restore_after_a_failed_pin_names_the_backup_directory(tmp_path):
    """recover ok, pin raises, restore raises: the host may be pinned and nothing says so."""
    _ok, fakes, summary = a_run(
        tmp_path,
        engines_list=WITH_OSAURUS,
        osaurus=True,
        pin_error="the settings write failed",
        restore_error="the settings write failed again",
    )

    # The scenario is the claimed one: the pin did not take effect, so the cell was skipped
    # with the pin's own reason rather than measured.
    cell, = [cell for cell in summary["stage_a"]["cells"] if cell["engine"] == "osaurus"]
    assert cell["status"] == "SKIPPED"
    assert "the settings write failed" in cell["reason"]
    assert summary["osaurus"]["pinned"] is False

    # Both side effects were really attempted, so "restored: None" is not the shape of a run
    # that never tried.
    assert [name for name, _kwargs in fakes.osaurus.calls] == ["recover", "pin", "restore"]

    ours = summary["osaurus"]
    assert ours["restored"] is False, (
        f"a restore that raised is recorded as restored: {ours['restored']!r}; Osaurus may "
        "still hold the harness settings and the record says nothing about it"
    )
    assert ours["reason"] is not None, "nothing names the backup the originals are in"
    assert str(tmp_path / "backup") in ours["reason"]
    assert any(
        event["type"] == "error" and event["payload"]["code"] == "restore_failed"
        for event in fakes.events
    ), "no restore_failed event reached the app"
