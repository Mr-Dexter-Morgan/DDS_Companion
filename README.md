# DDS Companion 0.4.0 — Desktop Dashboard

Project: **DDS — Discord Data Snatcher**  
Authors: **Mr_Dexter_Morgan, Masya**

> Are you sure your data is secure?

Status: **BUILT / LOCAL TESTING**

0.4.0 gives the verified Companion core its first real desktop interface. The archive pipeline remains the same local pipeline proven in 0.1.0–0.3.0; the GUI consumes plain snapshots/events from that core instead of owning database logic itself.

## What this release adds

- PySide6 dark desktop shell.
- Navigation: **Dashboard / Library / Activity / Health / Settings**.
- Live Dashboard backed by the real Stats/Health/Activity services.
- Total known storage always visible.
- Separate known vs cached media counts.
- Session growth: messages, imports, activity events and storage delta.
- Human-readable current activity.
- Per-subsystem health for Database, DDS_Data, Importer and Watcher.
- Library tree: **Server → Channel → Thread** with message counts.
- Activity table backed by persisted `activity_events`.
- Paths & Storage page with one-click folder access.
- Quick actions: **Open library folder / Open DDS_Data / Open logs**.
- SQLite database, cache, media and backups can be opened directly from Settings.
- Runtime-created DDS app icon; no external icon path can go missing.
- Existing CLI remains available through `run_cli.bat`.
- Existing one-shot importer remains available through `run_once.bat`.

## Architecture boundary

The Qt UI does **not** execute archive SQL directly.

```text
Discord Desktop
      ↓
DDS 0.5.2 plugin
      ↓
DDS_Data / capture.json
      ↓
Companion watcher + importer + SQLite
      ↓
Activity / Health / Stats / Library services
      ↓ plain dictionaries / observer events
PySide6 presentation layer
```

The GUI runtime keeps the SQLite connection on one background runtime thread. Qt receives serializable snapshots through thread-safe signals. Presentation callbacks are observers and are isolated from the watcher/import pipeline.

Closing the application asks the watcher to stop cleanly. A normal UI close does not delete or mirror-trim archive data.

## Installation / first launch

Requirements:

- Windows 10/11 for the live target.
- Python 3.11+.
- PySide6 for the GUI.

Run:

```text
run_companion.bat
```

If PySide6 is missing, the launcher offers to install it using:

```text
requirements-gui.txt
```

You can also install it manually with:

```text
install_gui_dependencies.bat
```

The headless watcher is still available:

```text
run_cli.bat
```

## Default paths

DDS plugin export:

```text
%APPDATA%\BetterDiscord\DDS_Data
```

Companion data:

```text
%LOCALAPPDATA%\DDS_Companion
```

SQLite:

```text
%LOCALAPPDATA%\DDS_Companion\database\dds.sqlite3
```

## Dashboard contract

The first screen must answer three questions immediately:

1. **Is Companion healthy?**
2. **What is it doing now?**
3. **How much has it archived?**

The Dashboard therefore shows overall state, four subsystem states, total storage, message/context/media counts, session growth, storage breakdown and latest activity without requiring navigation.

## Library contract

0.4.0 intentionally provides archive structure browsing, not message full-text search. The tree is:

```text
Server
└── Channel
    └── Thread
```

Message search/version history remains a later architectural stage and is not faked in this release.

## Reliability rules preserved

- One malformed capture must not terminate the watcher.
- One bad UI/activity observer must not terminate the watcher.
- Source capture deletion must not delete accumulated archive rows.
- Existing 0.1/0.2/0.3 SQLite archives upgrade in place.
- Drive/network availability is not required for local capture/import.
- UI convenience actions only open local paths; they do not alter archive content.

## Local validation

- Python compile: **PASS**
- 0.1/0.2/0.3 regression suite: **PASS**
- New Library hierarchy test: **PASS**
- New GUI runtime startup/clean-stop integration test: **PASS**
- New live capture-change → Activity integration test: **PASS**
- Total automated tests: **21/21 PASS**

The build environment used for this release does not include PySide6, so the actual Qt window render is intentionally marked **awaiting live Windows validation**. Backend/UI-boundary behavior is tested without Qt; the visual render and native folder buttons must be verified on the user's Windows machine before the release becomes VERIFIED.

See `VALIDATION.txt`, `UI_CONTRACT.md`, and `LIVE_TEST_CHECKLIST_0.4.0.txt`.
