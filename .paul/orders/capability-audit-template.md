GOAL: produce a complete capability and configuration reference for ONE serving runtime, so
this project stops inferring what a tool cannot do from the absence of a command-line flag.

WHY THIS ORDER EXISTS. The harness published that oMLX 0.6.4 "cannot stream incrementally",
on the evidence that `omlx serve --help` exposes no streaming-granularity flag. Every fact in
that reasoning was true and the conclusion was false. oMLX streams 15 deltas per response in
its reasoning_content channel; one grep of its own bundled source finds
`stream_interval: int = 1  # Tokens to batch before streaming (1=every token)`. The harness
had reported the runtime's TTFT as 5.499 s when it is 0.685 s — wrong by 8x, against the
runtime. `--help` documents a command line. It does not document a runtime.

DELIVERABLE: one new file, `docs/runtimes/<name>.md`. Create the directory if needed. Write
nothing else. Do not edit any Python, any test, or any existing document.

COVER, each with the evidence that establishes it — a file path and line, a `--help` excerpt,
a settings key, or a source quote. An unsourced claim is worse than an omission:

1. **Every entry point.** The binary on PATH, what it actually execs, and any other
   executables shipped in the bundle. Note when a console script resolves its interpreter
   relative to its own location (a symlink into ~/.local/bin then breaks it).
2. **The full command-line surface.** Every flag, its default, and what it controls.
3. **The settings surface beyond the command line.** Config files, their location, every key,
   and which settings have NO command-line equivalent. These are the ones that silently
   decide what a cell measures.
4. **Per-request API fields** the OpenAI-compatible endpoint honours beyond the standard set.
5. **Streaming behaviour — mandatory, and measured, not inferred.** Which channels it emits
   (content, reasoning_content, reasoning, other), whether each streams incrementally or
   arrives whole, whether any channel is mirrored into another, and what controls the
   granularity. Say exactly where in the source this is decided.
6. **Token accounting.** What its usage block reports, whether it separates reasoning from
   content, and whether its self-reported rates are trustworthy. oMLX reports
   generation_tokens_per_second of 15286.61 from a generation_duration of 0.0.
7. **Anything that silently changes performance without appearing in the start command** —
   automatic heuristics, memory-pressure behaviour, caches, batching thresholds. mlx-optiq
   turns --stream-experts on by itself above a RAM threshold and costs 5x with nothing in the
   artifact explaining it. Find this runtime's equivalents.
8. **Which quantization formats it loads**, with the evidence, and which it refuses.

METHOD. Read `--help` for every subcommand. Read the config/settings file if one exists. Then
read the SHIPPED SOURCE — these are GUI apps bundling readable Python, and the source is the
authority when it disagrees with the docs. Grep it for the behaviours above rather than
trusting a flag list.

HARD LIMITS. Do NOT start the server, load a model, send a request, or run any benchmark —
static inspection only; the coordinator runs live probes. Do not install, upgrade, or
reconfigure anything. Do not edit the runtime's own files.

WRITE IT AS A REFERENCE DOCUMENT, at full length, with headings and tables — a future agent
should be able to answer "can it do X" from this file without opening the bundle. State
plainly what you could not determine and why. A negative claim ("it cannot do X") requires
source or settings evidence; if you only have "no flag for it", say exactly that instead.
