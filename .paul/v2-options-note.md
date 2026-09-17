# v2 candidates — options note for Jason (2026-09-17)

Plan only. Nothing below starts without Jason's go-ahead.

## 1. JANG-in-vMLX as its own cell study (ROADMAP "Out of this milestone")

The question: JANG_4S is fastest in both runtimes that load it, but it loads in no
runtime that loads the portable formats — it is a runtime+format bundle, not an axis
point. The honest study is JANG-in-vMLX against the best portable format in the same
vMLX, format held constant, runtime held constant, loader as the variable.

- Cost: measurement campaign, one runtime, two cells plus repeats. No harness work
  expected (vMLX already a supported runtime).
- Risk: low. The comparison is single-variable by construction.

## 2. Accuracy via lm-evaluation-harness

The coherence gate is a floor ("is this language at all"), never an eval. v2's accuracy
axis would be lm-eval's `local-chat-completions` against the same OpenAI-compatible
endpoints, same pinning discipline (temperature 0, fixed seed, fixed template).

- Cost: harness integration work (new module + CLI surface), then eval runs that are
  slower than speed cells by an order of magnitude.
- Risk: medium. Eval comparability across runtimes has the same sampler-default traps
  the speed work just finished pinning; scope must stay narrow (one benchmark, not a suite).

## 3. Repeat the cache split on a non-hybrid model

The 06-02 finding (only oMLX and Osaurus serve a warm hit) is proven only on Qwen3.5, a
hybrid model whose `ArraysCache` mlx-lm/OptiQ cannot trim and whose prefix cache vMLX
declines. Open question: on a non-hybrid model, do mlx-lm, OptiQ and vMLX hit?

- Cost: one measurement campaign on a model with all portable formats published
  (needs a model choice + format availability check first). No harness work.
- Risk: low, but the answer may be "still no" for reasons each runtime documents
  nowhere — a negative result is still publishable.

## 4. vMLX 32k on a later vMLX release

vMLX 1.6.59's hybrid prefill path is one-shot regardless of `--prefill-step-size`
(42/49 die). A later release may chunk it. Re-running the single 32k cell on a new
vMLX decides whether the published FAIL is version-specific.

- Cost: one cell re-run per candidate release. Trivial.
- Risk: none, but watch the release notes for prefill-path changes first — don't
  re-run blind on every point release.

## Suggested order (coordinator's view, not a decision)

3 → 4 → 1 → 2. The cache-split repeat and the vMLX re-test are cheap and close out
v1's two open measurement questions; JANG is the headline v2 study; accuracy is the
largest scope and should go last, alone.
