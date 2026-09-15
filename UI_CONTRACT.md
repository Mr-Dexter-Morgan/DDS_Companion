# DDS Companion 0.4.3 — UI Contract

## Preserve accepted surfaces

Dashboard, Library and Activity keep the 0.4.2 information architecture and
must not be redesigned as part of the Health patch.

## Compact brand

At the compact 1366x768 profile the sidebar must leave enough room for the full
**DDS Companion** brand. Truncation to `DDS Compan` is a defect.

## Health

Health is scroll-safe and shows six runtime/informational cards:

- Database
- DDS_Data
- Importer
- Watcher
- Discord
- Update check

Critical archive health comes from Database / DDS_Data / Importer / Watcher /
runtime. Discord being closed and updater telemetry being absent are
informational and must not degrade the archive.

Watcher heartbeat expiry is displayed as **STALE**. STALE is yellow/warning and
causes overall DEGRADED while the watcher is expected to be running.

The Update check card must be truthful: until a real updater performs checks it
shows NEVER and empty timestamps; it must not fabricate a successful check.

The Last error area shows the active unresolved failure with subsystem/job kind
and timestamp; a resolved historical failure is not presented as current.

## Settings contract retained

Settings opens on **Основные**. Paths & Storage remains the secondary,
vertically-scrollable service-path surface with Copy/Open actions.
