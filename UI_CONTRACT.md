# DDS Companion 0.4.1 — UI Contract

## Visual direction

- Dark, restrained desktop utility; graphite base with blue/violet accent.
- No fake hacker-terminal aesthetic.
- Total storage and health remain immediately discoverable.
- Layout adapts by rearranging content, not by blindly scaling the whole UI.

## Responsive profiles

The GUI evaluates `availableGeometry()`, `logicalDotsPerInch()`,
`devicePixelRatio()` and current window width.

- **Compact** — short/laptop displays such as 1366x768: tighter margins,
  2x2 metric grid, vertically stacked lower Dashboard cards and scroll-safe body.
- **Standard** — typical 1080p desktop layout.
- **Large** — roomy 2K/4K/high-density presentation with more breathing room.

Profile is recalculated on resize, screen changes, usable-geometry changes and
logical-DPI changes.

## Navigation

Persistent left rail:

1. Dashboard
2. Library
3. Activity
4. Health
5. Settings

Navigation has three deliberately distinct visual states: idle, hover and
selected.  Brand/version and the `LOCAL FIRST` card remain visible.

## Top bar

Always visible:

- latest transient/persisted activity text;
- overall `RUNNING / DEGRADED / ERROR / STARTING / STOPPED` pill.

There is no duplicate Open Library action in the top bar.

## Dashboard

Quick actions:

- Open DDS_Data
- Open logs
- compact secondary Refresh

Primary metrics:

- Total known storage
- Message count
- Guild / channel / thread counts
- Known / cached media

Secondary panels:

- Latest activity
- Four subsystem health rows
- Storage breakdown
- Current-session growth

The body is scroll-safe.  Compact mode prioritizes non-overlap over fitting all
panels above the fold.

## Library

Read-only structural tree: `Server → Channel → Thread`.

This page is the single UI location for **Open library folder**.

## Activity / Health / Settings

Semantics remain the same as 0.4.0.  Settings remain read-only for policy
values; path cards can still copy/open Companion, DDS_Data, SQLite, logs, media,
cache and backups.

## Launch modes

- `run_companion.bat` → normal user launch; after dependency check it hands off
  to `pythonw.exe` / `run_companion.pyw`, so no console remains open.
- `run_companion_debug.bat` → explicit diagnostic launch with console retained.
- First-time PySide6 installation is allowed to use the console.

## Architecture boundary

- SQLite connection remains on the Companion runtime thread.
- Qt receives plain snapshots/events.
- GUI widgets never write archive rows.
- Manual refresh remains a thread-safe request.
- Closing the app requests a clean watcher/runtime stop.
