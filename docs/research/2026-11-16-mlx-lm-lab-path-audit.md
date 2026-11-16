# Which measured mlx-lm rows ran from OptiQ's lab venv

**Date:** 2026-11-16
**Finding:** S5-F1
**Scope:** every existing `results/**/results.jsonl` on this Mac, plus both app quickbench runs under Application Support. This is an attribution audit, not a re-measurement.

## Summary

The audit covers **47 run directories and 216 rows whose `cell.runtime` is `mlxlm`**.

| Verdict | Run directories | mlx-lm rows |
|---|---:|---:|
| Affected | 2 | 2 |
| Not affected | 45 | 214 |
| Undetermined | 0 | 0 |
| **Total** | **47** | **216** |

**One-line answer:** only app quickbench runs `20261102T225004Z` and `20261103T164018Z` have mlx-lm rows demonstrated by their own runtime logs to have run `mlx_lm.server` from OptiQ's `optiq-0.5.13` lab venv; every other mlx-lm run in the corpus is not affected, and no run remains undetermined.

Of the 45 unaffected runs, 44 (213 rows) predate `e7a98ae`, which introduced the shared lab-prefix mechanism. The other is canary `20261029T201017Z-mlxlm` (one row): it postdates that commit but predates the OptiQ lab install, and both of its runtime logs name the dedicated mlx-lm control venv.

Neither affected run directory is cited by name in any pre-existing document under `docs/research/`; this audit note itself is excluded from that statement.

## Evidence for the lab-path window

### Mechanism and manifest history

- `e7a98ae479205294f2c340965dcd299b088f8820` (`2026-10-29T15:22:58-04:00`, `2026-10-29T19:22:58Z`) introduced `_engine_env` and its shared PATH-prefix behavior. Runs before this commit are not affected.
- `git log --follow -p -- ohyesmlx/engines-tested.json` shows that the manifest was created in `e7a98ae` and that **every engine's `lab_path` has remained `null` in every committed revision**. In particular, no committed OptiQ `lab_path` default could have activated the defect before the machine-local file existed.
- `a9b5c46b4c6b22509244dfafb8e24bf5e99b9d84` (`2026-10-30T13:23:28-04:00`, `2026-10-30T17:23:28Z`) added the machine-local `lab-paths.json` reader to `_engine_env`. This is separate from the earlier shared-prefix mechanism: the former supplies this Mac's OptiQ path, while the latter applied all supplied lab prefixes to every engine.

### OptiQ installation and registration evidence

All times in this timeline are consistent; UTC is used for comparisons, with local time (UTC-04:00 on this date) included where the filesystem evidence was reported that way.

| Evidence | Instant | What it establishes |
|---|---|---|
| `a9b5c46` commit | `2026-10-30T17:23:28Z` (`13:23:28` local) | Machine-local lab paths could be consumed by the harness. |
| `engines/optiq-0.5.13` birth time | `2026-10-30T17:23:50Z` (`13:23:50` local) | The OptiQ lab directory existed. Directory birth alone does not prove that its `bin` directory was registered on PATH. |
| `install-log.jsonl`: `create-venv`, exit 0 | `2026-10-30T17:23:51.931540Z` | Creation of the OptiQ lab venv succeeded. |
| `install-log.jsonl`: `install`, exit 0 | `2026-10-30T17:24:09.324450Z` | Installation into that venv succeeded. |
| `install-log.jsonl`: `done` | `2026-10-30T17:24:09.324741Z` | The install operation completed successfully. |
| `lab-paths.json` birth and modification time | `2026-10-30T17:24:21Z` (`13:24:21` local) | Direct filesystem evidence that the machine-local registration file existed by this instant. It names only `optiq` and its `engines/optiq-0.5.13/bin` directory. |

**Earliest defensible instant for the conservative audit window:** `2026-10-30T17:24:09.324741Z`, the successful install completion after local-lab support had landed and the OptiQ venv had been created. The first direct proof of the registration file is 12 seconds later, at `2026-10-30T17:24:21Z`.

This distinction does not hide false precision. `record_lab_path` writes `lab-paths.json` through `atomic_write_text`, which replaces the file, so its observed birth time is the **last** write, not necessarily the first. The successful-install event is therefore used as the earliest defensible conservative bound, while `17:24:21Z` is the earliest direct filesystem proof. No measured run starts in that 12-second interval, so the residual uncertainty changes no verdict.

The October 29 canary is before this entire machine-local installation window. The November 2 and November 3 app runs are after it. For all three, direct runtime-log evidence supersedes a date-only inference.

### The stack difference

The row label `mlx-lm 0.31.3` does not distinguish these environments:

| Environment | mlx-lm | mlx | transformers |
|---|---|---|---|
| OptiQ lab `engines/optiq-0.5.13` | 0.31.3 | **0.32.4** | **5.12.1** |
| Dedicated control `~/.local/share/ohyesmlx/mlx-lm-0.31.3` | 0.31.3 | **0.32.2** | **5.17.0** |

Thus an affected row did run mlx-lm 0.31.3, but not with the dedicated control's recorded mlx and transformers stack. This violates the single-axis requirement even though the reported mlx-lm version string is unchanged.

## Run inventory

Paths are abbreviated as follows:

- `R` = `/Users/jrazz/Dev/active/OhYesMLX/results`
- `Q` = `/Users/jrazz/Library/Application Support/OhYesMLX/quickbench`
- `L` = `/Users/jrazz/Dev/active/OhYesMLX/results/logs`

Start times are UTC. For ordinary runs they come from the run directory's UTC start identifier. For the app runs, `summary.json` supplies `best.measured_at` with fractional seconds and corroborates the directory identifier. The header's harness revision is its `version` plus `source_sha256`; that digest is a hash of the harness Python source, **not a git commit SHA**. `not recorded` means the first-line header has no `harness` object.

Evidence codes:

- **P** — the run predates `e7a98ae`; the shared-prefix implementation did not yet exist.
- **C** — cold and warm runtime logs both resolve `mlx_lm/server.py` to the dedicated `~/.local/share/ohyesmlx/mlx-lm-0.31.3` control venv.
- **O** — cold and warm runtime logs both resolve `mlx_lm/server.py` to `/Users/jrazz/Library/Application Support/OhYesMLX/engines/optiq-0.5.13`; the run also lies inside the conservative lab-path window.

For the citation column, `none found` means an exact run-directory-name search over the pre-existing `docs/research/` documents returned no file; this audit note is excluded. An em dash means no citation search was required for an unaffected pre-window run.

### Harness digest key

These are the complete `source_sha256` values behind the short labels in the table. Every labelled header reports harness version `0.3.0`.

| Label | Full header `source_sha256` |
|---|---|
| H1 | `07387e201cc53557e5a32490bd1590886b05938f507c6eb2378407d45e8d5604` |
| H2 | `a8ad60e7f76e13c5f2c4b7eaa686989abc60ff2cab5809999f7873ff6ed5c9c1` |
| H3 | `aa510642adcab88a3e3dd01c013d786201dcabb31203387bf09dfc0f052309f9` |
| H4 | `423650119dedde78f0873873e3aa41653999eec59001f4cf16242ab4b5748b92` |
| H5 | `6968456b730692c642201632055cfe3271d07db0df2afeb04458cde8f08427a2` |
| H6 | `6f36eb98b4f3530cd52b44e80da053bafabc541ee6e663f996a268f951389eb6` |
| H7 | `a19203c3eee7eb15bea4b8b793a8313b495e58f0919dd1765e55577b029fb828` |
| H8 | `a92c6a6a89dfe2766345eaa3671c08e8f8ebd2020955e204be154e26269134d5` |
| H9 | `fb8ce3ab4bfaf9eacd88220c0beede3d88ddcadc7371d0101ab2e14c16d9caee` |

### Complete table

| Run dir | Start (UTC) | Harness rev | mlx-lm rows | Verdict | Evidence | Cited by |
|---|---|---|---:|---|---|---|
| `R/20260915T143057Z-runtime` | 2026-09-15T14:30:57Z | not recorded | 1 | not affected | P | — |
| `R/20260915T144415Z-runtime` | 2026-09-15T14:44:15Z | not recorded | 1 | not affected | P | — |
| `R/20260915T144831Z-runtime` | 2026-09-15T14:48:31Z | not recorded | 1 | not affected | P | — |
| `R/20260915T150039Z-runtime` | 2026-09-15T15:00:39Z | not recorded | 1 | not affected | P | — |
| `R/20260915T151218Z-runtime` | 2026-09-15T15:12:18Z | not recorded | 1 | not affected | P | — |
| `R/grid/20260915T200320Z-format` | 2026-09-15T20:03:20Z | not recorded | 12 | not affected | P | — |
| `R/grid/20260916T004734Z-format` | 2026-09-16T00:47:34Z | not recorded | 12 | not affected | P | — |
| `R/grid/20260916T034308Z-format` | 2026-09-16T03:43:08Z | not recorded | 12 | not affected | P | — |
| `R/grid-moe/20260916T071532Z-format` | 2026-09-16T07:15:32Z | not recorded | 12 | not affected | P | — |
| `R/sweep-conc8/20260916T125834Z-format` | 2026-09-16T12:58:34Z | not recorded | 3 | not affected | P | — |
| `R/sweep-prompt/20260916T170017Z-format` | 2026-09-16T17:00:17Z | not recorded | 1 | not affected | P | — |
| `R/sweep-prompt/20260916T170155Z-format` | 2026-09-16T17:01:55Z | not recorded | 1 | not affected | P | — |
| `R/sweep-prompt/20260916T170416Z-format` | 2026-09-16T17:04:16Z | not recorded | 1 | not affected | P | — |
| `R/sweep-prompt/20260916T170941Z-format` | 2026-09-16T17:09:41Z | not recorded | 1 | not affected | P | — |
| `R/sweep-prompt/20260916T172618Z-format` | 2026-09-16T17:26:18Z | not recorded | 1 | not affected | P | — |
| `R/sweep-cache/20260917T024706Z-format` | 2026-09-17T02:47:06Z | not recorded | 1 | not affected | P | — |
| `R/sweep-cache/20260917T025229Z-format` | 2026-09-17T02:52:29Z | not recorded | 1 | not affected | P | — |
| `R/sweep-cache-nonhybrid/20260917T162610Z-format` | 2026-09-17T16:26:10Z | not recorded | 1 | not affected | P | — |
| `R/sweep-cache-nonhybrid/20260917T163922Z-format` | 2026-09-17T16:39:22Z | not recorded | 1 | not affected | P | — |
| `R/grid-35b/20260920T000155Z-format` | 2026-09-20T00:01:55Z | not recorded | 9 | not affected | P | — |
| `R/harden-2026-09-23/grid-35b/20260924T031838Z-format` | 2026-09-24T03:18:38Z | 0.3.0 / H1 | 9 | not affected | P | — |
| `R/harden-2026-09-23/grid-dense/20260924T054057Z-format` | 2026-09-24T05:40:57Z | 0.3.0 / H1 | 12 | not affected | P | — |
| `R/harden-2026-09-23/grid-moe/20260924T081417Z-format` | 2026-09-24T08:14:17Z | 0.3.0 / H1 | 12 | not affected | P | — |
| `R/sweep-kvquant/oq4__mlxlm/p16384/20260925T051131Z-format` | 2026-09-25T05:11:31Z | 0.3.0 / H2 | 1 | not affected | P | — |
| `R/sweep-kvquant/oq4__mlxlm/p16384/20260925T052827Z-format` | 2026-09-25T05:28:27Z | 0.3.0 / H2 | 1 | not affected | P | — |
| `R/sweep-kvquant/oq4__mlxlm/p16384/20260925T052838Z-format` | 2026-09-25T05:28:38Z | 0.3.0 / H2 | 1 | not affected | P | — |
| `R/sweep-kvquant/oq4__mlxlm/p32768/20260925T052850Z-format` | 2026-09-25T05:28:50Z | 0.3.0 / H2 | 1 | not affected | P | — |
| `R/sweep-kvquant/oq4__mlxlm/p32768/20260925T060200Z-format` | 2026-09-25T06:02:00Z | 0.3.0 / H2 | 1 | not affected | P | — |
| `R/sweep-kvquant/oq4__mlxlm/p32768/20260925T060211Z-format` | 2026-09-25T06:02:11Z | 0.3.0 / H2 | 1 | not affected | P | — |
| `R/multiturn/20260925T131430Z-runtime` | 2026-09-25T13:14:30Z | 0.3.0 / H2 | 10 | not affected | P | — |
| `R/harden-35b-r3/20260925T221741Z-format` | 2026-09-25T22:17:41Z | 0.3.0 / H3 | 9 | not affected | P | — |
| `R/sweep-conc-seedless/oq4__mlxlm/20260927T065624Z-format` | 2026-09-27T06:56:24Z | 0.3.0 / H4 | 3 | not affected | P | — |
| `R/sweep-conc-seedless/oq4__mlxlm/20260927T070250Z-format` | 2026-09-27T07:02:50Z | 0.3.0 / H4 | 3 | not affected | P | — |
| `R/sweep-conc-seedless/oq4__mlxlm/20260927T071157Z-format` | 2026-09-27T07:11:57Z | 0.3.0 / H4 | 3 | not affected | P | — |
| `R/sweep-conc-seedless/oq4__mlxlm/20260927T072639Z-format` | 2026-09-27T07:26:39Z | 0.3.0 / H4 | 3 | not affected | P | — |
| `R/harden-2026-09-27-seedless/grid-35b/20260928T020107Z-format` | 2026-09-28T02:01:07Z | 0.3.0 / H5 | 9 | not affected | P | — |
| `R/harden-2026-09-27-seedless/grid-dense/20260928T043415Z-format` | 2026-09-28T04:34:15Z | 0.3.0 / H5 | 12 | not affected | P | — |
| `R/harden-2026-09-27-seedless/grid-moe/20260928T071834Z-format` | 2026-09-28T07:18:34Z | 0.3.0 / H5 | 12 | not affected | P | — |
| `R/harden-2026-09-28-cacheoff/grid-dense/20260929T071829Z-format` | 2026-09-29T07:18:29Z | 0.3.0 / H6 | 12 | not affected | P | — |
| `R/harden-2026-09-28-cacheoff/grid-moe/20260929T095526Z-format` | 2026-09-29T09:55:26Z | 0.3.0 / H6 | 12 | not affected | P | — |
| `R/sweep-conc-cacheoff/oq4__mlxlm/20260929T113217Z-format` | 2026-09-29T11:32:17Z | 0.3.0 / H6 | 3 | not affected | P | — |
| `R/sweep-conc-cacheoff/oq4__mlxlm/20260929T114047Z-format` | 2026-09-29T11:40:47Z | 0.3.0 / H6 | 3 | not affected | P | — |
| `R/sweep-conc-cacheoff/oq4__mlxlm/20260929T115316Z-format` | 2026-09-29T11:53:16Z | 0.3.0 / H6 | 3 | not affected | P | — |
| `R/sweep-conc-cacheoff/oq4__mlxlm/20260929T121319Z-format` | 2026-09-29T12:13:19Z | 0.3.0 / H6 | 3 | not affected | P | — |
| `R/canary/20261029T201017Z-mlxlm` | 2026-10-29T20:10:17Z | 0.3.0 / H7 | 1 | not affected | C; pre-install | none found |
| `Q/20261102T225004Z` (`A/mlxlm`) | 2026-11-02T22:50:04.036767Z | 0.3.0 / H8 | 1 | **affected** | O | none found |
| `Q/20261103T164018Z` (`A/mlxlm`) | 2026-11-03T16:40:18.855368Z | 0.3.0 / H9 | 1 | **affected** | O | none found |

### Direct executable evidence for every post-`e7a98ae` candidate

The first line of each named log is the `mlx_lm.server` warning that includes the executing module's full `site-packages` path. Cold and warm visits agree in every case.

| Run | Runtime logs, all line 1 | Executing tree |
|---|---|---|
| `R/canary/20261029T201017Z-mlxlm` | `L/mlxlm-20261029T161017-77789.log`, `L/mlxlm-20261029T161308-77789.log` | `/Users/jrazz/.local/share/ohyesmlx/mlx-lm-0.31.3/lib/python3.14/site-packages/mlx_lm/server.py` |
| `Q/20261102T225004Z` | `L/mlxlm-20261102T175004-49734.log`, `L/mlxlm-20261102T175045-49734.log` | `/Users/jrazz/Library/Application Support/OhYesMLX/engines/optiq-0.5.13/lib/python3.14/site-packages/mlx_lm/server.py` |
| `Q/20261103T164018Z` | `L/mlxlm-20261103T114018-70396.log`, `L/mlxlm-20261103T114058-70396.log` | `/Users/jrazz/Library/Application Support/OhYesMLX/engines/optiq-0.5.13/lib/python3.14/site-packages/mlx_lm/server.py` |

The log timestamps also join the app records to the shared runtime-log directory: `20261102T175004` is `2026-11-02T22:50:04Z`, and `20261103T114018` is `2026-11-03T16:40:18Z`. These are the exact start identifiers of the two quickbench runs.

## What this does and does not change

- **Nothing is discarded, rewritten, moved, truncated, or re-scored.** All raw observations and all original result rows remain in place. This note adds an attribution caveat; it does not alter a status or a measured value.
- **The two affected mlx-lm rows must not be described as measurements of the dedicated control stack.** They measured mlx-lm 0.31.3 with mlx 0.32.4 and transformers 5.12.1 from OptiQ's lab venv, not mlx 0.32.2 and transformers 5.17.0 from the dedicated control. The speed or memory effect of that stack substitution is unknown and was not measured here.
- **Any published figure that cites either affected run carries this caveat.** In particular, an mlx-lm control figure from `20261102T225004Z` or `20261103T164018Z` cannot support a runtime-only or format-only attribution without disclosing the second stack difference. No pre-existing `docs/research/` document other than this audit note cites either affected run directory by name, so this audit identifies no existing research document requiring a run-name-specific correction.
- **The other 214 rows need no S5-F1 caveat.** The September rows predate the mechanism. The October 29 canary has direct evidence for the intended control venv.
- **This verdict is specific to mlx-lm rows.** It neither reclassifies the other engines' rows in the two quickbench runs nor claims that an OptiQ row was wrong to use OptiQ's own lab venv.
- **This is not a claim that the numbers moved, or by how much.** The defect is lost attribution under the one-variable rule. No remeasurement, package benchmark, or performance adjustment was performed.

## Method and limits

1. **Discovery and counts.** A recursive search of `/Users/jrazz/Dev/active/OhYesMLX/results` for files named exactly `results.jsonl` selected those containing a JSON `"runtime": "mlxlm"` field (with arbitrary JSON whitespace). Each matching observation line was counted once per file. The same selection was made under both app quickbench runs. This found 45 ordinary result files (214 rows) and two app `A/mlxlm/results.jsonl` files (one row each), reconciling to 47 runs and 216 rows. Files with no mlx-lm row contribute no table entry.
2. **Run metadata.** The first line of each selected file supplied `harness.version` and `harness.source_sha256` when present. Run-start UTC identifiers came from directory names; quickbench `summary.json` supplied the fractional `measured_at` values. No missing historical harness digest was treated as a missing date: all 20 early headers without a `harness` object still belong to run directories whose starts predate `e7a98ae` by more than a month.
3. **Window evidence.** Git history supplied the shared-prefix commit, machine-local reader commit, and every manifest `lab_path` value. The install log supplied successful creation/install/completion events. `stat` supplied the lab directory and registration-file times. The conservative window begins at successful install completion, with the registration file's atomic-replacement limitation stated explicitly.
4. **Direct evidence.** For every run after `e7a98ae`, the cold and warm `mlxlm` runtime logs were checked for the executing `mlx_lm/server.py` path. This direct evidence, rather than a date-only inference, decides the canary and two app verdicts. There were no other post-window candidates to leave undetermined.
5. **Citations.** Exact searches for `20261102T225004Z` and `20261103T164018Z` over `docs/research/`, excluding this new audit note, returned no files. `20261029T201017Z-mlxlm` was also checked and returned no files. A document that uses an export without naming its source run, or a publication outside `docs/research/`, is outside what an exact run-name search can discover; the caveat above applies to any such figure if it derives from either affected run.
6. **Limits.** The audit covers the existing on-disk corpus named in the order, not deleted runs or other machines. It does not execute either Python environment, start a server, load a model, analyze tensors, download anything, or recompute measurements. The established package-version facts are reported, not re-derived. A header `source_sha256` is reproduced as the harness revision and is not claimed to identify a git commit.
7. **Read-only checks.** `git -C /Users/jrazz/Dev/active/OhYesMLX status --porcelain results/` was empty before and after the audit. Quickbench directory modification times were checked before and after and remained `2026-11-02 17:58:51 -0500` for `20261102T225004Z` and `2026-11-03 12:12:55 -0500` for `20261103T164018Z`.
