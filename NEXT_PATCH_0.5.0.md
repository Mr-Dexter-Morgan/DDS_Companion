# DDS Companion 0.5.0 — Media Backfill Core

Status: **IMPLEMENTED / CANDIDATE r2 / AUTOMATED PASS / WINDOWS LIVE PENDING**  
Date: **2026-09-17**

## Goal

Open Stage 4 without weakening the proven archive/UI foundation. Add a bounded media-cache backend for Discord attachments while keeping archive ingestion, SQLite, Watcher and UI operational if media networking fails.

## Reliability laws for this layer

1. Archive/message metadata is durable source-of-truth data; downloaded media bytes are replaceable cache.
2. Media work runs on an isolated runtime thread with its own SQLite connection.
3. One failed media object never terminates the queue, Watcher, archive importer or UI.
4. Network work is opt-in on upgrade (`Automatic media download` defaults Off), bounded and timeout-limited.
5. Files are downloaded into `.staging` and promoted by atomic replace only after a complete transfer.
6. Cache deletion/eviction may remove binary files only; it may never delete messages, attachment metadata, DDS JSON or SQLite archive rows.
7. Every durable media object has an explicit lifecycle state and diagnostic reason.
8. Retry is bounded; permanent/stale failures are surfaced rather than hammered forever.
9. Only HTTPS Discord-owned media hosts are eligible; redirects are validated too.
10. Media problems are visible in Media Health, but a healthy local archive can remain overall RUNNING.

## Implemented scope

### Media registry / schema v3
- additive `media_objects` and `media_refs` tables;
- stable attachment identity, with message+position fallback when an attachment ID is unavailable;
- URL observation, attempt/retry data, local path/size/hash, cache timestamps and failure diagnostics;
- one-time idempotent projection of pre-0.5 `attachments` rows into the registry.

### Lifecycle
`KNOWN -> QUEUED -> DOWNLOADING -> CACHED`

Additional terminal/holding states:
- `SKIPPED`
- `TOO_LARGE`
- `FAILED_RETRYABLE`
- `FAILED_PERMANENT`
- `STALE_URL`
- `EVICTED`

`EVICTED` is an intentional anti-thrash state. Policy eviction never auto-resurrects. Manual Clear is tagged separately and stays EVICTED until the user explicitly toggles Automatic media download Off → On; that explicit action re-arms only manually cleared entries.

### Planner / downloader
- recovers abandoned DOWNLOADING claims after a bounded age;
- reconciles missing physical files with cached registry rows;
- enforces configured max-file and total-cache policy before network when metadata allows;
- max 2 concurrent workers by default, hard-clamped to 4;
- 15 second request timeout by default, hard bounded;
- streaming transfer with a configured byte ceiling;
- SHA-256 recorded for successfully cached files;
- expected-size mismatch is retryable instead of silently accepting a partial file;
- HTTP 401/403/404 -> `STALE_URL`;
- HTTP 429/5xx/network/IO -> bounded retry with exponential backoff / Retry-After support;
- retry limit -> `FAILED_PERMANENT`;
- unsupported hosts are rejected before opening a network connection.

### Cache maintenance integration
- existing 0.4.6 cache size / max-file / retention settings now govern real registered media;
- registered media uses last-access/cached-at ordering; orphan/manual files safely fall back to mtime;
- `.staging` is outside normal clear/eviction operations;
- deleted cached registry files become `EVICTED`, while archive metadata stays intact.

### UI / observability
- real persisted `Automatic media download` toggle in Data & Storage;
- dedicated `Media Backfill` Health card;
- Dashboard known/cached values and storage chart use registry/physical cache truth;
- diagnostics report media state and queue/failure counters;
- Activity receives cached/retry/stale/failure/maintenance events plus explicit autodownload enabled/disabled transitions; rapid UI toggles are carried through a command queue instead of a coalescing Event.
- Storage bars use the same category colors as the donut chart for visual correlation.

## Deliberately deferred

Not in 0.5.0:
- embed-image/video backfill beyond Discord attachment objects;
- per-type Images/Video/GIF/Audio policies;
- per-server/channel exclusions;
- per-item manual re-cache UI (global manual-clear recovery is now supported through explicit autodownload Off → On);
- richer Media library/details page;
- search/history stage;
- updater backend;
- Drive/AI export sync;
- final EXE/installer/productization.

## Promotion gate

0.5.0 does **not** become CURRENT RECOMMENDED until `LIVE_TEST_CHECKLIST_0.5.0.txt` passes on Windows against a real 0.4.6 archive and DDS Plugin 0.5.3.
