# DDS Companion 0.5.0 — Media Backfill Contract

Status: **IMPLEMENTED IN 0.5.0 CANDIDATE r2 / LIVE VALIDATION PENDING**  
Date: **2026-09-17**

## 1. Layer boundary

Archive metadata and media binaries are different classes of data.

```text
DDS Plugin capture JSON
        ↓
Importer / SQLite archive     ← source of truth
        ↓
Media Registry / Queue        ← durable lifecycle
        ↓
Media Downloader              ← bounded network I/O
        ↓
Media Cache                   ← replaceable binaries
```

No media operation may delete or rewrite archived messages merely because a file cannot be downloaded or is evicted.

## 2. Identity

Primary identity: `attachment:<Discord attachment id>`.
Fallback identity when an attachment ID is missing: `message:<message id>:position:<n>`.

URLs and filenames are metadata, not identity. Signed Discord URLs may rotate or expire.

## 3. State machine

- `KNOWN` — metadata exists; eligible for planning.
- `QUEUED` — planner approved a bounded download attempt.
- `DOWNLOADING` — worker owns the current attempt.
- `CACHED` — complete local file exists and size/hash metadata were committed.
- `SKIPPED` — not eligible automatically (for example missing/unsupported URL).
- `TOO_LARGE` — blocked by current max-file or total-cache policy; re-evaluated if policy changes.
- `FAILED_RETRYABLE` — transient failure with bounded backoff.
- `FAILED_PERMANENT` — retry budget/permanent response exhausted; waits for metadata change.
- `STALE_URL` — signed/media URL unavailable; waits for a refreshed capture URL.
- `EVICTED` — binary intentionally removed while metadata remains. Policy eviction stays EVICTED to prevent thrash. Manual Clear is tagged `evicted_manual_clear`; only an explicit user Automatic media download Off → On action re-arms those rows to `KNOWN`. Startup, URL rotation and ordinary planner cycles do not re-arm them.

Crash recovery: an abandoned `DOWNLOADING` claim older than the safety window returns to `QUEUED`.

## 4. Upgrade behavior

Pre-0.5 databases already contain `attachments`. Because unchanged captures are deduplicated, 0.5.0 performs a one-time projection from those rows into `media_objects`/`media_refs` on the isolated media thread. It does not force a destructive reimport.

## 5. Network rules

- Automatic media download is Off by default after upgrade.
- Only HTTPS Discord-owned media hosts are eligible.
- Redirect/final URL hosts are validated again.
- Two workers by default; concurrency is deliberately bounded.
- Requests have a finite timeout.
- Payload is streamed; configured max size is enforced before and during transfer.
- HTTP 429 and transient 5xx/network failures use bounded exponential retry.
- HTTP 401/403/404 becomes `STALE_URL`, waiting for future capture metadata rather than looping.

## 6. Filesystem rules

- Cache target names are SHA-256-derived from the stable media key; user-controlled filenames never define directories.
- Downloads first write `.part` files under `media/.staging`.
- Only complete downloads are atomically renamed into `media/objects/...`.
- Partial files are not considered cache and are excluded from normal cache cleanup.
- Final cached content stores SHA-256 plus actual size.

## 7. Cache rules

Settings are authoritative:
- total cache limit;
- max single media file;
- retention age.

Registered media uses explicit cached/last-access timestamps. Orphan/manual files use mtime as a conservative fallback.

Eviction and Clear Media Cache affect binaries only. Registry entries become `EVICTED`; message/attachment metadata remains queryable. Eviction reason is retained internally so manual Clear can be distinguished from policy eviction.

Manual-clear recovery rule:
- Clear while automatic download is Off (or On) leaves the cache empty and rows EVICTED;
- no immediate refill occurs;
- a later explicit Off → On user transition re-arms only `evicted_manual_clear` rows;
- policy-evicted rows are never resurrected by this action.
- candidate-r1 compatibility: old EVICTED rows did not store an eviction reason (`failure_class` was NULL). r2 treats those rows as legacy-ambiguous only during an explicit user Off → On action, allowing recovery of an r1-cleared cache without DB surgery. Once touched by r2, future policy eviction is reason-tagged and cannot repeatedly resurrect.

## 8. Failure containment

A single failed attachment cannot:
- stop another media download;
- stop DDS_Data watching/import;
- crash the GUI runtime;
- corrupt SQLite archive data;
- turn the entire Companion ERROR merely because media is unavailable.

Media has its own Health subsystem and Activity events. It may report `LIMITED` while Overall Health remains usable when archive/capture layers are healthy.

## 9. Deferred

Not part of 0.5.0:
- embed-image/video backfill;
- per-type/server/channel autodownload policy;
- manual item-level re-fetch UI;
- Drive/AI export sync;
- updater / final installer.
