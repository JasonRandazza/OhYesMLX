"""Fable 5.2 S1-F6: the event cap ends the job on paper while its worker keeps running.

At `MAX_EVENTS` the server stores `too_many_events` plus `done`, sets only
`cancel_requested`, and calls `_registry.finished(self)` (server.py:185-202). No
`abort_requested` is set and the module call is not waited for. Quickbench probes
`cancel` between cells (quickbench.py:772, :809, :845, :891), so a cap that lands
mid-cell leaves that cell's engine resident; a second quickbench accepted at that
moment starts a second runtime -- two engines at once, which the project voids a run for.

The invariant: a cap may end the *stream*, but it must not free the one job slot while
the module call that owns the engine has not returned. Nothing starts here: this drives
`_Job.append` and `_Jobs` directly.
"""

from __future__ import annotations

from ohyesmlx import server


def test_the_cap_must_not_free_the_slot_while_the_module_call_still_owns_the_engine():
    registry = server._Jobs()
    first = server._Job(registry, "0" * 16, "quickbench", "mlx-community/model-one")
    assert registry.claim(first) is None

    # The worker is inside a cell; these are the progress events a chatty module emits.
    for _ in range(server.MAX_EVENTS):
        first.append(server._event("progress", "a cell is running", None))
        if first.done:
            break

    assert first.done is True
    assert [event["type"] for event in first.events[-2:]] == ["error", "done"]
    assert first.events[-2]["payload"]["code"] == "too_many_events"

    second = server._Job(registry, "1" * 16, "quickbench", "mlx-community/model-two")
    holder = registry.claim(second)

    assert holder is first, (
        "the cap freed the slot while the first quickbench call is still inside its cell; "
        "a second quickbench would start a second engine beside the resident one"
    )
