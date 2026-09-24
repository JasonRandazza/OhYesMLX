"""``ohyesmlx run --study runtime --cells <cell>,<cell> [--rank <metric>]``.

One selector, one axis, one table per workload, one named ordering metric. ``--cells`` is the
only way to say which cells run: there is no config-file selector, no profile, no lineup, and
there will not be a second one. Each entry is ``<format>__<runtime>=<artifact dir>`` — the
``Cell.id`` convention — and ``--study`` says which of those two variables the run is allowed
to vary. A selection that varies both is refused before a runtime is started, because a number
that changed two things is not a result.

``--rank`` picks the single metric the tables are ordered by, and there is no blend of them:
weighting a second of latency against a megabyte has no objective answer, so the ordering
names its metric and the metric card carries every number behind it.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from ohyesmlx import __version__, report, token_counter
from ohyesmlx.runtimes import CACHE_STATES, KV_QUANTS, MTP_DEPTHS, STREAM_EXPERTS

STUDIES = report.AXES

CELLS_HELP = (
    "comma-separated cells, each `<format>__<runtime>=<artifact dir>`, "
    "e.g. oq4__mlxlm=~/.cache/huggingface/hub/models--avneetsb--gemma-4-12B-it-qat-oQ4-fp16"
)

# The two workload sets `--workloads` chooses between. `pinned` is the default and the three
# shapes of v1; `multiturn` is the ten turns of `DIALOGUE`. The set is a selector and not a pin,
# the way `--prompt-tokens` is a selector: the run header already lists every workload the run
# measured with its own messages and `max_tokens`, so the shapes are the provenance and a name
# for them would be a second copy of the same fact.
WORKLOAD_SETS = ("pinned", "multiturn")

# Pinned for v1: three workload shapes, and no more. One shape measures one corner of the
# space, and a column keyed by shape is the only honest way to publish them: prefill-heavy and
# decode-heavy work can have different winners, so a figure averaged across shapes describes
# no shape that was ever run. measure.py pins temperature 0 and a fixed seed; the prompts and
# the output caps live here so two runs are the same two runs.
#
# `chat` is the short prompt with a 128-token cap: latency and per-request overhead.
PROMPT = (
    "Explain why a benchmark that changes two variables at once cannot attribute a "
    "difference to either one. Give one concrete example."
)

# `prefill` is the long prompt with a 64-token cap: prompt-processing throughput. The excerpt
# below is 6,485 characters, roughly 1,600 tokens at four characters per token and ~12x the
# `chat` prompt. That is what makes it dominate the request: at a 400 tok/s prefill engine the
# prompt path is about 4 s, so fixed per-request overhead is a couple of percent of TTFT
# instead of a third of it, and `prompt_tokens / ttft_s` measures prompt processing rather
# than the cost of asking. A longer prompt would buy a fraction of a percent that a 5-sample
# median cannot resolve, at ~1.5 s more prefill on each of the 16 prefill requests a cell
# makes in a run. A read-and-answer task rather than a generative one, so the 64-token cap is
# enough to answer it coherently.
PREFILL_PROMPT = (
    "Read the engineering standard below in full, then answer the question at the end in "
    "one sentence.\n\n"
    "--- BEGIN EXCERPT: Measurement Standard MS-7 ---\n\n"
    "1. Scope. This standard governs every performance figure this organisation publishes "
    "about software it runs on hardware it owns, whether that figure appears in a changelog, "
    "a design review, a sales deck, or a comment in a source file. It applies to latency, "
    "throughput, memory, disk, cost, and every derived ratio built from them. A figure that "
    "cannot be traced to a run recorded under this standard is not evidence, and quoting one "
    "as though it were is a breach of the standard rather than an oversight in it.\n\n"
    "2. The single-variable rule. A comparison varies exactly one thing. Every other input "
    "that can move the measurement is pinned and written down: the software version, the "
    "hardware, the operating system, the model or data set, the request shape, the number of "
    "repetitions, the seeding, the cache state, and the ambient conditions where they matter. "
    "If two things differ between the runs being compared, the comparison answers no question "
    "at all, because any difference observed could belong to either variable and nothing in "
    "the numbers can apportion it between them.\n\n"
    "3. Why the rule is not negotiable. The rule is not a matter of taste or of neatness. It "
    "is what makes a difference attributable. A benchmark that moves two things at once "
    "produces a number that is real, reproducible, and useless: real because the machine did "
    "the work it did, reproducible because a rerun moves the same two things again, and "
    "useless because the reader cannot act on it. The reader's question is always which of two "
    "choices to make, and a figure that cannot separate the choices cannot answer it.\n\n"
    "4. Pinning. Everything held constant is recorded with the run rather than remembered by "
    "the person who ran it. A pin that lives only in someone's head is not a pin; it is a "
    "detail that will differ next month without anyone noticing. Recorded pins include the "
    "exact build, the exact weights including the file digest where one exists, the hardware "
    "model and its memory configuration, the power source as well as the charge state, and the "
    "version of every tool in the measurement path, because a runtime that ships a different "
    "default changes the result without changing a single flag in the command.\n\n"
    "5. Ordering and drift. The order in which configurations are measured is itself an input, "
    "so it is chosen deliberately and never left as the order they happen to be listed in. A "
    "machine that heats up under sustained load will report its first configuration cool and "
    "its last one throttled, which turns a thermal curve into a property of the software with "
    "no warning anywhere in the output. Configuration order is therefore interleaved or "
    "reversed between repetitions, cool-down periods are inserted between them and recorded, "
    "and the drift across the measurement window is kept as a number so a reader can see "
    "whether the window moved underneath the result.\n\n"
    "6. Repetition and distribution. A single request is an anecdote. Reported latency figures "
    "are percentiles with the count they were taken over, never a bare mean, because a mean "
    "hides exactly the queueing behaviour a reader is trying to understand. Where there are "
    "too few samples for a percentile to mean anything, the percentile is omitted and the "
    "count is printed instead of being estimated from three values. Throughput is reported per "
    "request and in aggregate as two separate numbers, since batching improves one and can "
    "worsen the other, and one figure cannot say both.\n\n"
    "7. Cold start. Model load time is its own measurement and is never folded into the first "
    "request. Loading weights from disk, mapping them, and compiling kernels are work that "
    "happens once, and a first-request figure that includes them describes a startup path "
    "rather than a serving path. Cold load is reported separately, alongside a warm-start "
    "figure where one was measured, and a run that reports only the cold case says so in the "
    "same sentence.\n\n"
    "8. Self-reported numbers. A number a server reports about itself is not a measurement. "
    "Servers report durations that were never instrumented, throughput computed from counters "
    "that restart, and token counts rounded to whatever their tokenizer happened to produce. "
    "Such numbers are kept as provenance, labelled as the server's own claim, and never used "
    "as the value in a table. Where a client-side and a server-side figure disagree, the "
    "disagreement is itself evidence and is published rather than smoothed away.\n\n"
    "9. Missing values. A metric that cannot be computed is reported as missing, with the "
    "reason, and never as zero. A zero is a measurement and will be read as one. If a stream "
    "delivered too few deltas for an interval to exist, the interval is undefined rather than "
    "tiny; if a token count is unavailable, the rate is unavailable with it. Printing a "
    "placeholder where a number belongs is how a table of blanks comes to look like a table of "
    "results.\n\n"
    "10. Raw records. Every run keeps its raw observations, including the ones that failed, "
    "the warmups, and the sample that produced the anomaly being investigated later. A summary "
    "is recomputable from the raw record or it is not a summary. Derived values are never "
    "stored beside the fields they were derived from, because two copies of one metric will "
    "eventually disagree and there will be no way to tell which one is right. Retention is not "
    "negotiable on the grounds of size: the record is small next to the cost of re-running a "
    "measurement window that has already passed.\n\n"
    "11. Grouping. A figure belongs to one configuration and one workload. Two configurations "
    "share a table only when the run varied one thing between them; two workloads share a "
    "table only when a reader can tell the workloads apart. Averaging across either grouping "
    "produces a number describing something that was never run, and that number will be quoted "
    "for years because it looks tidy. When in doubt, print more tables rather than fewer, and "
    "let each one say what it varied.\n\n"
    "12. Publication. Every published figure carries the caveat naming what it held constant, "
    "so a reader knows what it cannot claim. A table without that line is not a result, "
    "whatever the numbers in it say. Corrections are published with the same prominence as the "
    "original figure, since a wrong number that has been read once has already done its "
    "damage.\n\n"
    "--- END EXCERPT ---\n\n"
    "Question: which single rule does the standard treat as non-negotiable, and why?"
)

# The ten-turn conversation `--workloads multiturn` measures, as literal role/content pairs:
# the ten questions of `scripts/probe_multiturn_sweep.py`'s DIALOGUE_TURNS, each followed by a
# fixed reply. The replies are literal because the probe this replaces fed each runtime's own
# replies back into the next turn, so every runtime saw a different history and a difference
# between two turns could belong to the history rather than to the runtime. Fixed replies are
# what make turn N the same prompt on every runtime, which is what makes one runtime's turns
# comparable with another's.
DIALOGUE = (
    (
        "user",
        "What are the core differences between monolithic and microservice software "
        "architectures?"
    ),
    (
        "assistant",
        "A monolith is deployed as one process: its modules share memory, a database connection "
        "pool, and a release cycle. A microservice architecture splits that process into "
        "independently deployed services, each owning its data and talking to the others over the "
        "network. The monolith trades granularity of scaling for simpler operations, "
        "transactions, and debugging, since a call between modules stays a function call. "
        "Microservices trade operational complexity for independent scaling and release, and they "
        "make partial failure an ordinary condition rather than an exception. Neither is a "
        "default: the split earns its cost only where independent scaling, team autonomy, or "
        "release cadence actually demands it."
    ),
    (
        "user",
        "Considering those differences, how does service discovery work in a microservice setup?"
    ),
    (
        "assistant",
        "Because instances are created and destroyed dynamically, a client cannot hardcode "
        "addresses. Service discovery keeps a registry of healthy instances, and callers resolve "
        "a logical name to a current address. Registration happens either as instances start and "
        "heartbeat, or through a separate registrar that watches the platform. The registry then "
        "answers queries for the set of healthy endpoints and drops entries that fail their "
        "health checks. Consul, etcd, and Eureka are typical registries. DNS-based discovery is "
        "common in Kubernetes, where a service name resolves to a stable address that the "
        "platform's proxy load balances across the pods behind it."
    ),
    (
        "user",
        "How does client-side service discovery compare to server-side service discovery in terms "
        "of load balancing?"
    ),
    (
        "assistant",
        "In client-side discovery the caller queries the registry directly and picks an instance "
        "itself, so load balancing lives in the client library and the caller knows the full set "
        "of endpoints. It saves a network hop and lets the client apply locality or latency-aware "
        "policies, at the cost of a discovery client in every language and of each client holding "
        "registry state. In server-side discovery the caller sends each request to a stable "
        "address and a router or proxy chooses the instance. That keeps clients simple and "
        "centralises policy and health checking, but it adds a hop and makes the router itself a "
        "component whose scaling and availability must be managed."
    ),
    (
        "user",
        "What consensus algorithms (like Raft or Paxos) are typically used by service registries "
        "like Consul or etcd?"
    ),
    (
        "assistant",
        "Consul and etcd both use Raft; ZooKeeper uses ZAB, which is close in structure to Paxos. "
        "These algorithms keep a replicated log consistent across a quorum of servers, so the "
        "registry has one agreed order of writes. A leader appends entries and replicates them, "
        "and once a majority has stored an entry it is committed and applied to the state machine "
        "that holds the key-value data. Reads are served either from the leader or, with care, "
        "from a follower whose log is known to be current. The quorum requirement is what sets "
        "the tolerance: a three-node cluster survives one failure, a five-node cluster two."
    ),
    (
        "user",
        "Explain the leader election phase in Raft in detail."
    ),
    (
        "assistant",
        "Raft nodes are followers, candidates, or leaders, and every message carries a term "
        "number that only ever increases. A follower that hears nothing from a leader within its "
        "randomised election timeout becomes a candidate, increments the term, votes for itself, "
        "and asks the others for votes. A node grants at most one vote per term, and only to a "
        "candidate whose log is at least as up to date as its own. A candidate holding a majority "
        "becomes leader and starts sending heartbeats. Randomised timeouts make a split vote "
        "unlikely; when one happens the term ends with no leader and a fresh election begins."
    ),
    (
        "user",
        "What happens if a network partition splits the Raft cluster into two equal halves?"
    ),
    (
        "assistant",
        "Neither half can elect a leader, because a majority of the whole cluster is required and "
        "each half holds exactly half the nodes. The cluster stops accepting writes and waits, "
        "which is the safe outcome: no value committed on the minority side can later be lost, "
        "because nothing on that side is ever committed. When the partition heals, the nodes "
        "exchange terms, the side with the higher term or the more complete log wins, and any "
        "uncommitted entry from the old leader is discarded and overwritten by replication from "
        "the new one. Even cluster sizes make this stall likelier, which is why production "
        "clusters use odd numbers of voters."
    ),
    (
        "user",
        "How do vector clocks help detect concurrent updates during network partitions in "
        "distributed key-value stores?"
    ),
    (
        "assistant",
        "A vector clock is a per-node counter vector attached to a value. Each node increments "
        "its own component on every write and carries the incoming vector forward, so the vector "
        "records how many events each node has contributed. Comparing two vectors gives three "
        "cases: one dominates and is therefore newer, or neither dominates and the writes are "
        "concurrent. During a partition two replicas accept writes independently, so their "
        "vectors diverge and neither dominates. On reconciliation the store can tell an overwrite "
        "from a genuine conflict and return both versions rather than silently dropping one, "
        "which is exactly the loss a partition makes possible."
    ),
    (
        "user",
        "Can you provide a simple concrete example of two conflicting vector clock states?"
    ),
    (
        "assistant",
        "Take nodes A, B and C, and a value first written at A and tagged {A:1}. Replica one "
        "sends that value to B, which updates it and tags it {A:1, B:1}. Meanwhile replica two "
        "sends the original value to C, which updates it and tags it {A:1, C:1}. Compare the two "
        "tags: B's component is absent from C's vector and C's is absent from B's, so neither "
        "dominates the other and the two writes are concurrent, and a client reading both sees a "
        "conflict. Had each replica received the other's version before writing, both tags would "
        "carry A, B and C, and the comparison would resolve cleanly."
    ),
    (
        "user",
        "How does Dynamo-style eventual consistency resolve such vector clock conflicts using "
        "Last-Write-Wins or CRDTs?"
    ),
    (
        "assistant",
        "Dynamo leaves the resolution to the application by returning every conflicting version "
        "with its vector clock. Many applications then apply last-write-wins, comparing "
        "timestamps or version numbers and keeping the newer value. It is simple and always "
        "resolves, but it discards the losing write silently, and clock skew can make an older "
        "write look newer. CRDTs instead resolve inside the data type: a grow-only set, a "
        "counter, or a multi-value register defines a merge that is commutative, associative and "
        "idempotent, so replicas that receive the same updates in any order converge on the same "
        "state without a coordinator and without a clock."
    ),
    (
        "user",
        "Summarize the key architectural lessons learned from these ten discussion points into "
        "three golden rules."
    ),
)

# The prompt-length pin's second source. A frozen package file rather than text assembled from
# `docs/`: those documents may be edited, and a prompt that changed under a pin is a different
# prompt. longtext.md is the 2026-09-14 and 2026-09-15 research documents concatenated in name
# order -- 60,701 tokens by the Qwen3.5-4B tokenizer, sha256 3ed2c160...a8a3 -- and it is never
# regenerated from `docs/`, reformatted, or edited.
LONGTEXT = Path(__file__).with_name("longtext.md")

# The markers around the MS-7 excerpt in PREFILL_PROMPT. The excerpt body between them is the
# first half of the source a sized prompt is cut from, and longtext.md is the rest. The head
# asks the model to read the document; the tail asks, in one sentence, what the document is
# about -- a question any cut can answer, which the MS-7 question at the end of PREFILL_PROMPT
# is not once the cut lands before rule 3.
EXCERPT_BEGIN = "--- BEGIN EXCERPT: Measurement Standard MS-7 ---"
EXCERPT_END = "--- END EXCERPT ---"

SIZED_HEAD = (
    "Read the document below in full, then answer the question at the end in one sentence.\n\n"
)
SIZED_TAIL = "\n\nQuestion: in one sentence, what is this document about?"


def sized_source() -> str:
    """The pinned source a sized prompt is cut from: the MS-7 excerpt body, then longtext.md."""
    body = PREFILL_PROMPT.split(EXCERPT_BEGIN, 1)[1].split(EXCERPT_END, 1)[0]
    return body.strip() + "\n\n" + LONGTEXT.read_text(encoding="utf-8")


def sized_prompt(counter, target: int) -> tuple[str, int]:
    """``(prompt text, achieved token count)``: the longest prompt that fits inside *target*.

    The text is ``SIZED_HEAD + cut + SIZED_TAIL``, where ``cut`` is a prefix of
    :func:`sized_source` ending at a whitespace boundary -- never a section repeated to reach
    the length, which would make the prompt a different prompt from the one the pin names. The
    cut is found by bisection over those boundaries, and the candidate it lands on is counted
    whole before it is returned, so the prompt cannot overshoot the target. On a tokenizer
    whose count is not monotone in prefix length the bisection can land a little short of the
    longest cut that fits, which is the direction that keeps the pin honest. ``achieved`` is
    ``counter.count`` of the exact text returned, and is never above *target*.

    The counter is the **serving** tokenizer -- whatever will tokenize this prompt -- and it is
    the only thing consulted, so a test can drive this with a counter as simple as
    ``len(text.split())``.

    Refused rather than approximated: a target too small to hold the head and the tail, one
    that fits them and leaves no room for any of the document, and one that would need more
    text than the source holds.
    """
    source = sized_source()
    head_and_tail = counter.count(SIZED_HEAD + SIZED_TAIL)
    if head_and_tail > target:
        raise ValueError(
            f"--prompt-tokens {target} cannot fit the head and the tail: they count "
            f"{head_and_tail} tokens on their own"
        )
    whole = counter.count(SIZED_HEAD + source + SIZED_TAIL)
    if whole < target:
        raise ValueError(
            f"--prompt-tokens {target} needs more text than the source holds: the whole "
            f"prompt counts {whole} tokens"
        )

    cuts = _cut_points(source)
    low, high = 0, len(cuts) - 1
    while low < high:
        middle = (low + high + 1) // 2
        candidate = source[: cuts[middle]]
        if counter.count(SIZED_HEAD + candidate + SIZED_TAIL) <= target:
            low = middle
        else:
            high = middle - 1

    cut = source[: cuts[low]]
    if not cut:
        raise ValueError(
            f"--prompt-tokens {target} fits only the head and the tail ({head_and_tail} "
            "tokens): the prompt would ask about a document it does not hold"
        )

    text = SIZED_HEAD + cut + SIZED_TAIL
    return text, counter.count(text)


def _cut_points(source: str) -> list[int]:
    """Every position a prefix of *source* may end at, in ascending order.

    A cut ends where whitespace begins, so the text never trails a run of spaces or newlines,
    and the end of the source is the last position. The empty prefix at 0 is the candidate the
    bisection starts from rather than a prompt: :func:`sized_prompt` refuses it.
    """
    points = [0]
    points.extend(
        index
        for index, char in enumerate(source)
        if index > 0 and char.isspace() and not source[index - 1].isspace()
    )
    points.append(len(source))
    return points


def sized_workload(measure, cells: list, target: int) -> tuple[list, dict]:
    """The one workload a ``--prompt-tokens`` run measures, and the pin its header records.

    One run pins one prompt length, so the prompt is sized once per **distinct artifact**: the
    counter is the tokenizer that will serve it, and two artifacts are free to disagree about
    how many tokens the same bytes are. Two that disagree refuse the run before a runtime is
    started, because a column measured under a length its own tokenizer does not produce is
    not a column of the sweep.

    ``chat`` and ``decode`` are not run: they would be byte-identical across every run of the
    sweep and each costs a warmup window of its own.
    """
    sized = []
    for artifact_dir in dict.fromkeys(cell.artifact_dir for cell in cells):
        text, achieved = sized_prompt(token_counter.TokenCounter(artifact_dir), target)
        sized.append((artifact_dir, text, achieved))

    achieved = {count for _artifact_dir, _text, count in sized}
    if len(achieved) > 1:
        raise ValueError(
            "the artifact tokenizers do not agree on this prompt's length: "
            + ", ".join(
                f"{artifact_dir} counts {count}" for artifact_dir, _text, count in sized
            )
            + f". One run pins one prompt length ({target} tokens), so its columns would be "
            "measuring different prompts"
        )

    _artifact_dir, text, count = sized[0]
    return (
        [
            measure.Workload(
                id="prefill", messages=[{"role": "user", "content": text}], max_tokens=64
            )
        ],
        {"target": target, "achieved": count},
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns the process exit code."""
    args = _parser().parse_args(argv)
    if args.command == "grid":
        return _join(args, "grid", lambda runs: report.render_grid(runs, rank=args.rank))
    if args.command == "sweep":
        return _join(
            args,
            "sweep",
            lambda runs: report.render_sweep(runs, varying=args.varying, rank=args.rank),
        )
    return _run(args)


def build_cells(cell_type, spec: str) -> list:
    """``"<format>__<runtime>=<artifact dir>,..."`` -> ``[Cell(...), ...]``.

    The artifact directory is carried in the selection itself rather than looked up in a
    registry: this is the only place a cell's identity is written down, and there is
    nothing to keep in sync with the machine's disk.
    """
    cells = []
    for entry in spec.split(","):
        entry = entry.strip()
        if "=" not in entry:
            raise ValueError(
                f"cell {entry!r} has no '='; expected <format>__<runtime>=<artifact dir>"
            )

        cell_id, artifact_dir = (part.strip() for part in entry.split("=", 1))
        if "__" not in cell_id:
            raise ValueError(
                f"cell {entry!r} has no '<format>__<runtime>' id; expected "
                "<format>__<runtime>=<artifact dir>"
            )

        label, runtime = cell_id.rsplit("__", 1)
        if not label or not runtime:
            raise ValueError(f"cell id {cell_id!r} is missing its format or its runtime")
        if not artifact_dir:
            raise ValueError(f"cell {cell_id!r} has no artifact directory")

        cells.append(
            cell_type(
                id=cell_id,
                runtime=runtime,
                artifact_dir=os.path.expanduser(artifact_dir),
                label=label,
            )
        )
    return cells


def workloads(measure) -> list:
    """The three pinned shapes, built against the measure module the run will use.

    Pinned as literals and pinned to three: there is no config file and no flag that adds a
    fourth. `chat` and `decode` send the same prompt and differ only in the output cap, which
    is the point — one measures per-request latency, the other sustained generation.
    """
    return [
        measure.Workload(
            id="chat", messages=[{"role": "user", "content": PROMPT}], max_tokens=128
        ),
        measure.Workload(
            id="prefill", messages=[{"role": "user", "content": PREFILL_PROMPT}], max_tokens=64
        ),
        measure.Workload(
            id="decode", messages=[{"role": "user", "content": PROMPT}], max_tokens=512
        ),
    ]


def multiturn_workloads(measure) -> list:
    """The ten turns of :data:`DIALOGUE`, one workload each, built against *measure*.

    ``turn-N``'s messages are the first N questions and the N-1 replies between them, ending on
    question N, so turn N's prompt is turn N-1's with the reply and the question after it
    appended: a strictly growing history, which is what the multi-turn study is about, and every
    turn's prompt is the same on every runtime because the history is the pinned conversation
    rather than whatever a runtime happened to answer.

    One cap for all ten, ``chat``'s 128. The conversation grows and the output cap does not,
    because a turn measured at 512 tokens would be a different request from the one before it.
    """
    turns = (len(DIALOGUE) + 1) // 2
    return [
        measure.Workload(
            id=f"turn-{turn:02d}",
            messages=[
                {"role": role, "content": content} for role, content in DIALOGUE[: 2 * turn - 1]
            ],
            max_tokens=128,
        )
        for turn in range(1, turns + 1)
    ]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ohyesmlx",
        description="Honest benchmarks for local LLM serving on Apple Silicon. "
        "One variable at a time.",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser(
        "run",
        help="measure cells and render the leaderboard",
        description="Measure cells one at a time and write results/<run-id>/results.jsonl "
        "plus a markdown leaderboard.",
    )
    run.add_argument(
        "--study",
        required=True,
        choices=STUDIES,
        help="the axis this run varies; the other variable is held constant",
    )
    run.add_argument("--cells", required=True, help=CELLS_HELP)
    run.add_argument(
        "--rank",
        default=report.DEFAULT_RANK,
        choices=tuple(report.RANK_METRICS),
        metavar="METRIC",
        help="the one metric each table is ordered by; lower-is-better metrics sort "
        f"ascending (default: {report.DEFAULT_RANK}). There is no blended score.",
    )
    run.add_argument(
        "--concurrency",
        type=int,
        default=1,
        metavar="N",
        help="requests issued together per batch (default: 1). `--measured` counts BATCHES, so "
        "at N=8 a run of 9 makes 72 requests. A sweep is several runs differing only in this "
        "pin, joined afterwards; it is not a second cell selector and not a third --study axis.",
    )
    # Two ways to choose the workload set and they cannot both choose it: `--prompt-tokens`
    # measures one `prefill` shape sized against the serving tokenizer, and `--workloads` names
    # a set of shapes pinned in this file. argparse refuses the pair before a run directory
    # exists, which is where a selection that names two sets belongs.
    selection = run.add_mutually_exclusive_group()
    selection.add_argument(
        "--workloads",
        choices=WORKLOAD_SETS,
        default="pinned",
        help="which workload set the run measures: `pinned` is the three shapes every column so "
        "far ran (`chat`, `prefill`, `decode`), `multiturn` is the ten turns of the conversation "
        "`cli.DIALOGUE` pins, whose fixed replies make turn N the same prompt on every runtime. "
        "A selector, not a pin: the header lists whichever set ran, with its messages and caps, "
        "and a join compares those. Mutually exclusive with --prompt-tokens, which measures one "
        "sized `prefill` workload of its own.",
    )
    selection.add_argument(
        "--prompt-tokens",
        type=int,
        default=None,
        metavar="N",
        help="pin the prompt length in tokens: the run measures one workload, `prefill`, whose "
        "prompt is sized to N against the serving tokenizer, and the header records the target "
        "beside the count achieved. A pin, not a selector: it says how long the prompt is, "
        "never which cells run. A sweep is several runs differing only in this pin.",
    )
    run.add_argument(
        "--cache-state",
        choices=CACHE_STATES,
        default=None,
        help="pin whether the runtime's prefix/KV reuse is on for this run: `off` disables it "
        "and `on` enables it, each through the runtime's own start flags. Leaving the flag out "
        "pins nothing: the header records `None` and every runtime starts at its own default, "
        "which was not uniform across the grid and is not the same fact as `off`. A state a "
        "runtime cannot be driven into is N/A with the reason rather than measured in the "
        "other one. A sweep is several runs differing only in this pin.",
    )
    run.add_argument(
        "--kv-quant",
        choices=KV_QUANTS,
        default=None,
        help="pin the KV-cache codec for this run: `off` for the runtime's own full-precision "
        "cache, `affine8`/`affine4` for MLX's affine codec at that width, each through the "
        "runtime's own start flags. The values name the codec rather than a bit width -- `fp8` "
        "is not one of them, because nothing these runtimes carry is a float8 KV codec -- and "
        "leaving the flag out pins nothing at all: the header records `None` and every runtime "
        "starts with its own codec. A value a runtime cannot deliver is N/A with the reason "
        "rather than approximated into a neighbouring codec. A sweep is several runs differing "
        "only in this pin.",
    )
    run.add_argument(
        "--mtp-depth",
        choices=MTP_DEPTHS,
        default=None,
        help="pin the native-MTP draft depth for this run: `off` for MTP not running, "
        "`1`/`2`/`3` for that many draft tokens per verify cycle under the runtime's fixed "
        "policy (vMLX's default policy moves the depth inside a single request, so it is never "
        "left to adapt). vMLX is the only runtime here with a depth to pin; the others are N/A "
        "with the reason. A depth is also refused on an artifact whose MTP heads vMLX will not "
        "wire, because its decode then falls back silently. Leaving the flag out pins nothing: "
        "the header records `None`. A sweep is several runs differing only in this pin.",
    )
    run.add_argument(
        "--stream-experts",
        choices=STREAM_EXPERTS,
        default=None,
        help="pin whether MoE expert weights are streamed from SSD (`on`) or held resident "
        "(`off`), through each runtime's own start flag. Both runtimes that accept `on` fall "
        "back to a resident load silently, so an `on` cell is only accepted when the runtime's "
        "own log shows streaming -- otherwise it is FAIL with that log quoted. Leaving the flag "
        "out pins nothing and is not `off`: the header records `None`, and OptiQ's own default "
        "is `auto`, which streams a large MoE unasked. A sweep is several runs differing only in "
        "this pin.",
    )
    run.add_argument(
        "--results-dir",
        default="results",
        help="parent of the run directory (default: results, so results/<run-id>/results.jsonl)",
    )

    grid = commands.add_parser(
        "grid",
        help="join run directories into one grid",
        description="Join finished run directories into one grid: formats down, runtimes "
        "across. Measures nothing and starts no runtime -- it reads results.jsonl files "
        "that already exist.",
    )
    grid.add_argument(
        "run_dirs",
        nargs="+",
        metavar="RUN-DIR",
        help="the run directories to join, named one by one. There is no glob and no "
        "--all: results/ accumulates runs from every session, and a grid assembled by "
        "wildcard would silently join columns that never belonged together.",
    )
    grid.add_argument(
        "--rank",
        default=report.DEFAULT_RANK,
        choices=tuple(report.RANK_METRICS),
        metavar="METRIC",
        help=f"the one metric each grid entry carries (default: {report.DEFAULT_RANK})",
    )
    grid.add_argument(
        "--out",
        default=None,
        help="also write the grid here (default: stdout only)",
    )

    sweep = commands.add_parser(
        "sweep",
        help="join run directories into one sweep of a single header pin",
        description="Join finished run directories that differ in exactly one header pin -- "
        "concurrency, prompt length, cache state, KV-cache codec, MTP depth or expert streaming "
        "-- into one table per "
        "workload: cells down, the pin's values across. Measures nothing and starts no runtime "
        "-- it reads results.jsonl files that already exist.",
    )
    sweep.add_argument(
        "run_dirs",
        nargs="+",
        metavar="RUN-DIR",
        help="the run directories to join, named one by one and read exactly as `grid` reads "
        "them. There is no glob and no --all: results/ accumulates runs from every session, "
        "and a sweep assembled by wildcard would join runs that never belonged together.",
    )
    sweep.add_argument(
        "--varying",
        required=True,
        choices=report.SWEEP_PINS,
        help="the one header pin these runs were allowed to disagree about; every other pin, "
        "and every workload, is compared across the runs and refused where it disagrees",
    )
    sweep.add_argument(
        "--rank",
        default=report.DEFAULT_RANK,
        choices=tuple(report.RANK_METRICS),
        metavar="METRIC",
        help=f"the one metric each sweep entry carries (default: {report.DEFAULT_RANK}). A "
        "concurrency sweep's per-request rates fall as N rises by construction, so "
        "`aggregate_tps` is the throughput reading; a prompt-length sweep is compared on "
        "`ttft_p50_s`, and so is a cache-state one, where a hit shows as a collapse in the "
        "time to first token.",
    )
    sweep.add_argument(
        "--out",
        default=None,
        help="also write the sweep here (default: stdout only)",
    )
    return parser


def _join(args, name: str, render) -> int:
    """Join the named run directories and render them with *render*.

    ``grid`` and ``sweep`` are two joins over one file format: the same ``load_run``, the same
    ``summarize``, the same run-directory name as the label, differing only in the renderer
    that puts the joined runs on the page. The guards live in ``report``, not here: refusing
    to join runs that disagree, or runs whose swept pin never moved, is a statement about the
    data, and the CLI is not where that is decided.
    """
    measure = _load_measure()
    runs = []
    for run_dir in args.run_dirs:
        try:
            header, results = measure.load_run(run_dir)
        except (OSError, ValueError) as exc:
            print(f"ohyesmlx {name}: {run_dir}: {exc}", file=sys.stderr)
            return 2
        # The run's own batch pin, from its header: a row that landed fewer batches than the
        # run asked for carries the count into the table beside its number.
        rows = report.summarize(results, measured=header.get("measured"))
        runs.append((Path(run_dir).name, header, rows))

    try:
        joined = render(runs)
    except ValueError as exc:
        print(f"ohyesmlx {name}: {exc}", file=sys.stderr)
        return 2

    print(joined)
    if args.out:
        Path(args.out).write_text(joined, encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


def _run(args) -> int:
    measure = _load_measure()
    try:
        cells = build_cells(measure.Cell, args.cells)
        _check_axis(cells, args.study)
        # The prompt is sized, and the tokenizers are made to agree on its length, before a
        # run directory exists and before any runtime is started for it.
        if args.prompt_tokens is not None:
            shapes, prompt_tokens = sized_workload(measure, cells, args.prompt_tokens)
        elif args.workloads == "multiturn":
            shapes, prompt_tokens = multiturn_workloads(measure), None
        else:
            shapes, prompt_tokens = workloads(measure), None
    except ValueError as exc:
        print(f"ohyesmlx run: {exc}", file=sys.stderr)
        return 2

    run_dir = Path(args.results_dir) / f"{_stamp()}-{args.study}"
    run_dir.mkdir(parents=True, exist_ok=True)

    results = measure.run_cells(
        cells,
        shapes,
        concurrency=args.concurrency,
        cache_state=args.cache_state,
        kv_quant=args.kv_quant,
        mtp_depth=args.mtp_depth,
        stream_experts=args.stream_experts,
        results_dir=str(run_dir),
        prompt_tokens=prompt_tokens,
    )
    # No pin is named here and none is passed: `run_cells` stamps each result with the batch
    # pin it ran under, which is the same value its header records, so the leaderboard's
    # short-window note is keyed to the run's own pin rather than to a copy of the default.
    rows = report.summarize(results)

    leaderboard = report.render_markdown(rows, axis=args.study, rank=args.rank)
    (run_dir / "leaderboard.md").write_text(leaderboard, encoding="utf-8")

    print(leaderboard)
    print(f"wrote {run_dir}/results.jsonl and {run_dir}/leaderboard.md")
    return 0


def _check_axis(cells: list, study: str) -> None:
    """Refuse a selection that varies the axis' held-constant variable too."""
    if study == "runtime":
        held = {(cell.label, cell.artifact_dir) for cell in cells}
        if len(held) > 1:
            raise ValueError(
                "--study runtime holds the quantization format constant, but these cells "
                f"use {len(held)} different artifacts: "
                + ", ".join(sorted(f"{label}={path}" for label, path in held))
            )
        return

    runtimes = {cell.runtime for cell in cells}
    if len(runtimes) > 1:
        raise ValueError(
            "--study format holds the serving runtime constant, but these cells use "
            f"{len(runtimes)} different runtimes: {', '.join(sorted(runtimes))}"
        )


def _load_measure():
    """measure.py owns the loop; the CLI only asks it to run cells."""
    from ohyesmlx import measure

    return measure


def _stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


if __name__ == "__main__":
    raise SystemExit(main())
