# DDS Companion Observability Contract — v0.4

This contract defines the state consumed by the PySide6 GUI, tray, diagnostics
and future updater surfaces.

## Rule 1 — presentation does not own state

The GUI must not infer health from console strings or raw widget state.
Use:

- `ActivityService` for human runtime events;
- `HealthService` for subsystem and capture-chain state;
- `StatsService` for counters, storage and session deltas.

## Activity contract

Each Activity record contains occurrence time, level, subsystem, event type,
human summary and structured details, with optional capture/guild/channel/thread
context and import counters.

Presentation subscribers are best-effort. A UI/subscriber failure must never
break capture/import.

### Health transition journal policy

Health refresh may run frequently, but Activity records only meaningful change:

- `health_initial_state` for an initially non-RUNNING state;
- `health_state_changed` when overall state changes;
- `health_reason_changed` when the reason set changes without a state change;
- `health_recovered` on return to RUNNING.

Do not emit repeated identical LIMITED/STale warnings on every refresh.

## Health contract

Persisted or derived subsystem state may include:

- STARTING
- RUNNING
- LIMITED
- STALE
- ERROR
- STOPPED
- NOT RUNNING
- WAITING
- UPDATE AVAILABLE
- NEVER
- UNKNOWN

Historical persisted `DEGRADED` values are accepted and normalized to LIMITED.

Overall state rules:

1. critical local database failure -> ERROR;
2. unavailable capture-chain dependency (Discord, DDS Plugin, DDS_Data), stale
   required heartbeat, unresolved import/runtime failure, or equivalent partial
   availability -> LIMITED;
3. informational updater telemetry such as NEVER does not limit the core;
4. otherwise -> RUNNING.

A closed Discord or stopped plugin is not itself a Companion application error:
the local archive remains usable. It limits new capture only.

## DDS Plugin heartbeat contract (consumer side)

Companion recognizes `plugin_heartbeat.json` under DDS_Data when the plugin
advertises `plugin-heartbeat-v1` or reports a heartbeat-capable version.
Expected fields:

- `schemaVersion`
- `plugin`
- `pluginVersion`
- `state`
- `updatedAt`
- `heartbeatIntervalMs`
- `captureSchemaVersion`

Fresh RUNNING -> RUNNING. Explicit STOPPED -> NOT RUNNING. If Discord is definitively NOT RUNNING, a fresh/stale heartbeat is dependency-overridden to NOT RUNNING while heartbeat metadata remains available. Age thresholds are
computed from the advertised interval with safe minimums. A pre-heartbeat
stable plugin is shown as UPDATE AVAILABLE instead of being falsely marked
broken.

## Watcher/source distinction

A live watcher thread does not imply a live source. If DDS_Data is absent,
Watcher presentation state is WAITING even if the observer loop itself still
exists. This distinction prevents green-but-useless diagnostics.

## Stats contract

Stats snapshots remain cheap and contain only derived counters/sizes, never
message payloads. Storage accounting avoids double-counting and includes SQLite
main/WAL/SHM, DDS_Data, cache, media and logs where applicable.

## Failure containment

- Activity persistence failure must not abort import.
- Presentation subscriber failure must not abort import.
- Health callback failure must not kill watcher.
- One capture failure must not stop observation of others.
- Loss of Discord/DDS Plugin/DDS_Data must not make the archived library
  unavailable.
