"""`ohyesmlx canary`: did an engine version bump move the numbers?

Decision 135's loop. Every published table was measured against one build -- the manifest's
``version`` for that engine -- and the engines upgrade under us: OptiQ went 0.5.13 to 0.7.8
on 2026-10-29 without anyone asking. Re-running every table to find out whether a bump
mattered costs hours; one fixed cell per engine costs minutes and answers the question the
tables actually ask: is the number this engine publishes still the number it published?

The cell is the manifest's own ``canary`` block -- one format, one repo, the ``decode``
workload -- and nothing here selects a second one: :func:`cells` composes the block as a
``--cells`` string and ``cli`` hands that string to ``build_cells``, the only cell selector
there is. Four engines canary on the ``stock4bit`` Qwen3.5-4B artifact the grid already
owns; Osaurus has no stock4bit cell in the grid, so its canary is the ``oq4`` one it does.

Three rules shape the rest.

**The comparison is pure, and the floor is one number.** :func:`verdict` is handed two sets
of numbers and answers which metric moved and by how much; ``NOISE_FLOOR`` is Decision 131's
~5% session bar, the point below which two sessions of the same cell on this host are one
reading rather than two results. The comparison is made on the percentage *as published*
(one decimal), so the number a reader sees is the number that decided the verdict: 5.0%
reads "no effect" rather than "moved +5%".

**A failed cell is never a verdict.** A cell that failed the coherence gate or never started
is ``FAIL: <reason>`` and no percentage is computed from it, because the number on such a
row is not a measurement of anything (a fast cell emitting garbage is a failed cell).

**A baseline recorded on a busy machine is not a baseline.** The harness cannot detect
contention, so this command reads the 1-minute load average around each engine's cell and
records it with the verdict. Above ``LOAD_NOISY`` the engine is marked noisy, and
``--record`` refuses its baseline unless ``--allow-noisy`` says the number is wanted anyway.
"""

from __future__ import annotations

import json
import os
import pathlib
import statistics
from dataclasses import dataclass

from ohyesmlx import fetch

# Decision 131's session bar. The vMLX repetition-penalty re-run moved its control formats
# by 1.4-12.7% with no penalty in them, so nothing below ~5% is separable from the session
# on this host. A canary exists to say whether a version bump moved a *published* number by
# more than that; a smaller threshold would report sessions as version effects.
NOISE_FLOOR = 0.05

# Contention is not a measurement error a rerun averages out, it is a reason not to record:
# the 2026-09-16 grid published a 40.6% drift it could not explain because other work ran
# during one column. Load is read before and after each engine's cell, and this 12-core host
# is allowed to be busy up to this 1-minute average before the reading counts as noisy.
LOAD_NOISY = 4.0

# Printed, and nothing else started, when the run is not confirmed with `--yes`.
QUIET_MACHINE = (
    "A canary measures one cell per engine, so nothing else may run on this machine while "
    "it does: close other apps and the browser, and start no test run, build, download or "
    "git operation. The 1-minute load average is read around each engine's cell; above "
    f"{LOAD_NOISY} the engine is marked noisy and --record refuses its baseline unless "
    "--allow-noisy is passed."
)
ESTIMATE = "One cell per engine on the decode workload: about 10-15 minutes for the five."


@dataclass(frozen=True)
class Verdict:
    """The metric that moved furthest, its signed percentage, and the line it earns."""

    moved_pct: float | None  # None when no metric cleared the floor
    metric: str | None  # "decode_tok_s" | "ttft_s"
    text: str  # "no effect" | "moved -11.4%"


@dataclass(frozen=True)
class Reading:
    """One engine's canary outcome: what moved, against which versions, on how busy a Mac."""

    engine: str
    text: str  # `verdict_line`'s answer: a verdict, or "FAIL: <reason>"
    baseline_version: str | None  # the version the baseline was recorded at
    measured_version: str | None  # the engine's detected version now
    load_before: float
    load_after: float

    @property
    def noisy(self) -> bool:
        """Whether the machine was busier than ``LOAD_NOISY`` while the cell ran."""
        return max(self.load_before, self.load_after) > LOAD_NOISY

    def line(self) -> str:
        """The one line this engine's run prints."""
        versions = (
            f"version {self.baseline_version or 'unrecorded'} -> "
            f"{self.measured_version or 'unknown'}"
        )
        loads = f"load {self.load_before:.1f} -> {self.load_after:.1f}"
        if self.noisy:
            loads += f", noisy: above {LOAD_NOISY}"
        return f"{self.engine}: {self.text}  [{versions}; {loads}]"


@dataclass(frozen=True)
class MedianReading:
    """One engine's N canary rows reduced to the reading its verdict and baseline use.

    ``decode_tok_s`` and ``ttft_s`` are the medians of the N rows. ``failure`` is set instead
    when one of the reps did not PASS, and names the first such rep when there is more than one
    visit: a number from a cell that failed the coherence gate is not a measurement, however
    fast it was. A metric some rep left undefined stays ``None`` -- the median of the reps that
    had one is not the median of N.
    """

    decode_tok_s: float | None
    ttft_s: float | None
    failure: str | None  # "FAIL: rep <k>: <reason>", or None


def _pct(change: float) -> str:
    """A signed percentage at the published precision, without a bare ".0"."""
    return f"{change:+.1f}%".replace(".0%", "%")


def verdict(baseline, measured, floor=NOISE_FLOOR) -> Verdict:
    """Which metric moved furthest from *baseline* to *measured*, and by how much.

    Both sides are mappings carrying ``decode_tok_s`` and ``ttft_s``: the manifest's canary
    block on the baseline side and ``report.summarize``'s row on the measured one, so neither
    figure is recomputed here -- the harness's own decode rate and TTFT are what get
    compared. The reading is the change in percent, rounded to the one decimal a reader is
    shown, and the metric with the larger absolute change names the verdict.

    A baseline of ``0`` is read as one that was never recorded: ``engines.load_manifest``
    admits it, and a percentage change from zero is undefined rather than infinite. A change
    of exactly *floor* is no effect: ``floor`` is the width of the session, and a number
    sitting on its edge has not left it.
    """
    worst = None
    for metric in ("decode_tok_s", "ttft_s"):
        base = baseline[metric]
        if base is None or base == 0:
            continue
        change = round((measured[metric] - base) / base * 100.0, 1)
        if worst is None or abs(change) > abs(worst[1]):
            worst = (metric, change)
    if worst is None:
        return Verdict(None, None, "no baseline recorded: --record writes one")
    metric, change = worst
    if abs(change) <= floor * 100.0:
        return Verdict(None, None, "no effect")
    return Verdict(change, metric, f"moved {_pct(change)}")


def verdict_line(baseline, row, floor=NOISE_FLOOR) -> str:
    """One engine's verdict line, from the row `report.summarize` wrote for its cell.

    A row that is not ``PASS`` never reaches the comparison: its reason is the verdict, in
    the harness's own words, because a cell that failed the coherence gate or never started
    has no number to compare against anything. A ``PASS`` row whose ``decode_tps`` or
    ``ttft_p50_s`` is ``None`` has no rate to compare either: ``report`` leaves those empty
    for a stream with fewer than two content deltas, and the line says the rate is undefined
    rather than raising. A ``PASS`` row with no recorded baseline says so instead of
    comparing -- the manifest ships null (or zero) baselines until a run records one.
    """
    if row["status"] != "PASS":
        return f"FAIL: {row['reason']}"
    undefined = [
        field for field in ("decode_tps", "ttft_p50_s") if row[field] is None
    ]
    if undefined:
        return f"no verdict: {', '.join(undefined)} is undefined for this row"
    if baseline is None or any(
        baseline.get(metric) in (None, 0) for metric in ("decode_tok_s", "ttft_s")
    ):
        return "no baseline recorded: --record writes one"
    reading = verdict(
        baseline, {"decode_tok_s": row["decode_tps"], "ttft_s": row["ttft_p50_s"]}, floor
    )
    if reading.moved_pct is None:
        return "no effect on our tables"
    return f"{reading.text}: re-run the grids containing {row['runtime']}"


def median_reading(rows) -> MedianReading:
    """One engine's N canary rows as the reading its verdict and baseline are taken from.

    The rows are ``report.summarize``'s, one per visit in rep order. The canary makes one
    statement per engine, so this is the one place N readings become one: the median per
    metric, which is what a 5-10% session-to-session swing (the reason for revisiting at all)
    cannot move on its own. An even N is the midpoint of the two middle readings, which is
    ``statistics.median``'s definition and the one this command publishes.

    A rep that did not PASS returns the FAIL line naming it instead: the engine's verdict is
    the failure, and nothing is compared or recorded from the visits that did pass. The rep is
    named only when there is more than one visit, because a single-visit line has no second
    rep to be mistaken for and the line a one-visit run prints is unchanged. This is the only
    median the canary computes; the CLI reads its answer rather than reducing rows itself.
    """
    rows = list(rows)
    for rep, row in enumerate(rows, start=1):
        if row["status"] != "PASS":
            where = f"rep {rep}: " if len(rows) > 1 else ""
            return MedianReading(None, None, f"FAIL: {where}{row['reason']}")
    decode = [row["decode_tps"] for row in rows]
    ttft = [row["ttft_p50_s"] for row in rows]
    return MedianReading(
        None if None in decode else statistics.median(decode),
        None if None in ttft else statistics.median(ttft),
        None,
    )


def artifact_dir(repo: str, root=None) -> str:
    """The newest Hugging Face cache snapshot of *repo* that carries a ``config.json``.

    The cache keeps one directory per repo and one directory per fetched revision under
    ``snapshots/``, so the revision a run should serve is the newest one that holds the
    config -- a half-finished fetch has none. ``root`` is the cache directory (the parent of
    every ``models--<org>--<name>``), injected so a test reads a tree it made; the default
    is ``fetch.default_cache_dir()``, so the same ``HF_HUB_CACHE`` the downloader honours
    decides where the canary looks (AC-2).
    """
    root = fetch.default_cache_dir() if root is None else root
    snapshots = pathlib.Path(root) / f"models--{repo.replace('/', '--')}" / "snapshots"
    found = (
        [path for path in snapshots.iterdir() if (path / "config.json").is_file()]
        if snapshots.is_dir()
        else []
    )
    if not found:
        raise ValueError(
            f"no Hugging Face snapshot of {repo} with a config.json under {snapshots}; "
            "fetch it before the canary runs"
        )
    return str(max(found, key=lambda path: path.stat().st_mtime))


def cells(engine: str, spec: dict, root=None) -> str:
    """One engine's ``--cells`` string: ``<format>__<engine>=<artifact dir>``.

    The canary has no selection of its own: this is the manifest's cell written in the
    syntax ``build_cells`` already parses, so the run is an ordinary harness run of one cell.
    """
    return f"{spec['format']}__{engine}={artifact_dir(spec['repo'], root)}"


def load() -> float:
    """This machine's 1-minute load average: the contention reading, injected in tests."""
    return os.getloadavg()[0]


def record(
    path, engine: str, *, decode_tok_s, ttft_s, version_measured, measured, runs=None
) -> dict:
    """Write one engine's baseline into the manifest at *path*, and nothing else.

    The four fields are the canary block's mutable half: the cell (format, repo, workload)
    stays as the manifest pins it, and each other engine's entry is untouched. *runs* is the
    engine's per-visit ``{decode_tok_s, ttft_s}`` readings in rep order, kept beside the
    medians so the baseline stays recomputable from what was measured -- raw observations are
    never discarded. A caller that measured one visit and passes no *runs* writes exactly the
    fields it always has. The tested *version* and its verified date are deliberately not
    written here -- a baseline recorded on an untested build is evidence for the next
    decision, never the decision, and adopting the version silently is how a published table
    comes to claim a build nobody chose.
    """
    path = pathlib.Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    entry = payload[engine]["canary"]
    entry.update(
        {
            "decode_tok_s": decode_tok_s,
            "ttft_s": ttft_s,
            "version_measured": version_measured,
            "measured": measured,
        }
    )
    if runs is not None:
        entry["runs"] = list(runs)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return entry
