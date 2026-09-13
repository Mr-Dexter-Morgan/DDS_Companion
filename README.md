# DDS Companion 0.1.0 — Foundation Importer

**Authors:** Mr_Dexter_Morgan, Masya  
**Project:** DDS — Discord Data Snatcher  
**Status:** BUILT / LOCAL TESTING

This is the first DDS Companion release. It consumes the stable `DDS_Data` filesystem contract produced by DDS Plugin `0.5.2` and builds a durable normalized SQLite archive.

## Scope of 0.1.0

This release intentionally does one architectural job: **turn current DDS JSON captures into an accumulating SQLite archive safely**.

Implemented:
- automatic default discovery of `DDS_Data`;
- explicit `--dds-data` override;
- stable Companion runtime data root;
- SQLite bootstrap + schema migration v1;
- WAL, foreign keys, busy timeout, transactional imports;
- recursive discovery of channel and thread `capture.json` files;
- Capture Schema v2 validation;
- guild / parent channel / thread relationship preservation;
- account and author normalization;
- message upsert by immutable Discord message ID;
- attachment and embed metadata registration;
- message-reference registration;
- import fingerprinting by `capture_path + SHA-256`;
- unchanged snapshot suppression;
- malformed capture isolation into `failed_jobs`;
- archive statistics and SQLite health summary;
- **no media download**;
- **no Discord token access**;
- **no hidden history fetching**;
- **no Google Drive dependency**.

## Why the archive accumulates

DDS Plugin keeps one current `capture.json` per channel/thread and updates it as Discord loads different message windows. Companion does **not** mirror-delete older rows when a newer snapshot no longer contains them. Once a message has been observed and imported, it stays in SQLite. Later snapshots update the same Discord message ID if its content/metadata changed.

## Default paths

DDS input on Windows:

```text
%APPDATA%\BetterDiscord\DDS_Data
```

Companion data on Windows:

```text
%LOCALAPPDATA%\DDS_Companion\
├── database\dds.sqlite3
├── logs\
├── cache\
├── media\
└── backups\
```

`media`, `cache`, and `backups` are reserved for later releases; 0.1.0 does not download media.

## Run

From the release folder:

```bat
python -m dds_companion.app
```

Explicit paths:

```bat
python -m dds_companion.app --dds-data "C:\Users\YOU\AppData\Roaming\BetterDiscord\DDS_Data" --app-data "D:\DDS_Companion_Data"
```

Machine-readable output:

```bat
python -m dds_companion.app --json
```

## Test

```bat
python -m unittest discover -s dds_companion\tests -v
```

## Not in this release

The live filesystem watcher is deliberately deferred to the next Companion release. `0.1.0` proves parser → normalizer → SQLite storage first, matching the DDS rule: test one architectural layer before adding the next one.
