# Recovering the Osaurus MoE MMLU score: an extraction defect, measured offline

Date: 2026-09-19. **No new measurement.** Nothing in this document was measured for it: no
runtime was started, no model was loaded, no benchmark item was re-run, no tensor was read, and
no sample row was altered. Every number is recomputed from the 57 sample files this repository
already holds.

Recovery tool: [`scripts/rescore_moe_mmlu.py`](file:///Users/jrazz/Dev/active/OhYesMLX/scripts/rescore_moe_mmlu.py).
Machine-readable output: `results/accuracy-moe/study-2c/jang2l__osaurus/mmlu_rescored.json`.

This note corrects nothing in the record and supersedes no number in it. Plan 02-03's published
MMLU figure for this cell stays **3.77%**, because that is what the instrument produced; §6 says
what the recovered figure may and may not be read against.

---

## 1. The defect

`jang2l__osaurus` is the Study 2C cross-runtime leg of Plan 02-03
([`2026-09-19-accuracy-moe.md`](2026-09-19-accuracy-moe.md) §1.1, §2.2): `LFM2.5-8B-A1B` in
`JANG_2L`, served by Osaurus 0.25.6, 2h 24m 53s of wall clock (11:21:44 → 13:46:37 UTC,
1h 30m 33s of it MMLU) culminating in all three tasks complete
and `status: PASS`. Its MMLU result was **3.77%, 43 of 1,140 items** — a number below chance for a
four-option multiple-choice task.

The cause is not the model. lm-eval 0.4.13's `mmlu_generative` task scores with the `get_response`
filter, whose first operation is a regex taking the first line of the completion:

```
^(.*?)(?=\n|$)
```

That pattern reduces every completion to its **first line**. This artifact does not answer on its
first line. It answers in a conventional `Answer: X` trailer after a paragraph of reasoning, so
what lm-eval compared against the key was, for most items, the opening sentence of an explanation.
The filter is a sensible default for a model that emits a bare letter and a silent failure for one
that writes an answer sentence.

**704 of the 1,140 completions name an answer on a line after the first** — invisible to the
filter. The distribution of the *scored* string explains the 43:

| form of the scored string | items | score under `exact_match` |
|---|---|---|
| prose of more than a bare letter | **845** | 0, however correct |
| empty output | 171 | 0 |
| reduced to a bare letter | 124 | 43 matched the key (34.7%) |

(Identical to the table already published at `2026-09-19-accuracy-moe.md` §2.2 and reproduced here
because the recovery is read against it.)

## 2. What was thrown away: three verbatim false negatives

Each of these is one item, keyed correctly, scored 0, and quoted from the sample rows. The scored
string is what lm-eval saw; the tail is what the model actually said.

**`public_relations`, `doc_id` 0, key `B`** — *"Which common public relations tactic involves
sending journalists on visits to appropriate locations?"*

- scored: `The question asks which common public relations tactic involves sending journalists on visits to appropriate l…`
- emitted: `…experience the organization's facilities or initiatives firsthand, ensuring accurate and timely information dissemination.` **`Answer: B. Media tour`**

**`astronomy`, `doc_id` 2, key `C`** — *"Why is the sky blue?"*

- scored: `The sky appears blue due to Rayleigh scattering, where atmospheric molecules scatter shorter (blue) wavelength…`
- emitted: `…the atmosphere itself does not have a blue color, the sky is not a reflection of the oceans, and Mars' surface minerals are unrelated to the sky's color.` **`Answer: C`**

**`abstract_algebra`, `doc_id` 19, key `A`**

- scored: `The ring 2Z (the set of even integers) is an infinite ring, and the characteristic of an infinite ring is 0. T…`
- emitted: `…Therefore, the correct answer is **A. 0**.` **`Answer: A`**

The `**Answer: B. Media tour**` form is the artifact's dominant shape, and it is the one the
`^(.*?)(?=\n|$)` rule is least equipped for: the answer is real, it is unambiguous, and it is on
the last line.

## 3. Extraction methodology

The recovery re-reads each completion with a five-pattern cascade, tried in priority order. Within
a pattern the **last** (rightmost) match wins, because the artifact restates its choice at the end
of an explanation and any earlier mention is usually the option list or a rejected candidate.

| priority | rule | pattern |
|---|---|---|
| 1 | `stated_answer` | `(?:Answer\|answer):\s*(?:\*\*)?([A-D])(?:\*\*)?(?:\.\|\b)` |
| 2 | `lettered_option` | `\b([A-D])\.\s+[A-Za-z]` — e.g. `B. Media tour` |
| 3 | `bold_letter` | `\*\*([A-D])\*\*` |
| 4 | `correct_answer_is` | `(?i:the correct answer is\s+(?:\*\*)?([A-D]))` |
| 5 | `isolated_letter` | `(?<![A-Za-z])[A-D](?![A-Za-z])` — last isolated letter |

- **Empty responses score 0.0**, and are counted separately from responses that name no letter at
  all, so "said nothing" is never confused with "said something unreadable".
- **Text is the full completion** (`resps[0][0]`); the baseline is read from lm-eval's own
  `filtered_resps`, so the two numbers differ only in the string they read.
- **Nothing is discarded.** The 171 empty and 13 truncated completions stay in the record and in
  the denominator.

## 4. The recovered score

| | items | score | 95% Wilson |
|---|---|---|---|
| **baseline** — strict equality on lm-eval's filtered string | 43 / 1,140 | **3.77%** | [2.81%, 5.04%] |
| **recovered** — cascade on the full completion | 481 / 1,140 | **42.19%** | [39.36%, 45.08%] |

The baseline reproduces lm-eval's reported `0.037719298245614034` exactly, which is the
reconciliation the tool refuses to publish without: it exits non-zero and writes nothing if the
43 does not come back.

**The recovery is a strict widening, not a swap.** `baseline hits lost: 0` — every one of the 43
items lm-eval matched is also matched by the cascade, and 438 further items are recovered. A
recovery that lost baseline hits would be a different instrument, not a better reading of the same
one.

Per-pattern usage, which shows where the recovery comes from:

| priority | rule | items used | correct | accuracy |
|---|---|---|---|---|
| 1 | `stated_answer` | 742 | 395 | 53.2% |
| 2 | `lettered_option` | 70 | 36 | 51.4% |
| 3 | `bold_letter` | 8 | 2 | 25.0% |
| 4 | `correct_answer_is` | 1 | 0 | 0.0% |
| 5 | `isolated_letter` | 135 | 48 | 35.6% |

Pattern 1 carries the result and is also the most accurate: where the model says `Answer: X`
outright it is right 53.2% of the time. Pattern 2 exists for the `**Answer: B. Media tour**`
family, where a bolded option restates the letter.

**Unscored: 184 items (16.1%)** — 171 empty completions and 13 truncated at `max_gen_toks` without
ever naming a letter. Both score 0.0 in every reading here. The 171 empties are empty in the
recorded **content** channel; the sample files do not retain the reasoning channel, so whether the
model answered there is not recoverable from these files and is not claimed.

**Extracted vs. keyed distribution.** The extraction is not visibly degenerate — it does not
collapse onto one letter, and its shape is close to the key's:

| | A | B | C | D | none |
|---|---|---|---|---|---|
| **extracted** | 215 | 232 | 229 | 280 | 184 |
| **targets** | 274 | 291 | 284 | 291 | — |

### 4.1 Subject-by-subject

Full table, sorted by subject name. Every subject is 20 items.

| subject | n | baseline | recovered | + |
|---|---|---|---|---|
| `abstract_algebra` | 20 | 1/20 | 3/20 | +2 |
| `anatomy` | 20 | 2/20 | 6/20 | +4 |
| `astronomy` | 20 | 0/20 | 12/20 | +12 |
| `business_ethics` | 20 | 1/20 | 10/20 | +9 |
| `clinical_knowledge` | 20 | 0/20 | 4/20 | +4 |
| `college_biology` | 20 | 1/20 | 12/20 | +11 |
| `college_chemistry` | 20 | 0/20 | 7/20 | +7 |
| `college_computer_science` | 20 | 1/20 | 5/20 | +4 |
| `college_mathematics` | 20 | 0/20 | 2/20 | +2 |
| `college_medicine` | 20 | 1/20 | 11/20 | +10 |
| `college_physics` | 20 | 0/20 | 9/20 | +9 |
| `computer_security` | 20 | 1/20 | 9/20 | +8 |
| `conceptual_physics` | 20 | 1/20 | 10/20 | +9 |
| `econometrics` | 20 | 1/20 | 6/20 | +5 |
| `electrical_engineering` | 20 | 0/20 | 3/20 | +3 |
| `elementary_mathematics` | 20 | 0/20 | 14/20 | +14 |
| `formal_logic` | 20 | 1/20 | 4/20 | +3 |
| `global_facts` | 20 | 3/20 | 4/20 | +1 |
| `high_school_biology` | 20 | 2/20 | 10/20 | +8 |
| `high_school_chemistry` | 20 | 0/20 | 6/20 | +6 |
| `high_school_computer_science` | 20 | 0/20 | 10/20 | +10 |
| `high_school_european_history` | 20 | 1/20 | 12/20 | +11 |
| `high_school_geography` | 20 | 0/20 | 11/20 | +11 |
| `high_school_government_and_politics` | 20 | 2/20 | 12/20 | +10 |
| `high_school_macroeconomics` | 20 | 0/20 | 3/20 | +3 |
| `high_school_mathematics` | 20 | 0/20 | 5/20 | +5 |
| `high_school_microeconomics` | 20 | 1/20 | 9/20 | +8 |
| `high_school_physics` | 20 | 0/20 | 6/20 | +6 |
| `high_school_psychology` | 20 | 0/20 | 10/20 | +10 |
| `high_school_statistics` | 20 | 1/20 | 6/20 | +5 |
| `high_school_us_history` | 20 | 0/20 | 11/20 | +11 |
| `high_school_world_history` | 20 | 0/20 | 16/20 | +16 |
| `human_aging` | 20 | 2/20 | 8/20 | +6 |
| `human_sexuality` | 20 | 1/20 | 9/20 | +8 |
| `international_law` | 20 | 0/20 | 14/20 | +14 |
| `jurisprudence` | 20 | 1/20 | 13/20 | +12 |
| `logical_fallacies` | 20 | 0/20 | 8/20 | +8 |
| `machine_learning` | 20 | 2/20 | 8/20 | +6 |
| `management` | 20 | 2/20 | 11/20 | +9 |
| `marketing` | 20 | 3/20 | 8/20 | +5 |
| `medical_genetics` | 20 | 2/20 | 13/20 | +11 |
| `miscellaneous` | 20 | 1/20 | 13/20 | +12 |
| `moral_disputes` | 20 | 0/20 | 6/20 | +6 |
| `moral_scenarios` | 20 | 0/20 | 6/20 | +6 |
| `nutrition` | 20 | 1/20 | 10/20 | +9 |
| `philosophy` | 20 | 1/20 | 8/20 | +7 |
| `prehistory` | 20 | 1/20 | 10/20 | +9 |
| `professional_accounting` | 20 | 0/20 | 4/20 | +4 |
| `professional_law` | 20 | 0/20 | 6/20 | +6 |
| `professional_medicine` | 20 | 0/20 | 10/20 | +10 |
| `professional_psychology` | 20 | 0/20 | 8/20 | +8 |
| `public_relations` | 20 | 0/20 | 6/20 | +6 |
| `security_studies` | 20 | 0/20 | 9/20 | +9 |
| `sociology` | 20 | 2/20 | 5/20 | +3 |
| `us_foreign_policy` | 20 | 2/20 | 11/20 | +9 |
| `virology` | 20 | 1/20 | 5/20 | +4 |
| `world_religions` | 20 | 0/20 | 14/20 | +14 |

**No subject recovers by nothing** — the weakest, `college_mathematics`, still recovers 2 of 20.
Empty completions and recovery are related but are not the same story: across the 57 subjects the
two are negatively correlated (Pearson **r = −0.568**), which is what one expects, since an item
with no text has nothing to extract. The emptiest subjects are the emptiest recoveries —
`college_mathematics` (17 empty, 2 recovered), `formal_logic` (14, 4), `high_school_mathematics`
(13, 5), `abstract_algebra` (11, 3).

But not every weak subject is empty-limited, and reading it that way would be a mistake:
`high_school_macroeconomics` recovers 3 of 20 with only **3** empty completions, and
`electrical_engineering` 3 of 20 with **6**. Those are subjects where the model wrote a full
explanation and named the wrong letter — extraction cannot help, because there is nothing wrong
with the reading. Conversely **18 of 57 subjects have no empty completions at all**
(`anatomy`, `astronomy`, `college_biology`, `computer_security`, `high_school_biology`,
`high_school_european_history`, `high_school_geography`, `human_sexuality`, `jurisprudence`,
`logical_fallacies`, `management`, `marketing`, `miscellaneous`, `moral_disputes`, `philosophy`,
`prehistory`, `security_studies`, `virology`).

The largest recoveries are `high_school_world_history` (+16), then `elementary_mathematics`,
`international_law` and `world_religions` (+14 each) — subjects where the artifact answered at
length and answered correctly.

## 5. Where this sits against the other two cells

| cell | runtime | MMLU (n=1,140) | what the number is |
|---|---|---|---|
| `jang2l__vmlx` | vMLX 1.6.59 | **no score** | halted at item 80 on `requests.exceptions.HTTPError: 502 Server Error: Bad Gateway for url: http://127.0.0.1:8000/v1/chat/completions` (`mmlu_generative/lm_eval_output.txt:575`). No samples file was written at all — the task scored zero items, not a low score. |
| `stock4bit__vmlx` | vMLX 1.6.59 | **35.53%** | lm-eval `exact_match,get_response`; replicated exactly in the second pass (`replicate/stock4bit__vmlx`, 0.35526315789473684, PASS). |
| `jang2l__osaurus` | Osaurus 0.25.6 | **3.77%** published / **42.19%** recovered | this note. |

Three things are worth saying plainly.

**`jang2l__vmlx` has no MMLU number and cannot be given one.** Its task died on a 502 from the
runtime before writing a single sample row, so there are no completions to recover from. The
recovery path in this note needs rows; that cell has none. This is the difference between *the
instrument failed* and *the model failed*, and only the first one is recoverable offline.

**`stock4bit__vmlx`'s 35.53% is the number worth comparing against**, because it is the one other
MoE cell that completed MMLU with a full 1,140 rows and reproduced its own score.

**And the comparison is still not a like-for-like one.** 35.53% is an lm-eval `exact_match` score
produced by the pre-registered instrument on completions that mostly were bare letters; 42.19% is
an offline re-reading of this cell's prose under the extraction rule in §3. The two numbers come
from two different extraction instruments applied to two different artifacts. The direction of the
gap is informative — the Osaurus cell's stored outputs contain more correct answers than the
published 3.77% counted, and after recovery this cell reads *above* the `stock4bit` vMLX cell —
but the gap is not a measured Δ and §6 says why it cannot be published as one.

## 6. Attribution, and the limits of this number

**Attribution.** Every figure here is an **offline recovery from completed, verified model
outputs**. The 1,140 rows under `results/accuracy-moe/study-2c/jang2l__osaurus/mmlu_generative/`
were produced by a real, canary-gated Osaurus 0.25.6 run (`status: PASS`, `port_released: true`,
`cold_load_s: 1.262`, manifest `completed_at: 2026-09-19T13:46:37Z`). This note re-reads those
rows. It does not re-run the benchmark, does not re-load the model, and does not change a single
stored byte — including the 171 empty completions and the 13 truncated ones, which stay in the
denominator exactly as the record has them.

**What the recovered number is.** The best available estimate of what this cell's own stored
outputs say the model chose, under one stated extraction rule, with the baseline it was recovered
from printed beside it.

**What it is not.**

- **It is not a replacement for the published 3.77%.** The study's number is what the
  pre-registered instrument produced and it stays in the record labelled as instrument-limited.
- **It is not a measurement of the model.** It cannot distinguish answers the model could not
  produce from answers the filter could not read, and 16.1% of items have no text to read at all.
- **It is not a licence for a Δ, a Pareto position, or a cross-runtime claim.** The design
  ([`2026-09-17-v2-track2-accuracy-study-design.md`](2026-09-17-v2-track2-accuracy-study-design.md))
  draws those only from scores the pre-registered instrument produced. 42.19% clears the design's
  25% four-option floor that 3.77% failed, and clearing a floor makes a number readable, not
  comparable.
- **It is not exact.** Patterns 2 and 5 are permissive by construction: a completion that lists
  options and then declines to choose can still yield a letter, and one that names a letter inside
  prose can yield the wrong one. 35.6% accuracy on the 135 items pattern 5 had to catch is what
  that costs. A stricter rule would recover less; this rule is what §3 specifies and the number
  above is what it gives.

**The tool's own check.** `scripts/rescore_moe_mmlu.py` refuses to write its summary and exits
non-zero unless the strict-equality baseline reproduces lm-eval's 43/1,140, and its `--self-test`
mode pins each of the five patterns, the priority order, the last-match-wins rule, the empty and
truncated cases, and the A–D range of every extraction.

## 7. Reproducing this

```sh
/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python scripts/rescore_moe_mmlu.py --self-test
/Users/jrazz/.claude/jobs/1704c764/tmp/verify-venv/bin/python scripts/rescore_moe_mmlu.py
```

The second command recomputes both scores from the 57 sample files and writes
`results/accuracy-moe/study-2c/jang2l__osaurus/mmlu_rescored.json`. It is stdlib-only and touches
no network, no port and no model.
