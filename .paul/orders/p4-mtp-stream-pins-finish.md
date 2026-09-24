## Order: finish the `--mtp-depth` / `--stream-experts` pins (continuation)

The original order is `.paul/orders/p4-mtp-stream-pins.md` — read it; its acceptance criteria and
file list stand. A previous worker ran out of turns with its work **uncommitted in the tree**
(`git diff`; suite currently 611 green). Its last words: "Let me correct the `LOG_HEAD_BYTES`
claim with the measured offsets and make the tests use verbatim recorded lines". It left no report.

Do, in order:
1. Read the whole `git diff`. Finish that `LOG_HEAD_BYTES` correction and anything else left
   half-done. Do not restart from scratch and do not revert working parts.
2. Check every acceptance criterion of the original order against the tree; fix gaps.
3. Trim. The diff is +859 lines in `runtimes.py` alone. AGENTS.md: each rationale is written
   once, where the thing is defined; callers point at it. Where a docstring restates the refusal
   string it returns (or another docstring), cut the docstring to one pointer line. Remove any
   dead helper, duplicated constant, or second copy of a check. Behaviour must not change: the
   suite stays green, and the same tests pass.
4. Run the suite; red-check the log-banner verification (OptiQ `SSD expert streaming: on`, and
   vMLX's equivalent) and the MTP refusal.
5. Report: what each pin does per runtime with its citation; how "on"/depth is verified live;
   any BLOCKED question; what you did not verify; the final `git diff --stat` and test count.

Files: exactly those in the original order. Touch nothing else. Do not commit.
