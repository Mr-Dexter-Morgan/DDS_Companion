# DDS Companion Observability Contract — v0.5

This contract defines the state consumed by the PySide6 GUI, diagnostics and future product surfaces.

## Rule 1 — presentation does not own state

The GUI must not infer operational truth from console strings or widget state.
Use:
- `ActivityService` for human runtime events;
- `HealthService` for subsystem/capture/media state;
- `StatsService` for counters, storage and session deltas;
- Media registry state for known/queued/downloading/cached/failure lifecycle.

Presentation subscribers are best-effort. A UI/subscriber failure must never break capture/import/media work.

## Activity contract

Activity records occurrence time, level, subsystem, event type, human summary and structured details, with optional capture context and counters.

0.5 media event families include:
- `media_registry_bootstrap`;
- `media_backfill_enabled`;
- `media_backfill_disabled`;
- `media_manual_clear_requeued`;
- `media_cached`;
- `media_retry_scheduled`;
- `media_url_stale`;
- `media_failed_permanent`;
- `media_skipped` / `media_skipped_too_large`;
- `media_cache_maintenance`;
- `media_worker_iteration_failed`.

## Health contract

Persisted/derived subsystem state may include STARTING, RUNNING, LIMITED, STALE, ERROR, STOPPED, NOT RUNNING, WAITING, UPDATE AVAILABLE, NEVER and UNKNOWN.

Critical local archive/capture subsystems remain database, DDS_Data, importer, watcher and runtime. `media` is intentionally non-critical: media failure is surfaced in its own card/details but does not make archived messages unusable.

Overall rules remain:
1. critical local database failure -> ERROR;
2. unavailable capture-chain dependency / unresolved critical import/runtime condition -> LIMITED;
3. optional/non-critical subsystem degradation is visible without falsely declaring the archive dead;
4. otherwise -> RUNNING.

## DDS Plugin heartbeat contract

Companion consumes `plugin_heartbeat.json` under DDS_Data for Plugin 0.5.3+ (`plugin-heartbeat-v1`). Discord process state can override a still-fresh heartbeat so Plugin cannot remain falsely green after Discord closes.

## Media observability

Media Health details include known/cached/queued/downloading/retry/stale/permanent-failure/too-large/skipped/evicted counts plus the last cycle summary.

Signed URL expiration is a media condition, not an archive failure. Retryable errors have a scheduled next attempt; stale URLs wait for refreshed capture metadata; permanent failures stop retrying automatically. Explicit UI autodownload toggles are queued so rapid Off/On sequences produce ordered Activity evidence instead of being collapsed into the final state.

## Stats contract

Stats snapshots contain derived counters/sizes, never message payloads. Storage accounting includes SQLite main/WAL/SHM, DDS_Data, media, logs and other Companion data without treating archive metadata as cache.

Known/cached media counters come from the durable media registry. Physical media bytes come from the filesystem.

## Failure containment

- Activity persistence failure must not abort import.
- Presentation subscriber failure must not abort import.
- Health callback failure must not kill watcher.
- One capture failure must not stop observation of others.
- One media failure must not block other media jobs.
- Media network/disk work runs outside the archive watcher/UI runtime thread.
- Loss of Discord/DDS Plugin/DDS_Data must not make the archived library unavailable.
