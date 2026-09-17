GOAL (diagnosis only, read-only): results/sweep-prompt/runner.log and
results/sweep-cache/runner.log are 0 bytes although the runners echoed progress and the
per-run logs are fine. Find why.

READ: scripts/run_sweep_prompt.sh and scripts/run_sweep_cache.sh (how each runner redirects
its own output and its per-run logs); list results/sweep-prompt/ and results/sweep-cache/ to
see what actually landed; check whether anything in the repo ever creates or redirects into
a file named runner.log, and how the runners were likely invoked (redirection is set up by
the CALLER's shell before the script runs — a missing directory at redirect time, a
redirect to a different cwd, or output going to a terminal instead of a file are all live
hypotheses; confirm or kill each from the evidence).

WRITE NOTHING. This is an `explain` dispatch: read-only by construction.

ANSWER IN YOUR REPORT: the root cause with the file:line or the invocation fact behind it;
whether the cause is in this repo (a fix belongs here) or in how the runs were launched
(then say exactly what the launcher should have done); and if in-repo, sketch the smallest
fix as a proposal — do not implement it.
