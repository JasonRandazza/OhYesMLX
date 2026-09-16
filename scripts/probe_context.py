"""Probe 06-01c: does a runtime serve a long prompt whole, refuse it, or cut it?

The source says none of the five refuses 32k tokens on Qwen3.5-4B
(`docs/research/2026-09-16-prompt-length-context-limits.md`), and Osaurus has no source to
read. This asks each runtime directly, on the oQ4 cell every sweep so far used:

  * the HTTP outcome -- a refusal is a 400 or 413 with the prompt never prefilled
  * `prompt_tokens` against the local count -- a runtime that truncated or rotated reports
    fewer than it was sent, or reports all of them and answers from a window of them
  * TTFT on the same prompt twice -- a second TTFT that collapses is a prefix-cache hit, and a
    sweep would publish it as prefill

    scripts/probe_context.py <runtime> [target ...]
    scripts/probe_context.py osaurus 16384 32768

Nothing here is a published figure, and nothing is written to results/.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ohyesmlx import cli, coherence, runtimes, token_counter, transport  # noqa: E402

ARTIFACT = os.path.expanduser(
    "~/.cache/huggingface/hub/models--RepublicOfKorokke--Qwen3.5-4B-oQ4/snapshots/"
    "3ae88a7d17b1c6bb71b795c1090948a82508fdb8"
)


def main() -> int:
    name = sys.argv[1]
    targets = [int(arg) for arg in sys.argv[2:]] or [16384, 32768]
    counter = token_counter.TokenCounter(ARTIFACT)
    prompts = [(target, *cli.sized_prompt(counter, target)) for target in targets]

    handle = runtimes.RUNTIMES[name].start(ARTIFACT, ARTIFACT)
    try:
        for target, text, achieved in prompts:
            for attempt in (1, 2):
                o = transport.chat(
                    handle.base_url,
                    handle.model_id,
                    [{"role": "user", "content": text}],
                    max_tokens=64,
                    temperature=0.0,
                    seed=0,
                    token_counter=counter,
                    api_key=handle.api_key,
                )
                answer = o.text or o.reasoning_text
                verdict = coherence.is_coherent(answer)[1] if answer.strip() else "no output"
                ttft = "-" if o.ttft_s is None else f"{o.ttft_s:.2f}"
                print(
                    f"{name} target={target} sent={achieved} #{attempt} ok={o.ok} "
                    f"error={o.error!r} prompt_tokens={o.prompt_tokens} ttft_s={ttft} "
                    f"completion={o.completion_tokens} coherence={verdict!r}"
                )
                print(f"    {answer[:160]!r}")
    finally:
        handle.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
