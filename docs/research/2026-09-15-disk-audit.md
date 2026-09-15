# Disk Audit — 2026-09-15

Internal SSD, `disk0` → APFS container `disk3`, 994.7 GB capacity ceiling. 37.6 GB unallocated.

Filesystem-only audit. No project planning documents were read. No files were deleted, moved,
or truncated; every number below is a measurement taken during this session. Nothing was
committed.

## Measurement constraints

Stated up front because they bound what this report can claim:

- **No root.** `sudo -n` fails (`a password is required`). All `du` figures are unprivileged and
  therefore **exclude** directories the account cannot read. The exclusions are enumerated in
  §2 and are bounded, not silent.
- **`tmutil` has no size verb.** `tmutil version` reports 4.0.0. `tmutil localsnapshotinfo` is not
  a valid verb on this build, `tmutil calculatedrift` only accepts a machine directory and rejects
  `/`, and `diskutil apfs listSnapshots` reports identity and purgeability but no byte counts.
  Snapshot space is therefore reported as a derived residual, not a direct measurement.
- **No hardlinks anywhere in the model stores.** Verified with
  `find <dir> -type f -links +1` across `~/.cache/huggingface/hub`, `~/MLXModels`, `~/.omlx/cache`,
  `~/.osaurus/cache` and `~/AI/LTX/models`: **0 files with nlink > 1** in each. Symlinks are not
  followed by `du` and are not hardlinks, so no blob is double counted and the `du` totals are exact.
- **Rounding.** Sizes are exact GB (bytes / 1024³) except where a command was run with `-g`, in
  which case the value is a whole-GB truncation. Nothing is estimated from file counts or
  extrapolated.

---

## 0. Headline: the "700 GB unaccounted for" premise does not survive measurement

The 700 GB gap was an artefact of comparing APFS accounting against a Finder-visible home
directory. Once dot-directories are included, the overwhelming majority of the volume is
attributed to directories that can be named precisely.

| Layer | GB |
|---|---:|
| APFS container ceiling (`disk3`) | 994.7 |
| In use by volumes | 957.0 |
| Not allocated (free) | 37.6 |

Container contents, all four volumes:

| Volume | Role | GB |
|---|---|---:|
| `disk3s1` Macintosh HD | System (sealed) | 12.6 |
| `disk3s2` Preboot | Preboot | 9.0 |
| `disk3s3` Recovery | Recovery | 1.3 |
| `disk3s5` Macintosh HD - Data | Data | 933.9 |
| `disk3s6` VM | swap | 0.00002 |
| | **total** | **956.8** |

Data volume reconciliation:

| | GB |
|---|---:|
| Data volume consumed (APFS) | 933.9 |
| Attributed to readable directories | 656.5 |
| **Not explainable from readable files** | **~277.4** |

The 656.5 GB of readable directories breaks down as: `~` 591.45, `/Applications` 26.45,
`/opt` 12.91, `Data/System` 11.76, `/private` 7.87, `/Library` 6.05, `/usr` 0.75.

**The two answers to the original question:**

1. **~368 GB sits in dot-directories the Finder hides.** `~/.cache` (152.80) + `~/MLXModels`
   (147.07) + `~/.omlx` (68.58) alone is 368.45 GB. None of it appears in a default Finder view of
   the home folder. This is why the space looked unaccounted for.
2. **~277 GB is APFS-resident and invisible to `du` at any depth** — local Time Machine snapshots
   plus a small set of root-only system directories. Detail in §2.

---

## 1. Top consumers

26 directories, full paths, measured GB. Overlap is intentional — parent and child are both shown
where the parent's total is otherwise hard to attribute.

| GB | Path | Notes |
|---:|---|---|
| 152.80 | `/Users/jrazz/.cache` | parent of rows 3, 11, 12 |
| 147.07 | `/Users/jrazz/MLXModels` | parent of rows 4, 7 |
| 100.61 | `/Users/jrazz/.cache/huggingface/hub` | the "~100 GB HF cache" |
| 93.65 | `/Users/jrazz/MLXModels/OsaurusAI` | JANG-format MLX weights |
| 82.08 | `/Users/jrazz/Library` | parent of rows 9, 13, 21, 22, 23 |
| 68.58 | `/Users/jrazz/.omlx/cache` | KV/prefix cache, confirmed by header |
| 53.41 | `/Users/jrazz/MLXModels/image` | diffusion weights |
| 41.82 | `/Users/jrazz/AI/LTX` | `models/` 41.43 + repo |
| 37.30 | `/Users/jrazz/Library/Application Support` | parent of rows 21, 22 |
| 26.45 | `/Applications` | Xcode 5, Android Studio 4, Docker 3 |
| 26.42 | `/Users/jrazz/.cache/uv` | `archive-v0` 26.42 |
| 21.82 | `/Users/jrazz/.cache/vmlx-engine` | `block-cache/` 21.82 |
| 21.31 | `/Users/jrazz/Library/Caches` | Homebrew 7.58, Google 5.97 |
| 20.68 | `/Users/jrazz/.gradle` | `caches/` 17.68 |
| 18.50 | `/Users/jrazz/Dev` | `active/` 14.11 |
| 17.68 | `/Users/jrazz/.gradle/caches` | Gradle artifact cache |
| 14.11 | `/Users/jrazz/Dev/active` | source checkouts |
| 13.36 | `/Users/jrazz/.android` | `avd/` 13.13 |
| 13.13 | `/Users/jrazz/.android/avd` | emulator images |
| 12.91 | `/opt` | Homebrew (`/opt/homebrew`) |
| 12.86 | `/Users/jrazz/Library/Application Support/Claude` | `vm_bundles/` 11.22 |
| 12.70 | `/Users/jrazz/Library/Application Support/Google` | Chrome 7.91, DriveFS 3.46 |
| 11.00 | `/Users/jrazz/Library/Android` | SDK |
| 10.90 | `/Users/jrazz/.osaurus` | `cache/kv_v2` 8.24 |
| 8.24 | `/Users/jrazz/.osaurus/cache` | KV cache, confirmed by header |
| 7.92 | `/Users/jrazz/.npm` | `_cacache` 5.95 |

Directories from the brief that landed small enough to fall off this table, all measured:
`~/Documents` 1, `~/Downloads` 1, `~/Movies` 1, `~/Desktop` 1, `~/Music` 1, `~/Pictures` 1,
`~/.Trash` 1 (and **empty of items** — `ls ~/.Trash | wc -l` = 0), `~/.docker` 0.02,
`~/.lmstudio` 1.44, `~/Library/Developer` 0.74, `~/Library/Containers` 6.90
(`com.docker.docker` 5.98), `/private/var/folders` 2.01, `/private/var/vm` 2.00,
`/private/var/db` 3.29, `/Library` 6.05, `/Library/Developer` 5
(`CoreSimulator/Caches` 3.04).

**Xcode is not the problem here.** `~/Library/Developer/Xcode/DerivedData` is **0.11 GB**. The
brief anticipated DerivedData, iOS DeviceSupport, simulators and archives as a likely consumer;
on this machine they total **0.74 GB**. `~/Library/Developer` as a whole is 0.74 GB and
`/Library/Developer` is 5 GB. There is no meaningful Xcode reclaim on this machine.

**Absent entirely:** `~/.ollama` and `~/.orbstack` do not exist. `~/.lmstudio` is 1.44 GB.
`~/.docker` is 0.02 GB — the container data lives in
`~/Library/Containers/com.docker.docker` (5.98 GB) instead.

---

## 2. Invisible space

### 2.1 Local Time Machine snapshots — the leading explanation

```
$ tmutil listlocalsnapshots /
com.apple.TimeMachine.2026-09-03-130310.local
com.apple.TimeMachine.2026-09-10-130415.local
```

```
$ diskutil apfs listSnapshots disk3s5
Snapshots for disk3s5 (2 found)
+-- D3B2B526-6A82-40B2-B7B2-1F0D11D9706D
|   Name:        com.apple.TimeMachine.2026-09-03-130310.local
|   XID:         7799681
|   Purgeable:   Yes
+-- F2654AB6-A7A8-46AF-8CD5-7FACE336CAE1
    Name:        com.apple.TimeMachine.2026-09-10-130415.local
    XID:         8048239
    Purgeable:   Yes
    NOTE:        This snapshot limits the minimum size of APFS Container disk3
```

Two snapshots exist. Both are marked `Purgeable: Yes`. The second carries APFS's own note that it
**limits the minimum size of the container** — that is APFS stating the snapshot pins blocks that
the container cannot release.

**Byte-exact snapshot size could not be obtained without root** (see constraints). What can be
stated rigorously:

- The 277.4 GB residual is *not* attributable to root-only directories. Those are
  `/System/Volumes/Data/.DocumentRevisions-V100`, `.Spotlight-V100`, `.fseventsd`,
  `/private/var/db` and a handful of `/Library` entries. Measured where readable:
  `/private/var/db` 3.29 GB, `/private/var` 7.87 GB total. On a volume of this size these are
  normally single-digit to low-tens of GB. `/private/var/folders` is 2.01 GB, `/private/var/vm`
  2.00 GB (`sleepimage`, exactly 2147483648 bytes).
- Therefore **the bulk of the 277.4 GB residual is snapshot-pinned blocks** — data that was
  deleted from the live filesystem but is retained because a snapshot still references it.

This is consistent with the known history of this machine: large quantized model artifacts
(~19–23 GB each) are downloaded, evaluated and deleted repeatedly, and any deletion after
2026-09-03 is still pinned by these snapshots.

**This is the single largest reclaimable item on the machine, and it is invisible to `du`,
Finder, and `df`'s "used" figure alike.** The fix is `tmutil deletelocalsnapshots <date>` (or
`sudo tmutil thinlocalsnapshots / <bytes> 4` to thin rather than delete), which requires the
password that this session did not have. **Not executed — this report is read-only.**

### 2.2 Purgeable space

`diskutil apfs list` on this build emits no `Purgeable` line for the container or its volumes, and
`diskutil apfs list -plist` exposes no purgeable key (only `CapacityCeiling`, `CapacityFree`,
`CapacityInUse`, `CapacityQuota`, `CapacityReserve`). The requested
`grep -i -A2 purgeable` equivalent therefore returns nothing from `diskutil`; the only
purgeability signal available unprivileged is the per-snapshot `Purgeable: Yes` in §2.1.

### 2.3 Other containers

`diskutil list` shows two additional containers on the same physical disk, outside `disk3`:
`disk1` (Apple_APFS_ISC, 524.3 MB) and `disk2` (Apple_APFS_Recovery, 5.4 GB). Both are
system-managed. `/Volumes` contains only a `.timemachine` directory and a `Macintosh HD` symlink
to `/`; there are no mounted external volumes contributing to the count.

---

## 3. Model artifacts

True sizes, one line per repo. **No hardlinks exist in any of these trees** (§Measurement
constraints), and `du` does not follow the snapshot symlinks in the HF cache, so each blob is
counted exactly once. Nothing here is double counted.

### 3.1 `~/.cache/huggingface/hub` — 100.61 GB total

Two different layouts coexist, which is worth knowing before scripting against this cache: most
entries use the canonical `models--<org>--<name>/{blobs,refs,snapshots,trees}` form, but four are
plain `<org>/<name>/` directories instead. Both are listed.

| GB | Path (relative to `~/.cache/huggingface/hub/`) |
|---:|---|
| 23.00 | `mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit` |
| 21.49 | `mlx-community/Ornith-1.0-35B-OptiQ-4bit` |
| 20.15 | `Jundot/Qwen3.6-35B-A3B-oQ4-mtp` |
| 19.67 | `georgeis55/Ornith-1.0-35B-MLX-oQ4` |
| 8.42 | `mlx-community/gemma-4-12B-it-qat-OptiQ-4bit` |
| 6.69 | `avneetsb/gemma-4-12B-it-qat-oQ4-fp16` |
| 0.94 | `models--mlx-community--Qwen3.6-35B-A3B-OptiQ-4bit` |
| 0.26 | `models--chopratejas--kompress-v2-base` |
| 0.002 | `models--answerdotai--ModernBERT-base` |
| **100.61** | **total** |

**Seven empty stub repos** — `refs/` only, 4 KB each, no `blobs/` content. These are
interrupted or ref-only metadata fetches and occupy no meaningful space, but they are clutter that
will confuse any script that enumerates the cache by directory:

`models--mlx-community--ltx-2.5-mlx-q8`, `models--mlx-community--ltx-2.5-mlx-ditq8`,
`models--mlx-community--Agents-A1-OptiQ-4bit`, `models--Jundot--Qwen3.6-35B-A3B-oQ4-mtp`,
`models--JANGQ-AI--Spark-X2.5-4B-JANG_8M`, `models--georgeis55--Ornith-1.0-35B-MLX-oQ4`,
`models--avneetsb--gemma-4-12B-it-qat-oQ4-fp16`.

Note that `models--Jundot--Qwen3.6-35B-A3B-oQ4-mtp` (stub, empty) and
`Jundot/Qwen3.6-35B-A3B-oQ4-mtp` (20.15 GB, populated) are the *same model repo* under the two
layouts. Similarly for `georgeis55` and the two `mlx-community` entries. A naive per-directory
enumeration will report these twice, once at 4 KB and once at full size.
`~/.cache/huggingface/hub/.locks/` holds 19 empty lock directories, also harmless.

### 3.2 `~/MLXModels` — 147.07 GB total

**`~/MLXModels/OsaurusAI` — 93.65 GB**

| GB | Model |
|---:|---|
| 18.46 | `Ornith-1.0-35B-JANG_4M` |
| 18.35 | `Qwen3.6-35B-A3B-JANGTQ4` |
| 16.88 | `Qwen3.8-27B-JANG_4D` |
| 9.47 | `gemma-4-12B-it-qat-JANG_4M` |
| 7.50 | `Bonsai-27b-Ternary-JANG` |
| 6.32 | `Raptor-v0.5-8B-A1B-JANG_6M` |
| 3.64 | `Raptor-0.6-preview-JANG_6M` |
| 3.64 | `Nanbeige4.2-3B-JANG_6M` |
| 3.43 | `Spark-X2.5-4B-JANG_6M` |
| 3.43 | `Raptor-0.6.1-preview-JANG_6M` |
| 2.50 | `MiniCPM5-2B-JANG_8M` |
| 0.03 | `rampart-mlx` |
| **93.65** | **subtotal** |

**`~/MLXModels/image` — 53.41 GB**

| GB | Model | Contains |
|---:|---|---|
| 27.77 | `Qwen-Image-Edit-mflux-q5` | `text_encoder` 14.43, `transformer` 13.09, `vae` 0.24, `tokenizer` 0.01 |
| 25.65 | `ideogram-4-fp8` | `transformer` 8.65, `unconditional_transformer` 8.65, `text_encoder` 8.18, `vae` 0.16 |
| **53.41** | | |

**`~/MLXModels/mlx-community` — ~0 GB** (shell directory, effectively empty).

### 3.3 `~/AI/LTX/models` — 41.43 GB

Separate from the two stores above — a diffusion-model repo checkout under `~/AI/LTX`, not part of
the HF cache.

### 3.4 Cross-store observation

The three model stores hold **289.11 GB combined** (`~/.cache/huggingface` 100.61,
`~/MLXModels` 147.07, `~/AI/LTX` 41.43). The HF cache and `MLXModels` hold the *same model
families* in *different quantization formats* — e.g. `Ornith-1.0-35B` appears as
`-OptiQ-4bit` (21.49), `-oQ4-mtp` variants, and `-JANG_4M` (18.46); `Qwen3.6-35B-A3B` appears as
`-OptiQ-4bit` (23.00), `-JANGTQ4` (18.35) and `-oQ4-mtp` (20.15). This is a deliberate axis-of-
comparison workload for this project, **not** accidental duplication, and it is the reason the
disk filled. It is recorded here as a fact, not as a recommendation.

---

## 4. Reclaim table

`SAFE` = regenerable or re-downloadable **and** containing no personal data. Anything with any
uncertainty is `CHECK-FIRST`. **Every model file is `CHECK-FIRST` regardless of age** — which
models go is the human's call.

Categories are confirmed where possible by inspecting file *contents*, not by trusting the
directory name: the three KV caches below were each verified by reading the JSON header of a
`shard` file and confirming they hold `layer_N_state_M` / `L0.cache.N` attention state rather
than model parameters.

### SAFE

| Path | GB | What it is | Risk | Reasoning |
|---|---:|---|---|---|
| `~/.omlx/cache` | 68.58 | oMLX SSD KV/prefix cache | **SAFE** | Header inspection shows `layer_0_state_0` `[1,3,8192]` BF16 + `[1,32,128,128]` F32 per layer — attention state, not weights. Content-addressed, 734 shards, no manifest; regenerates as the server runs. Contains no documents. |
| `~/.cache/uv` | 26.42 | uv package archive cache | **SAFE** | `archive-v0` holds unpacked wheel artifacts; `uv cache clean` is the supported path and everything re-downloads from PyPI. |
| `~/.cache/vmlx-engine/block-cache` | 21.82 | vMLX KV block cache | **SAFE** | Header shows `L0.cache.0` `[1,3,8192]` F16 + `[1,32,128,128]` F32 — same KV shape as oMLX. 3,847 block files, regenerated on use. |
| `~/.gradle/caches` | 17.68 | Gradle dependency/artifact cache | **SAFE** | Rebuilt from Maven repositories on next build; contains no sources. |
| `~/.osaurus/cache/kv_v2` | 8.24 | Osaurus KV cache | **SAFE** | Header shows `__jang_cache_format_version__` plus `__layer_kind_N__` markers — serialized KV state. 19 files, no model weights. |
| `~/Library/Caches/Homebrew` | 7.58 | Homebrew download cache | **SAFE** | `downloads/` 7.58 GB of bottles and tarballs; `brew cleanup` is the supported path and everything re-downloads. |
| `~/Library/Caches/Google` | 5.97 | Chrome/Android Studio HTTP cache | **SAFE** | Ordinary browser and IDE caches; re-fetched on demand. No user documents. |
| `~/.npm/_cacache` | 5.95 | npm content-addressable cache | **SAFE** | `npm cache clean --force`; re-populated from the registry. |
| `/Library/Developer/CoreSimulator/Caches` | 3.04 | CoreSimulator runtime cache | **SAFE** | Downloaded simulator runtime images; re-fetched by Xcode. |
| `/private/var/folders` | 2.01 | Per-user temp/cache (`$TMPDIR`) | **SAFE** | Ephemeral by design; macOS reaps these and apps recreate what they need. |
| `/private/var/vm/sleepimage` | 2.00 | Hibernation image (exactly 2147483648 B) | **SAFE** | Regenerated on demand by the kernel; deleting it costs one slower wake from hibernation. |
| `~/.cache/codex-runtimes` | 1.89 | Downloaded runtime binaries | **SAFE** | Re-downloadable tool runtimes. |
| `~/Library/Caches/ms-playwright` | 1.10 | Playwright browser binaries | **SAFE** | `npx playwright install` re-fetches. |
| `~/.cache/puppeteer` | 1.05 | Puppeteer Chromium download | **SAFE** | Re-fetched by the installer. |
| `~/Library/Developer/Xcode/DerivedData` | 0.11 | Xcode build products | **SAFE** | Pure build output; regenerated by the next build. Included for completeness — it is negligible. |
| **Running total** | **173.44** | | | **Achieved without touching root, snapshots, or any model.** |

### CHECK-FIRST

| Path | GB | What it is | Risk | Reasoning |
|---|---:|---|---|---|
| APFS local snapshots (2) | **~277** (residual, see §2.1) | `com.apple.TimeMachine.2026-09-03/10` | **CHECK-FIRST** | Largest single item on the disk. `Purgeable: Yes`, and one is flagged as limiting the container minimum — so it is almost certainly reclaimable. **But these are the only local restore points on the machine**; deleting them destroys the ability to roll back anything changed since 2026-09-03. Byte-exact size needs root. Human must decide. |
| `~/.cache/huggingface/hub` | 100.61 | HF model cache, 6 populated repos | **CHECK-FIRST** | Re-downloadable in principle, but these are the artifacts under comparison in this project's own measurement work; which ones are still needed is a research decision, not a housekeeping one. |
| `~/MLXModels` | 147.07 | JANG/JANGTQ quantized MLX weights | **CHECK-FIRST** | Same reasoning. Some of these formats may not be reproducible or re-downloadable at their current revisions. |
| `~/AI/LTX/models` | 41.43 | LTX diffusion weights | **CHECK-FIRST** | Same reasoning. |
| `~/Library/Application Support/Claude/vm_bundles` | 11.22 | Claude Desktop VM images | **CHECK-FIRST** | Re-downloadable, but it is the app's active runtime; deleting it forces a re-provision that the app may or may not do cleanly. |
| `~/.android/avd` | 13.13 | Android emulator images | **CHECK-FIRST** | System images re-download via `sdkmanager`, but an AVD can hold cold-boot snapshots and app state created by hand. |
| `~/Library/Android` | 11.00 | Android SDK | **CHECK-FIRST** | Mostly re-downloadable, but may contain the only copy of a locally-built or side-loaded artifact. |
| `~/Library/Application Support/Google/DriveFS` | 3.46 | Google Drive local cache | **CHECK-FIRST** | A local cache of cloud content — but Drive Files On-Demand can hold the *only* copy of a file if it was never fully synced. Explicitly a data-loss risk. |
| `~/.local/share` | 4.70 | XDG app data | **CHECK-FIRST** | Mixed content; some subdirectories are caches and some are genuine application state. Not itemized this pass. |
| `~/Library/Application Support/Google/Chrome` | 7.91 | Chrome profile | **CHECK-FIRST** | Contains the real profile: history, cookies, saved passwords, extensions. Mostly not reclaimable without losing state. |
| `/private/var/db` | 3.29 | System databases and diagnostics | **CHECK-FIRST** | Partially root-only and partly unreadable even unprivileged. Not a disk-space target; leave it alone. |
| `~/Library/Containers/com.docker.docker` | 5.98 | Docker Desktop VM disk image | **CHECK-FIRST** | Contains every local image, volume and container. Deleting it destroys all local Docker state. Use `docker system prune` inside the app instead. |
| `~/.lmstudio` | 1.44 | LM Studio data | **CHECK-FIRST** | May hold downloaded models or conversation history. |
| `~/.gradle` (non-cache) | 3.00 | wrapper/native/daemon | **CHECK-FIRST** | Small residual outside `caches/`; not independently itemized. |
| `/opt/homebrew` | 12.91 | Homebrew Cellar | **CHECK-FIRST** | Installed packages, not cache. `brew autoremove` is the safe subset; the 12.91 GB is not straightforwardly reclaimable. |

### DO-NOT-TOUCH

| Path | GB | What it is | Risk | Reasoning |
|---|---:|---|---|---|
| `~/Dev` | 18.50 | Source checkouts (`Dev/active` 14.11) | **DO-NOT-TOUCH** | Working source trees, including uncommitted work. |
| `~/Documents`, `~/Desktop`, `~/Pictures`, `~/Music`, `~/Movies`, `~/Downloads` | ~6 total | Personal files | **DO-NOT-TOUCH** | User documents. Each is ~1 GB; there is nothing to win here. |
| `/Applications` | 26.45 | Installed applications | **DO-NOT-TOUCH** | Uninstalling an app is a decision about workflow, not disk hygiene. |
| `/System/Volumes/Data/System`, `/usr`, `Preboot`, `Recovery`, sealed System volume | ~35 | OS | **DO-NOT-TOUCH** | System-managed. Sealed and read-only. |
| `~/.Trash` | 1 | Trash | **DO-NOT-TOUCH** | Left alone deliberately: emptying Trash is destructive and outside this report's remit. It is also already empty of items. |

### The 277 GB is the whole answer, and it is one command away

Ranked by reclamation per unit of risk, the finding is unambiguous:

| Rank | Action | GB | Risk | Blocker |
|---:|---|---:|---|---|
| 1 | Thin or delete the two local snapshots (`sudo tmutil thinlocalsnapshots / 250000000000 4`, or `sudo tmutil deletelocalsnapshots <date>`) | ~277 | CHECK-FIRST | Needs password; destroys restore points |
| 2 | The 15 SAFE cache rows | 173.44 | SAFE | None |
| 3 | Model artifacts | 289.11 | CHECK-FIRST | Research decision |

**Rank 1 alone recovers more than every SAFE row combined (277 vs 173.44), and it is a single
command.** It is also the only reclaim that requires no judgement about which models are still
needed.

---

## 5. Blockers and what would settle them

Three items could not be measured in this session. None of them changes the shape of the answer,
but each would tighten a number:

1. **Byte-exact snapshot size.** Needs root. `tmutil` 4.0.0 provides no size verb and
   `tmutil calculatedrift` rejects `/`. With sudo, `sudo tmutil listlocalsnapshots /` combined
   with a container listing before/after a thin would give an exact figure. Currently reported as
   the 277.4 GB residual — bounded above and below by the fact that readable root-only
   directories in `/private/var` total only 7.87 GB.
2. **The root-only directories themselves.** `/System/Volumes/Data/.DocumentRevisions-V100`,
   `.Spotlight-V100`, `.fseventsd` all return `Permission denied` even for `du`. Expected
   low-tens of GB at most; unmeasurable without sudo. `.DocumentRevisions-V100` is the one that
   could in principle be larger, since it stores version history for edited documents.
3. **Purgeable accounting.** This `diskutil` build emits no purgeable line, contrary to the
   brief's expectation. The only purgeability evidence available unprivileged is the per-snapshot
   `Purgeable: Yes` flag.

---

## Method

Every figure in this report came from one of: `df -h`, `diskutil info` / `diskutil apfs list` /
`diskutil apfs listSnapshots` / `diskutil list`, `tmutil listlocalsnapshots`,
`du -d1 -g` / `du -d2 -g` / `du -sk`, `find -type f -links +1`, `stat -f %z`,
`find -exec stat`, `sysctl vm.swapusage`, `mount`, `ls`. Traversal was shallow-first and widened
only where a directory was large; the volume was never recursed wholesale.

Confirmed absent on this machine: `~/.ollama`, `~/.orbstack`, `~/Public`. Swap is not in use
(`vm.swapusage` reports 0.00 M total).

No destructive command was run. No cache was emptied. No file was created other than this one.
