GOAL: Author docs/research/2026-09-17-dense-jang-study.md — the comprehensive research report for Plan 01-01 (Dense JANG Study: Qwen3.5-4B in vMLX and Osaurus, format axis, cross-runtime JANG row reading, 2-cell replication, and attribution analysis).

FILES YOU MAY EDIT:
docs/research/2026-09-17-dense-jang-study.md only. Touch nothing else.

STYLE & METHOD:
- Follow docs/research/ style: rigorous prose, exact Markdown tables, citations to run records.
- Ground all numbers in real run files under results/grid-jang-dense/ and results/grid-jang-dense/replicate/.
- Evaluate findings against the pre-registered readings (R1-R4), tie band (2.5%), and replication rule (5%) in docs/research/2026-09-17-v2-track1-jang-study-design.md.

INPUTS:
- results/grid-jang-dense/runner.log
- results/grid-jang-dense/grid.md
- results/grid-jang-dense/20260917T185649Z-format/leaderboard.md (vMLX column)
- results/grid-jang-dense/20260917T194005Z-format/leaderboard.md (Osaurus column)
- results/grid-jang-dense/replicate/20260917T202054Z-format/leaderboard.md (vMLX replicate)
- results/grid-jang-dense/replicate/20260917T203824Z-format/leaderboard.md (Osaurus replicate)
- docs/research/2026-09-17-v2-track1-jang-study-design.md

KEY NUMBERS & OBSERVATIONS TO CITE:
1. vMLX Column (20260917T185649Z-format):
   - decode (512 tokens): jang4s 54.2 tok/s > oq4 47.6 (+13.9%) > oq4e 46.0 (+17.8%) > stock4bit 44.2 (+22.6%).
   - chat (128 tokens): stock4bit 60.5 (drift -24.7%) > jang4s 55.2 (drift -0.8%) > oq4e 46.6 > oq4 46.1.
   - prefill (64 tokens): stock4bit 60.7 (drift -12.4%) ~ jang4s 60.2 (drift +2.3%, 0.8% tie) > oq4 53.8 > oq4e 50.8.
2. Osaurus Column (20260917T194005Z-format):
   - decode (512 tokens): jang4s 42.5 tok/s > oq4 38.8 (+9.5%) > optiq 38.7 (+9.8%) > oq4e 38.6 (+10.1%).
     Notice: oq4 (38.8), optiq (38.7), and oq4e (38.6) are within 0.5% of each other — a 3-way tie under the 2.5% tie band!
   - chat (128 tokens): jang4s 48.1 tok/s > oq4 44.3 > oq4e 41.5 > optiq 41.4.
   - prefill (64 tokens): jang4s 55.8 tok/s > oq4 52.6 > optiq 50.4 > oq4e 48.2.
3. 2-Cell Replication Runs (replicate/):
   - vMLX replicate (20260917T202054Z-format):
     * decode: jang4s 59.1 tok/s vs stock4bit 50.6 tok/s (+16.8% lead for JANG, replicating the lead).
     * chat: jang4s 60.0 tok/s vs stock4bit 52.3 tok/s (+14.7% lead for JANG; resolves grid's thermal drift anomaly on stock4bit).
     * prefill: jang4s 62.7 tok/s vs stock4bit 58.1 tok/s (+7.9% lead for JANG).
   - Osaurus replicate (20260917T203824Z-format):
     * decode: jang4s 46.0 tok/s vs oq4 42.2 tok/s (+9.0% lead for JANG, replicating grid's +9.5% lead).
     * chat: oq4 50.5 tok/s vs jang4s 49.6 tok/s (1.8% difference, within 2.5% tie band).
     * prefill: jang4s 59.0 tok/s vs oq4 58.4 tok/s (1.0% difference, within tie band).
4. Cross-Runtime JANG Row (Runtime Axis on identical bytes):
   - decode: vMLX 54.2 tok/s (59.1 repl) > Osaurus 42.5 tok/s (46.0 repl). vMLX is +27.5% to +28.5% faster on the exact same JANG weights!
5. Attribution Analysis:
   - JANG_4S is 4.15 actual bits and 2.99 GB on disk vs stock-4bit (2.85 GB) and oq4 (2.94 GB).
   - Size reduction cannot explain the lead. Custom Metal kernel unpacking and packed half-width embeddings in utils/jang_loader account for the speedup, even with JIT and MTP pinned off.
6. Memory & Integrity:
   - Memory: vMLX footprint ~3820 MB on decode; Osaurus ~2466-3400 MB.
   - Cold load: vMLX 7.06s; Osaurus 1.25s (with ~3.4s first request).
   - Osaurus settings restored byte-exact (cmp verified), all 12 cells passed 100% coherence gate.

REQUIRED SECTIONS:
1. Executive Summary & Headline Finding (JANG leads sustained decode in both runtimes on near-equal precision).
2. Provenance & Operational Environment (runtimes, versions vmlx 1.6.59, osaurus 0.25.6, pins, artifact digests).
3. The Format Axis inside vMLX (decode, chat, prefill tables, drift analysis, replicate confirmation).
4. The Format Axis inside Osaurus (decode, chat, prefill tables, 3-way portable tie, replicate confirmation).
5. The Cross-Runtime JANG Axis (identical weights compared across vMLX and Osaurus).
6. Attribution Breakdown (why 4.15 bits beats 4.0 bits: packing and Metal kernel execution).
7. Memory & Cold-Start Cost.
8. Threats to Validity & Boundaries (JIT pinned off, dense model only, accuracy out of scope).

REPORT:
Path to the new document, summary of findings, and confirmation of byte-exact test verification.
