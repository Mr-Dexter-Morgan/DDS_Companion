# DDS Companion 0.4.5 — UI Contract

## Preserve accepted surfaces

Dashboard, Library and Activity keep their accepted information architecture.
Health changes must not trigger a redesign of working pages.

## Sidebar brand

The navigation header uses three lines:

```text
DDS
Companion
v0.4.5
```

The product name must remain readable in compact layouts without widening the
sidebar merely to fit a single-line brand.

## Health

Health is scroll-safe and shows seven cards/blocks:

- Database
- DDS_Data
- Importer
- Watcher
- Discord
- DDS Plugin
- Update check

User-facing state vocabulary includes:

- RUNNING
- LIMITED
- STALE
- ERROR
- NOT RUNNING
- WAITING
- UPDATE AVAILABLE
- NEVER (update telemetry only)

`DEGRADED` is legacy compatibility input and must not be the normal user-facing
word in 0.4.5.

### Truthfulness rules

- Discord closed -> overall LIMITED, archived data remains available.
- Plugin stopped/stale/unavailable -> overall LIMITED, archived data remains
  available.
- Missing DDS_Data -> overall LIMITED and Watcher displays WAITING.
- Critical local database failure -> ERROR.
- Update-check state NEVER is informational and must not make Health LIMITED.
- Pre-heartbeat plugin versions may display UPDATE AVAILABLE rather than a
  fabricated NOT RUNNING result.

### Explanations

Hovering the overall status pill must show the reason(s) for LIMITED/ERROR.
Hovering each subsystem state word must show the subsystem's own summary.
When multiple reasons exist, the overall tooltip includes all relevant reasons.

### Timing labels

Use truthful labels rather than generic Heartbeat:

- Database — Checked
- DDS_Data — Checked
- Importer — Last import
- Watcher — Heartbeat
- Discord — Checked
- DDS Plugin — Version / Heartbeat

## Activity integration

Health must not write the same warning repeatedly every refresh cycle. Journal
entries are created for:

- first observed non-running state;
- overall state transition;
- reason-set change while state is unchanged;
- recovery to RUNNING.

## Settings contract retained

Settings continues to open on **Основные**. `Paths & Storage` remains the
secondary scrollable service-path surface with Copy/Open actions. Larger
Settings redesign is deferred.
