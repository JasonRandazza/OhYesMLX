"""macOS unified-memory sampling for a running process.

Peak memory is Apple's ``phys_footprint``, read from ``/usr/bin/footprint -p <pid>``. That
is the number Activity Monitor shows in its Memory column for the process.

``ps`` RSS is never used and must not be added: under MLX, Metal buffers, mmap-ed weights
and wired GPU memory are accounted for inconsistently by RSS, so it cannot answer "how
much RAM does this quant need".

    sampler = Sampler(pid, interval_s=1.0).start()
    run_the_benchmark()
    result = sampler.stop()          # {peak_mb, samples: [{t, mb}], ...}

Sampling happens on a background thread, so ``start()`` returns immediately and the caller
is never blocked by a poll.
"""

from __future__ import annotations

import re
import subprocess
import threading
import time

FOOTPRINT = "/usr/bin/footprint"
VMMAP = "/usr/bin/vmmap"
SYSCTL = "/usr/sbin/sysctl"

DEFAULT_INTERVAL_S = 1.0

FOOTPRINT_TIMEOUT_S = 10.0
VMMAP_TIMEOUT_S = 30.0
SYSCTL_TIMEOUT_S = 5.0
CONSECUTIVE_MISSES_BEFORE_STOP = 3

VMMAP_COMPRESSED_NOTE = (
    "vmmap --summary on this macOS exposes no COMPRESSED column; compressed pages are "
    "folded into SWAPPED, so the split here is dirty/swapped only"
)

_SIZE_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s*([KMGT]?)(?:i?B)?$", re.IGNORECASE)
_MB_PER_UNIT = {
    "": 1.0 / (1024 * 1024),
    "K": 1.0 / 1024,
    "M": 1.0,
    "G": 1024.0,
    "T": 1024.0 * 1024,
}
_PHYS_PEAK_RE = re.compile(r"^phys_footprint_peak:\s*(.+?)\s*$")
_PHYS_RE = re.compile(r"^phys_footprint:\s*(.+?)\s*$")
_VMMAP_FOOTPRINT_RE = re.compile(r"^Physical footprint:\s*(.+?)\s*$")
_VMMAP_PEAK_RE = re.compile(r"^Physical footprint \(peak\):\s*(.+?)\s*$")
_VMMAP_TOTAL_HEADER_RE = re.compile(
    r"^VIRTUAL\s+RESIDENT\s+DIRTY\s+SWAPPED\b(.*)$", re.IGNORECASE
)
_WIRED_LIMIT_RE = re.compile(r"^iogpu\.wired_limit_mb:\s*(-?\d+)\s*$")
_SIZE_COLUMNS = frozenset(
    {"virtual", "resident", "dirty", "swapped", "compressed", "volatile", "nonvol", "empty"}
)


def _run(cmd, timeout_s):
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _reason(proc):
    text = (proc.stderr or proc.stdout or "").strip()
    return text.splitlines()[0] if text else f"exit code {proc.returncode}"


def parse_mb(text):
    """``'907 MB'``, ``'1232K'``, ``'0 B'`` -> megabytes. ``None`` if not a size."""
    match = _SIZE_RE.match(text.strip())
    if match is None:
        return None
    return float(match.group(1)) * _MB_PER_UNIT[match.group(2).upper()]


def parse_footprint_text(text):
    """``phys_footprint`` and ``phys_footprint_peak`` in MB from ``footprint`` stdout.

    The summary header's ``Footprint:`` figure is not used; it is the dirty+clean total and
    differs from phys_footprint.
    """
    found = {"mb": None, "peak_mb": None}
    for raw in text.splitlines():
        line = raw.strip()
        match = _PHYS_PEAK_RE.match(line)
        if match:
            found["peak_mb"] = parse_mb(match.group(1))
            continue
        match = _PHYS_RE.match(line)
        if match:
            found["mb"] = parse_mb(match.group(1))
    return found


def phys_footprint_mb(pid, *, timeout_s=FOOTPRINT_TIMEOUT_S):
    """Current ``phys_footprint`` for *pid* in MB, or ``None`` if it cannot be read."""
    proc = _run([FOOTPRINT, "-p", str(int(pid))], timeout_s)
    if proc is None or proc.returncode != 0:
        return None
    return parse_footprint_text(proc.stdout)["mb"]


def parse_vmmap_summary(text):
    """The ``vmmap --summary`` region-table TOTAL row, as ``{column_name: mb}``.

    Columns are read from the region table's own header rather than by position, so a
    version of vmmap that adds a column (COMPRESSED, for instance) is picked up unchanged.
    """
    lines = [line.strip() for line in text.splitlines()]
    total_at = next((i for i, line in enumerate(lines) if line.startswith("TOTAL")), None)
    if total_at is None:
        return {}

    names = None
    for i in range(total_at - 1, -1, -1):
        match = _VMMAP_TOTAL_HEADER_RE.match(lines[i])
        if match:
            names = ["virtual", "resident", "dirty", "swapped", *match.group(1).lower().split()]
            break
    if names is None:
        return {}

    totals = {}
    values = lines[total_at].split()[1:]
    for name, value in zip(names, values):
        if name in _SIZE_COLUMNS:
            mb = parse_mb(value)
            if mb is not None:
                totals[name] = mb
    return totals


def vmmap_split(pid, *, timeout_s=VMMAP_TIMEOUT_S):
    """``vmmap --summary`` cross-check for *pid*: dirty / swapped / compressed split.

    Also carries vmmap's own ``Physical footprint`` reading, which is the independent
    cross-check on what ``footprint`` reported. Its *compressed* key is ``None`` wherever
    the tool does not expose a compressed column (``note`` says so).
    """
    result = {
        "available": False,
        "reason": None,
        "footprint_mb": None,
        "peak_mb": None,
        "virtual_mb": None,
        "resident_mb": None,
        "dirty_mb": None,
        "swapped_mb": None,
        "compressed_mb": None,
        "note": None,
    }
    proc = _run([VMMAP, "--summary", str(int(pid))], timeout_s)
    if proc is None:
        result["reason"] = f"vmmap did not complete within {timeout_s}s"
        return result
    if proc.returncode != 0:
        result["reason"] = _reason(proc)
        return result

    for raw in proc.stdout.splitlines():
        line = raw.strip()
        match = _VMMAP_PEAK_RE.match(line)
        if match:
            result["peak_mb"] = parse_mb(match.group(1))
            continue
        match = _VMMAP_FOOTPRINT_RE.match(line)
        if match:
            result["footprint_mb"] = parse_mb(match.group(1))

    totals = parse_vmmap_summary(proc.stdout)
    result["available"] = True
    for column in ("virtual", "resident", "dirty", "swapped", "compressed"):
        result[f"{column}_mb"] = totals.get(column)
    if result["compressed_mb"] is None:
        result["note"] = VMMAP_COMPRESSED_NOTE
    return result


def gpu_wired_limit(*, timeout_s=SYSCTL_TIMEOUT_S):
    """Whether ``iogpu.wired_limit_mb`` has been raised, with the raw reading.

    A raised wired limit changes how much model fits, and so changes what is comparable
    against runs taken elsewhere. 0 is the stock value: not raised.
    """
    result = {"mb": None, "raised": False, "raw": None, "reason": None}
    proc = _run([SYSCTL, "iogpu.wired_limit_mb"], timeout_s)
    if proc is None:
        result["reason"] = f"sysctl did not complete within {timeout_s}s"
        return result
    if proc.returncode != 0:
        result["reason"] = _reason(proc)
        return result

    result["raw"] = proc.stdout.strip()
    match = _WIRED_LIMIT_RE.match(result["raw"])
    if match is None:
        result["reason"] = f"unrecognised sysctl output: {result['raw']!r}"
        return result
    result["mb"] = int(match.group(1))
    result["raised"] = result["mb"] > 0
    return result


class Sampler:
    """Polls ``footprint -p <pid>`` on a background thread for the life of a run.

    ``start()`` returns immediately; ``stop()`` joins the thread and returns
    ``{peak_mb, samples, ...}``. ``peak_mb`` is the largest ``phys_footprint`` seen, or
    ``None`` if the process was never sampled successfully.
    """

    def __init__(self, pid, interval_s=DEFAULT_INTERVAL_S):
        if interval_s <= 0:
            raise ValueError("interval_s must be > 0")
        self.pid = int(pid)
        self.interval_s = float(interval_s)
        self.result = None
        # ponytail: plain list appended from the worker thread. CPython list.append is
        # atomic, so reading it mid-run is safe for inspection. Ceiling: no snapshot
        # guarantee across future interpreters. Upgrade path: hand out a locked copy.
        self.samples = []
        self.error = None
        self._t0 = None
        self._stop = threading.Event()
        self._thread = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *_exc):
        self.stop()
        return False

    @property
    def running(self):
        """Whether the sampling thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        """Begin sampling. Returns immediately; the polling happens on a worker thread."""
        self._t0 = time.monotonic()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name=f"ohyesmlx-sample-{self.pid}", daemon=True
        )
        self._thread.start()
        return self

    def _loop(self):
        misses = 0
        while not self._stop.is_set():
            t = time.monotonic() - self._t0
            mb = phys_footprint_mb(self.pid)
            if mb is None:
                misses += 1
                if misses >= CONSECUTIVE_MISSES_BEFORE_STOP:
                    self.error = (
                        f"footprint read nothing {misses} times running for pid {self.pid}; "
                        "the process has most likely exited"
                    )
                    return
            else:
                misses = 0
                self.samples.append({"t": t, "mb": mb})
            self._stop.wait(self.interval_s)

    def stop(self):
        """Stop sampling and return the result dict (also stored on ``self.result``)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=FOOTPRINT_TIMEOUT_S + 1.0)
            if self._thread.is_alive():
                self.error = f"sampling thread for pid {self.pid} is still alive after join"
            else:
                self._thread = None

        samples = list(self.samples)
        peak_mb = max((s["mb"] for s in samples), default=None)
        self.result = {
            "pid": self.pid,
            "interval_s": self.interval_s,
            "duration_s": time.monotonic() - self._t0 if self._t0 is not None else 0.0,
            "n_samples": len(samples),
            "peak_mb": peak_mb,
            "samples": samples,
            "memory_split": vmmap_split(self.pid),
            "gpu_wired_limit": gpu_wired_limit(),
            "error": self.error,
        }
        return self.result
