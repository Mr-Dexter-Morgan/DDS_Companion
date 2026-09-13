# DDS Companion 0.2.0 — Watcher Layer

**Authors:** Mr_Dexter_Morgan, Masya  
**Companion status:** BUILT / LOCAL TESTING  
**Upstream DDS Plugin:** 0.5.2 — VERIFIED / STABLE MILESTONE

DDS Companion 0.2.0 turns the 0.1.0 foundation importer into a continuously running local companion.

## What it does

On startup Companion:

1. locates `%APPDATA%\BetterDiscord\DDS_Data`;
2. opens/reuses `%LOCALAPPDATA%\DDS_Companion\database\dds.sqlite3`;
3. performs one full synchronization of all existing `capture.json` files;
4. starts watching `DDS_Data` continuously;
5. waits for changed files to become stable before reading them;
6. imports new/changed captures into the accumulating SQLite archive;
7. keeps running when one capture is malformed or temporarily unreadable;
8. preserves archived SQLite data even if a source `capture.json` later disappears.

No media files are downloaded. Attachments and embeds remain metadata-only.

## Run on Windows

Double-click:

```text
run_companion.bat
```

The default mode is now persistent watcher mode. Leave the window open while Discord + DDS are running.

Stop cleanly with:

```text
Ctrl+C
```

For the old one-shot behavior:

```text
run_once.bat
```

or:

```text
python -m dds_companion.app --once
```

## Expected startup

A healthy real-machine startup should look approximately like:

```text
DDS Companion v0.2.0  [RUNNING]
DDS_Data : C:\Users\...\AppData\Roaming\BetterDiscord\DDS_Data
Database : C:\Users\...\AppData\Local\DDS_Companion\database\dds.sqlite3
Watcher  : ACTIVE  poll=750 ms, settle=500 ms

Import   : seen=..., imported=..., unchanged=..., failed=0
Messages : +... new, ... existing refreshed; archive total=...
Context  : guilds=..., channels=..., threads=...
Media    : attachments=..., embeds=... (metadata only)
Storage  : ...

Watching DDS_Data. Press Ctrl+C to stop cleanly.
```

When DDS changes a capture you should then see something like:

```text
[19:42:10] WATCH   changed: guilds/.../capture.json (settling)
[19:42:11] IMPORT  guilds/.../capture.json -> +1 new, 25 existing refreshed, attachments=..., embeds=...
```

`existing refreshed` means an already-known message was encountered in the newer capture and upserted. It does **not** yet mean DDS Companion has classified it as a semantic Discord edit; true message-version history belongs to a later milestone.

## Reliability choices

### No extra watcher dependency

0.2.0 deliberately uses a conservative standard-library polling watcher instead of requiring `watchdog` or a platform-specific native backend. This keeps deployment simple and removes another failure surface.

### Settle window

DDS 0.5.2 normally publishes JSON safely, but its BetterDiscord filesystem compatibility layer can fall back to direct writes. Companion therefore waits until a changed file remains stable for a short period before parsing it.

Defaults:

```text
poll:   750 ms
settle: 500 ms
```

They can be overridden:

```text
python -m dds_companion.app --poll-ms 500 --settle-ms 350
```

### Failure isolation and recovery

A bad capture is recorded in `failed_jobs` and the watcher continues. If that same file is corrected and later imports successfully, its unresolved failure entries are marked resolved automatically.

### Archive is authoritative

The DDS plugin exposes current snapshots. SQLite is the accumulating archive. Removing a capture file from `DDS_Data` does not erase already imported history.

## Data paths

Default input:

```text
%APPDATA%\BetterDiscord\DDS_Data
```

Default Companion data:

```text
%LOCALAPPDATA%\DDS_Companion\
├── database\dds.sqlite3
├── logs\
├── cache\
├── media\
└── backups\
```

## CLI

```text
python -m dds_companion.app
python -m dds_companion.app --once
python -m dds_companion.app --json
python -m dds_companion.app --dds-data "D:\path\DDS_Data"
python -m dds_companion.app --app-data "D:\path\DDS_Companion"
python -m dds_companion.app --poll-ms 750 --settle-ms 500
```

In watch mode `--json` emits an initial JSON object followed by JSON Lines watcher events.

## Validation performed before publication

```text
compileall                         PASS
0.1.0 importer regression tests   4/4 PASS
0.2.0 watcher tests               4/4 PASS
watcher integration smoke test    PASS
clean SIGINT shutdown             PASS
```

## Live test for VERIFIED status

1. Start `run_companion.bat`.
2. Confirm `Watcher : ACTIVE`.
3. With DDS 0.5.2 enabled, switch to a Discord channel/thread or load one more message so its `capture.json` changes.
4. Without restarting Companion, confirm a `WATCH changed` line followed by `IMPORT`.
5. Press `Ctrl+C` and confirm a clean watcher summary.

That single real Windows test is the gate for marking 0.2.0 VERIFIED.
