# DDS Companion 0.4.3 — Health Telemetry Patch

Project: **DDS — Discord Data Snatcher**  
Authors: **Mr_Dexter_Morgan, Masya**

> Are you sure your data is secure?

Status: **BUILT / LOCAL TESTING**

0.4.3 is a focused live-telemetry patch over 0.4.2. It keeps the archive/import
core and the successful Dashboard / Library / Activity layout intact while
making Health more truthful and useful during real Windows operation.

## What changed

- Compact sidebar no longer truncates **DDS Companion** to `DDS Compan`.
- Health is scroll-safe and now exposes six cards:
  - Database
  - DDS_Data
  - Importer
  - Watcher
  - Discord
  - Update check
- Database and DDS_Data are live probes in every Health snapshot instead of
  simply repeating startup state.
- Watcher heartbeat expiry is represented explicitly as **STALE**; overall
  Companion health still becomes DEGRADED when a critical subsystem is stale.
- Discord process status is checked on Windows without adding a new dependency.
  `Discord.exe`, `DiscordCanary.exe` and `DiscordPTB.exe` are recognized.
  Discord not running is informational and does not degrade the archive.
- Update-check telemetry is prepared without performing network requests yet.
  Health shows the configured interval and reads last-attempt / last-success /
  next-check values from `application_state` when a future updater writes them.
  Until then the state is **NEVER** and the default interval is 6 hours.
- The last unresolved failure now carries subsystem/job kind and timestamp.
  Once the durable failure is resolved, Health returns to **Ошибок нет** instead
  of presenting an obsolete error as active.

## What did not change

- No archive schema migration.
- Importer, watcher capture semantics and deduplication remain unchanged.
- Dashboard, Library, Activity and Settings information architecture remain as in
  0.4.2.
- No Media Backfill, media cache policy, GitHub updater, AI export or Drive sync
  is enabled in this release.

## Validation

- Python compileall: **PASS**
- Full automated suite: **35/35 PASS**
- Clean regression coverage includes importer/watcher/archive behavior.
- New tests cover STALE watcher state, live DDS_Data probe, update telemetry,
  unresolved-error metadata and Discord tasklist parsing.

Actual Qt rendering and Windows process detection still require the live Windows
check in `LIVE_TEST_CHECKLIST_0.4.3.txt`.
