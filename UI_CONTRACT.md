# DDS Companion 0.4.0 — UI Contract

## Visual direction

- Dark, restrained, professional desktop utility.
- Graphite base, slightly lighter panels, blue/violet accent.
- Accent is semantic, not decorative noise.
- Native window chrome is retained for predictable Windows behavior.
- No fake hacker terminal aesthetic.
- No animation required for core usability.
- Dashboard must remain readable at a glance.

## Navigation

Persistent left rail:

1. Dashboard
2. Library
3. Activity
4. Health
5. Settings

Brand and version stay visible. A small `LOCAL FIRST` card states that the archive remains local.

## Top bar

Always visible:

- latest transient/persisted activity text;
- `Open library` quick action;
- overall `RUNNING / DEGRADED / ERROR / STARTING / STOPPED` pill.

## Dashboard

Top actions:

- Open library folder
- Open DDS_Data
- Open logs
- Refresh

Primary metric cards:

- Total known storage
- Message count
- Guild / channel / thread counts
- Known / cached media

Secondary panels:

- Latest activity
- Four subsystem health rows
- Storage breakdown
- Current-session growth

## Library

Read-only structural tree:

`Server → Channel → Thread`

Each node displays message count and immutable Discord ID. A local tree filter can narrow visible nodes. It does not pretend to be full-text message search.

## Activity

Table columns:

- local time
- level
- subsystem
- event type
- human summary

Backed by persisted Activity API, newest first.

## Health

Shows:

- overall state
- Database
- DDS_Data
- Importer
- Watcher
- subsystem summary and updated time
- last error / clean state

## Settings

0.4.0 intentionally keeps policies read-only. It exposes Paths & Storage with direct actions for:

- Companion library/data root
- DDS_Data
- SQLite database folder
- Logs
- Media cache
- Cache
- Backups

Each path can be selected/copied and opened through the native file manager.

Watcher poll/settle values are visible. Editing policies belongs to a later release so the first GUI milestone does not mix presentation with configuration mutation.

## Threading boundary

- SQLite connection lives on the Companion runtime thread.
- Qt main thread receives plain snapshots/events.
- GUI widgets never perform archive writes.
- Observer callback failures are ignored by archive/watch code.
- Manual refresh is a thread-safe request flag, not a cross-thread SQLite call.

## Non-goals for 0.4.0

- Media downloading
- Full-text message search
- Message edit/version browser
- Drive sync
- Tray/background-on-window-close behavior
- Editable watcher/media/sync policies
- Installer/productization

These are deliberately excluded to keep one clear release task: **first production-shaped desktop dashboard over the verified Companion core**.
