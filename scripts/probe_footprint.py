"""Probe: why does Osaurus report a footprint below the weights it is serving?

The joined grid exposed the eighth measurement-validity defect. Decode workload, `footprint`
against `vmmap`'s resident size and the weights on disk:

    runtime      footprint MB   resident MB   weights MB
    mlx-lm          2867-3789     3379-4198    3061-4044
    oMLX            3686-4198     4403-4813    3061-4044
    mlx-optiq       2970-3789     3379-4198    3061-4044
    vMLX            3686          4096-4301    3061-3207
    Osaurus         1331-2560     2867-3994    3161-4044

In four columns footprint lands within a few percent of the weight bytes. In the Osaurus
column it lands at roughly half them -- below the size of the weights the process is serving,
which a process holding them in anonymous memory cannot do -- while that column's resident
number sits right at the weights.

The standing explanation is that Osaurus maps its weights file-backed, so those pages are
clean and `phys_footprint` does not count them. **That is a hypothesis, and this script is
what turns it into a finding or kills it.** Until then "Osaurus uses half the memory" is a
claim about the sampler, not the runtime, and `report.CROSS_RUNTIME_UNCOMPARABLE` says so
above any runtime-axis ordering by `peak_mb`.

What it does: starts one runtime on one artifact, sends a single request so the weights are
certainly resident, then reads the full `vmmap` region table -- not the `--summary` TOTAL row
the harness uses, but the per-region breakdown -- and reports how many MB sit in mapped-file
regions against how many sit in anonymous ones. A runtime whose weights are file-backed shows
the weight bytes under `mapped file`; one that read them into anonymous memory does not.

Run it against two runtimes on the same artifact and the answer is a comparison rather than a
number: same weights, same size on disk, and the difference is where the pages live.

    scripts/probe_footprint.py osaurus omlx      # or any subset of the five

Nothing here is a published figure. It answers one question about the sampler.
"""

from __future__ import annotations

import collections
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ohyesmlx import runtimes, sample, token_counter, transport  # noqa: E402

ARTIFACT = os.path.expanduser(
    "~/.cache/huggingface/hub/models--RepublicOfKorokke--Qwen3.5-4B-oQ4/snapshots/"
    "3ae88a7d17b1c6bb71b795c1090948a82508fdb8"
)
PROMPT = [{"role": "user", "content": "Say the word ready."}]

# vmmap's region lines: "REGION TYPE   START - END   [ VSIZE  RSDNT  DIRTY   SWAP] ..."
# The columns are whitespace-separated and the region type itself contains spaces, so the
# split is anchored on the address range rather than on column count.
_REGION = re.compile(
    r"^(?P<kind>.+?)\s+([0-9a-f]+)-([0-9a-f]+)\s+\[\s*(?P<vsize>\S+)\s+(?P<rsdnt>\S+)\s+"
    r"(?P<dirty>\S+)\s+(?P<swap>\S+)\s*\]",
    re.IGNORECASE,
)


def regions(pid: int) -> list[dict]:
    """Every region vmmap reports for *pid*, with its sizes in MB."""
    proc = subprocess.run(
        [sample.VMMAP, str(pid)], capture_output=True, text=True, timeout=120
    )
    if proc.returncode != 0:
        raise RuntimeError(f"vmmap {pid} exited {proc.returncode}: {proc.stderr[:200]}")

    found = []
    for line in proc.stdout.splitlines():
        match = _REGION.match(line)
        if not match:
            continue
        found.append(
            {
                "kind": match.group("kind").strip(),
                "resident_mb": sample.parse_mb(match.group("rsdnt")),
                "dirty_mb": sample.parse_mb(match.group("dirty")),
            }
        )
    return found


def by_kind(found: list[dict]) -> list[tuple[str, float, float]]:
    """Regions folded by type, biggest resident first."""
    totals: dict[str, list[float]] = collections.defaultdict(lambda: [0.0, 0.0])
    for region in found:
        resident = region["resident_mb"] or 0.0
        dirty = region["dirty_mb"] or 0.0
        totals[region["kind"]][0] += resident
        totals[region["kind"]][1] += dirty
    ordered = sorted(totals.items(), key=lambda item: -item[1][0])
    return [(kind, sizes[0], sizes[1]) for kind, sizes in ordered]


def probe(name: str) -> None:
    runtime = runtimes.RUNTIMES.get(name)
    if runtime is None:
        print(f"{name}: unknown runtime")
        return

    print(f"\n{'=' * 72}\n{name}\n{'=' * 72}")
    counter = token_counter.TokenCounter(ARTIFACT)
    handle = runtime.start(ARTIFACT, ARTIFACT)
    try:
        # One request, so the weights are certainly resident rather than merely mapped.
        transport.chat(
            handle.base_url, handle.model_id, PROMPT, max_tokens=8,
            temperature=0.0, seed=0, token_counter=counter, api_key=handle.api_key,
        )
        time.sleep(1.0)

        pid = handle.memory_pid
        footprint = sample.phys_footprint_mb(pid)
        split = sample.vmmap_split(pid)
        found = regions(pid)

        mapped = sum(r["resident_mb"] or 0.0 for r in found
                     if "mapped file" in r["kind"].lower())
        total_resident = sum(r["resident_mb"] or 0.0 for r in found)
        weights_mb = sum(
            os.path.getsize(os.path.join(root, f))
            for root, _dirs, files in os.walk(ARTIFACT) for f in files
        ) / (1024 * 1024)

        print(f"pid                {pid}")
        print(f"weights on disk    {weights_mb:8.0f} MB")
        print(f"phys_footprint     {footprint if footprint is None else f'{footprint:8.0f} MB'}")
        print(f"vmmap resident     {total_resident:8.0f} MB  (summed over regions)")
        print(f"  of which mapped file {mapped:8.0f} MB  <- file-backed, clean, not in footprint")
        print(f"  of which other       {total_resident - mapped:8.0f} MB")
        print(f"vmmap --summary    {split}")
        print("\nbiggest regions by resident size:")
        for kind, resident, dirty in by_kind(found)[:8]:
            print(f"  {kind:34} resident {resident:8.1f} MB   dirty {dirty:8.1f} MB")

        verdict = (
            "weights look FILE-BACKED: mapped-file regions cover the weight bytes"
            if mapped >= weights_mb * 0.8
            else "weights do NOT look file-backed: mapped-file regions are well under the weights"
        )
        print(f"\n  => {verdict}")
    finally:
        handle.stop()


if __name__ == "__main__":
    names = sys.argv[1:] or ["osaurus", "omlx"]
    for runtime_name in names:
        try:
            probe(runtime_name)
        except Exception as error:  # noqa: BLE001 - a probe that cannot run says so and moves on
            print(f"{runtime_name}: probe failed: {type(error).__name__}: {error}")
