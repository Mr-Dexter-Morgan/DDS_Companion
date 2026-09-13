# DDS Companion Observability Contract — v0.3

This file defines the contract that future presentation layers (PySide6 GUI, tray UI, diagnostics) should consume.

## Rule 1 — presentation does not own state

The GUI must not calculate archive totals, infer watcher health from console text, or query raw capture files directly.

Use:

- `ActivityService` for human runtime events;
- `HealthService` for subsystem state;
- `StatsService` for dashboard counters/storage/session deltas.

## Activity contract

Each Activity record contains:

- immutable row id when persisted;
- UTC occurrence timestamp;
- level;
- subsystem;
- event type;
- human summary;
- structured details JSON;
- optional capture path / guild / channel / thread context;
- import counters;
- storage delta field reserved for events that can quantify storage change.

Subscribers are best-effort presentation listeners. A subscriber exception is isolated.

Suggested GUI behavior:

- newest first in Activity page;
- INFO/WARNING/ERROR filter;
- subsystem filter;
- click event -> structured details;
- never block the watcher while rendering.

## Health contract

Persisted subsystem row fields:

- subsystem
- state
- summary
- last_ok_at
- last_error_at
- updated_at
- details_json

States:

- STARTING
- RUNNING
- DEGRADED
- ERROR
- STOPPED
- UNKNOWN

Overall state precedence:

1. database failure -> ERROR;
2. unresolved failures, missing DDS_Data, stale watcher, or degraded/error subsystem -> DEGRADED;
3. otherwise RUNNING.

A clean stopped watcher is not an error when watcher monitoring is not expected (for example after shutdown or `--once`).

## Stats contract

A Stats snapshot must remain cheap enough for periodic Dashboard refresh and contain only derived counters/sizes, not message payloads.

Session deltas are measured against a baseline captured once at process start, before the startup import and Activity writes.

Storage accounting includes SQLite main/WAL/SHM, DDS_Data, cache, media, and logs without double-counting the whole app directory.

## Failure containment

Observability is subordinate to archive correctness:

- Activity persistence failure must not abort import;
- presentation subscriber failure must not abort import;
- health callback failure must not kill watcher;
- one capture failure must not stop observation of others.

## 0.4.0 GUI constraint

The first GUI should treat these services as its model layer. It may add presentation-specific models/adapters, but should not move domain logic back into widgets.
