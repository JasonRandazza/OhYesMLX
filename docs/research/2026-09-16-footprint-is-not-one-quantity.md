# The eighth defect, probed: `phys_footprint` is not one quantity across runtimes

Date: 2026-09-16, 08:45–09:05Z. `scripts/probe_footprint.py` plus two follow-ups. Not a
measurement of any published figure — this settles what `peak_mb` means.

## The defect, as the joined grid found it

Decode workload, `footprint` against the weights on disk:

| runtime | footprint MB | weights MB |
|---|---|---|
| mlx-lm | 2867–3789 | 3061–4044 |
| oMLX | 3686–4198 | 3061–4044 |
| mlx-optiq | 2970–3789 | 3061–4044 |
| vMLX | 3686 | 3061–3207 |
| **Osaurus** | **1331–2560** | 3161–4044 |

Four columns land within a few percent of the weight bytes. Osaurus lands at roughly half —
below the size of the weights it is serving.

## The first explanation was wrong

The standing hypothesis, recorded in `report.CROSS_RUNTIME_UNCOMPARABLE` and in the Phase 5
write-up, was that Osaurus maps its weights **file-backed**, leaving them clean and therefore
uncounted by `phys_footprint`.

`vmmap`'s full region table — not the `--summary` TOTAL row the harness samples — says no:

| | mapped-file resident | total resident | weights |
|---|---|---|---|
| Osaurus | **34 MB** | 2524 MB | 3014 MB |
| oMLX | **2 MB** | 4633 MB | 3014 MB |

Neither runtime holds any meaningful part of its weights in mapped-file regions. The
hypothesis is dead.

## What is actually happening: the page class differs

The region table points straight at it. `IOAccelerator (graphics)`, serving identical weights:

- **oMLX: 3334 MB** — the weights are plainly in the GPU allocation, and `phys_footprint`
  counts them.
- **Osaurus: 581 MB** — they are not.

Loading the same artifact and watching system-wide page counts across the load:

| | process footprint | wired | active |
|---|---|---|---|
| Osaurus | 1562 MB | **+1064 MB** | −66 MB |
| oMLX | 3995 MB | +1 MB | **+752 MB** |

Osaurus's weights go into **wired**, GPU-pinned pages. oMLX's are ordinary **active**
anonymous memory. `phys_footprint` charges those two differently, which is the whole defect.
Exactly how Metal attributes a wired device allocation back to a process is not settled here
and does not need to be: what a cross-runtime memory ranking needs is *one quantity*, and this
is demonstrably not one.

The system-wide deltas are both well under 3014 MB because the weight files were already in
the unified buffer cache — every runtime in this project had read them repeatedly by then — so
the delta measures re-mapping rather than a cold read. That does not affect the comparison,
which is between the two runtimes' page classes, not the absolute sizes.

## What changes

`report.CROSS_RUNTIME_UNCOMPARABLE["peak_mb"]` already refused to let a runtime-axis ordering
by `peak_mb` be read as a ranking. Its justification is now a measurement rather than an
inference, and the wrong explanation has been removed from the source comment rather than left
sitting there looking authoritative.

**A format-axis ordering by `peak_mb` is still sound.** Within one column the runtime is held
constant, so whatever page class it uses, it uses for every format. It is only the
cross-runtime reading that has no single quantity behind it.

## The other thing the probe found: Osaurus processes accumulate

While probing, four `osaurus` processes were live, three of them stale
`--launched-by-cli` app instances aged **5h13m, 5h23m and 6h49m** — spanning every measurement
taken during the night — holding 851, 902 and 915 MB. None held a port.

`osaurus stop` frees the port and leaves the app alive. That was already known and recorded in
the handoff; what was not recorded is that the leftovers **accumulate across runs** and each
keeps roughly 900 MB resident. Three of them is 2.7 GB of the machine held by servers nobody
is talking to, present during the dense grid, the MoE grid and both re-runs.

On a 64 GiB machine that is not enough to invalidate the measurements, and the numbers do not
suggest it did. It is still a leak in the protocol: the grid sweeps **ports** between columns,
and a process that has released its port survives the sweep by design.

**Fixed for the sweep, not for the harness:** they are now swept by their full executable path
between runs. Never by the name `osaurus` alone — `osaurus mcp` is a long-running user process
and must not be touched. That distinction is why the sweep never grew this rule by itself.

A fresh Osaurus with no siblings at all still reports 1552 MB against 3014 MB of weights, so
the accumulation is a separate problem from the accounting one and neither explains the other.
