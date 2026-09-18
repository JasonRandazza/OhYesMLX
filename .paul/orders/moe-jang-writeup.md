GOAL: Author docs/research/2026-09-17-moe-jang-study.md — the comprehensive research report for Plan 01-02 (MoE JANG Study: LFM2.5-8B-A1B across vMLX and Osaurus, format axis, cross-runtime JANG row reading, 2-cell replication, and attribution analysis).

FILES YOU MAY EDIT:
docs/research/2026-09-17-moe-jang-study.md only. Touch nothing else.

STYLE & METHOD:
- Model after docs/research/2026-09-17-dense-jang-study.md: rigorous prose, exact Markdown tables, citations to run records.
- Ground all numbers in real run files under results/grid-jang-moe/ and results/grid-jang-moe/replicate/.
- Evaluate findings against the pre-registered readings (R1-R4), tie band (2.5%), and replication rule (5%) in docs/research/2026-09-17-v2-track1-jang-study-design.md.

INPUTS:
- results/grid-jang-moe/runner.log
- results/grid-jang-moe/grid.md
- results/grid-jang-moe/20260917T213103Z-format/leaderboard.md (vMLX column)
- results/grid-jang-moe/20260917T215805Z-format/leaderboard.md (Osaurus column)
- results/grid-jang-moe/replicate/20260917T222656Z-format/leaderboard.md (Osaurus replicate)
- results/grid-jang-moe/replicate/20260917T223632Z-format/leaderboard.md (vMLX replicate)
- docs/research/2026-09-17-v2-track1-jang-study-design.md
- docs/research/2026-09-17-dense-jang-study.md

KEY NUMBERS & OBSERVATIONS TO CITE:
1. Headline Finding — Pre-registered Reading R4 (Split by Model):
   - Unlike Dense (where JANG_4S scored R1, leading sustained decode across both runtimes), on MoE LFM2.5-8B-A1B JANG_2L does NOT lead portable formats on sustained decode:
     * vMLX decode (512 tokens): jang2l 116.3 tok/s vs stock4bit 115.3 tok/s (+0.9% in primary); replicate jang2l 120.4 tok/s vs stock4bit 121.0 tok/s (-0.5% in replicate). Both gaps are strictly inside the 2.5% tie band: JANG and stock4bit are in an unresolvable TIE (R3) in vMLX!
     * Osaurus decode (512 tokens): stock4bit 123.0 tok/s vs jang2l 116.7 tok/s (stock4bit leads by +5.4% / JANG is -5.1% in primary); replicate stock4bit 127.5 tok/s vs jang2l 115.0 tok/s (stock4bit leads by +10.8% / JANG is -9.8% in replicate). stock4bit cleanly beats JANG in Osaurus!
     * Conclusion: Pre-registered reading R4 is triggered. The JANG decode advantage is model- and architecture-specific; it does NOT transfer to MoE.
2. Format Axis inside vMLX (20260917T213103Z-format):
   - decode (512 tokens): jang2l 116.3 ~ stock4bit 115.3 (tie) > optiq 100.6 > oq4e 97.0 > oq4 65.6 (drift +76.0%).
   - chat (128 tokens): stock4bit 115.5 > jang2l 112.2 (-2.8%) > optiq 96.9 > oq4 96.1 > oq4e 94.4.
   - prefill (64 tokens, decode rate): stock4bit 108.4 > jang2l 97.1 (-10.5%) > optiq 88.9 > oq4 84.5 > oq4e 84.3.
   - Prefill TTFT & Prompt TPS: jang2l achieves 0.812s TTFT (1643.4 tok/s prefill prompt tps) vs stock4bit 1.245s TTFT (1069.7 tok/s) — a 53.6% prefill prompt throughput advantage for JANG, driven by low precision (2.37 actual bits) on prompt ingestion!
3. Format Axis inside Osaurus (20260917T215805Z-format):
   - decode (512 tokens): stock4bit 123.0 > jang2l 116.7 > oq4 115.8.
     Two cells reproduced predicted FAILs: oq4e and optiq both FAILed with "no content completion tokens from token_source='none', so decode tok/s is undefined" (exercising the grid's 4 entry states).
   - chat (128 tokens): stock4bit 141.8 > oq4e 127.2 > jang2l 126.1 > oq4 124.8 > optiq 119.7.
   - prefill (64 tokens, decode rate): stock4bit 138.9 > oq4 128.5 > oq4e 128.0 > optiq 126.4 > jang2l 123.4.
   - Prefill TTFT verification: with osaurus_cache off, TTFT was 1.60-1.69s across all formats (prefill tps ~787-831 tok/s), proving zero prefix cache lookups and 100% genuine prompt processing!
4. 2-Cell Replication Pass (results/grid-jang-moe/replicate/):
   - Replicate column order reversed from primary: Osaurus replicate (20260917T222656Z-format) run first, vMLX replicate (20260917T223632Z-format) run second.
   - Decisive cells selected dynamically from decode leader: stock4bit was the best portable in both runtimes.
   - Osaurus replicate: stock4bit 127.5 tok/s vs jang2l 115.0 tok/s on decode (stock4bit leads by +10.8%). On chat: stock4bit 137.4 vs jang2l 132.3 (+3.9%). On prefill: stock4bit 138.0 vs jang2l 124.4 (+10.9%).
   - vMLX replicate: stock4bit 121.0 tok/s vs jang2l 120.4 tok/s on decode (0.5% gap, confirming tie). On chat: jang2l 117.4 vs stock4bit 116.7 (0.6% gap, tie). On prefill: stock4bit 100.0 vs jang2l 99.5 (0.5% gap, tie).
5. Cross-Runtime JANG Row (Runtime Axis on identical JANG_2L bytes: 3,062,430,853 B):
   - decode: vMLX 116.3 vs Osaurus 116.7 in primary (0.3% gap, tie!); in replicate, vMLX 120.4 vs Osaurus 115.0 (+4.7% lead for vMLX).
   - chat: Osaurus 126.1 vs vMLX 112.2 (+12.4% for Osaurus); in replicate, Osaurus 132.3 vs vMLX 117.4 (+12.7% for Osaurus).
   - prefill: Osaurus 123.4 vs vMLX 97.1 (+27.1% for Osaurus); in replicate, Osaurus 124.4 vs vMLX 99.5 (+25.0% for Osaurus).
   - Comparison with Dense JANG Row: In dense, vMLX was +28% faster than Osaurus on decode. In MoE, sustained decode is essentially tied (or +4.7% vMLX in replicate), while Osaurus leads on short generation / prefill.
6. Memory, Footprint & Disk Space:
   - On-disk: jang2l is 3.06 GB vs stock4bit 4.78 GB (36% smaller on disk).
   - Peak Memory (peak_mb on decode):
     * vMLX: jang2l 3,624 MB vs stock4bit 5,214 MB (30.5% reduction in unified memory footprint).
     * Osaurus: jang2l 3,829 MB vs stock4bit 4,542 MB (15.7% reduction).
   - Even without a sustained decode throughput victory, JANG_2L delivers substantial memory and storage density benefits.
7. Verification & Invariants:
   - Osaurus settings backed up and restored byte-exact (cmp verified at runner.log:9 and :152).
   - Both runtimes at fixed versions: vmlx 1.6.59, osaurus 0.25.6.
   - All tests green, quiet machine maintained throughout.

REQUIRED SECTIONS:
1. Executive summary and headline finding (Pre-registered reading R4: Split by model; JANG ties stock4bit in vMLX and loses to stock4bit in Osaurus on sustained decode).
2. Provenance and operational environment (runtimes, versions, pins, artifact digests, cache-state off verification).
3. The format axis inside vMLX (decode, chat, prefill tables, replicate pass, prompt TTFT advantage).
4. The format axis inside Osaurus (decode, chat, prefill tables, optiq & oq4e decode FAILs, replicate pass, cache isolation verification).
5. The cross-runtime JANG row (identical bytes compared across vMLX and Osaurus; comparison with Dense finding).
6. Attribution breakdown & architectural analysis (why dense JANG won and MoE JANG did not: expert routing, 2.37 bits precision vs uniform 4-bit, kernel overhead).
7. Memory footprint, cold-start cost, and storage economics.
8. Threats to validity and boundaries.

REPORT:
Path to the new document, executive summary of findings, and confirmation of byte-exact test verification.
