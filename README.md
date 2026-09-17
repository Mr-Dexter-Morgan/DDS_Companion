# DDS Companion 0.5.0 — Media Backfill Core Candidate r2

Status: **CANDIDATE / AUTOMATED PASS / WINDOWS LIVE PENDING**  
Baseline: **0.4.6 — VERIFIED / LIVE TESTED / CURRENT RECOMMENDED**  
Date: **2026-09-17**

## What this release is

0.5.0 opens Stage 4 — Media Layer. The archive/import/UI foundation from 0.4.6 is preserved; this release adds a separate, failure-isolated media subsystem for Discord attachment caching.

The media worker runs independently from capture/import/UI work. A slow CDN request, expired signed URL, oversized attachment, full disk, or one broken download must not freeze the Companion or damage the archive.

## New in 0.5.0

- SQLite schema v3 with durable `media_objects` and `media_refs` tables.
- One-time projection of pre-0.5 attachment rows into the new registry without reimporting or rewriting archived messages.
- Stable media identity by Discord attachment ID, with message/position fallback.
- Media lifecycle states: `KNOWN`, `QUEUED`, `DOWNLOADING`, `CACHED`, `SKIPPED`, `TOO_LARGE`, `FAILED_RETRYABLE`, `FAILED_PERMANENT`, `STALE_URL`, `EVICTED`.
- Separate media runtime thread and separate SQLite connection; archive watcher/UI are never blocked by media I/O.
- Bounded downloader: two workers by default, request timeout, streamed writes, temporary `.part` staging and atomic final rename.
- SHA-256 and actual cached size recorded after successful download.
- Strict Discord-media host allowlist to prevent capture data from turning Companion into an arbitrary URL fetcher.
- Bounded retries with exponential backoff and Retry-After respect for HTTP 429.
- Signed/expired URL classification: HTTP 401/403/404 becomes `STALE_URL` and waits for a refreshed capture URL instead of hammering the network.
- Size policy before and during download; oversized items never remain in cache.
- Cache eviction/cleanup updates registry to `EVICTED` while preserving message/attachment metadata.
- `EVICTED` deliberately does not auto-requeue, preventing download → eviction → re-download loops. Manual Clear is tagged separately: an explicit Automatic media download Off → On transition re-arms only those manually cleared entries, while policy-evicted entries remain EVICTED. Compatibility: r1 EVICTED rows had no reason tag; an explicit Off → On in r2 may re-arm those legacy ambiguous rows once, after which any new policy eviction receives the safe r2 policy tag and cannot loop.
- Real persistent `Automatic media download` switch in Settings → Data & Storage. Default is **Off** for safe upgrade behavior.
- Health gains a separate non-critical `Media Backfill` subsystem.
- Activity records media success, retry, stale URL, permanent failure, cache maintenance and explicit Automatic media download enabled/disabled transitions. Rapid toggle actions are queued so they are not silently coalesced.
- Dashboard/Stats continue to show known/cached media and real media cache bytes. Storage bars now use the same per-category colors as the donut chart.
- Diagnostics report media subsystem state and queue/failure counters.

## Data-safety invariants

1. SQLite messages, DDS JSON and attachment metadata are source-of-truth archive data.
2. Media binaries are replaceable cache.
3. Media clear/eviction can remove cache files only; it cannot delete archived messages or attachment metadata.
4. Media failures are non-critical: they may make the Media subsystem `LIMITED`, but they do not make the whole local archive unusable.
5. Network work is disabled by default after upgrade until the user explicitly enables automatic media download.
6. Filenames never control cache paths; cache filenames are derived from stable media keys/hashes.
7. Only HTTPS Discord media hosts are eligible for automatic download.

## Current scope

0.5.0 backfills **Discord attachments** already known to the archive. Embeds remain metadata-only in this release. Rich per-type autodownload policies, manual per-item fetch, search/history, Drive/AI sync, updater and final installer remain later stages.

## Run

Normal desktop launch:

`run_companion.bat`

The source/dev launcher automatically installs PySide6 if it is missing. The final 1.0 installer will bundle/runtime-manage dependencies without exposing pip to ordinary users.

## Validation

Automated gate: **70/70 PASS**, repeated three consecutive runs on the r2 source tree; `compileall` and CLI version checks PASS.

Run:

`python -m unittest discover -s dds_companion/tests -v`

Also see:
- `VALIDATION.txt`
- `MEDIA_BACKFILL_CONTRACT.md`
- `LIVE_TEST_CHECKLIST_0.5.0.txt`
- `OBSERVABILITY_CONTRACT.md`
- `UI_CONTRACT.md`

0.5.0 must not replace 0.4.6 as current recommended until the Windows live gate passes.
