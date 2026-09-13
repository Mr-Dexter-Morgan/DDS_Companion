# DDS Companion 0.4.1 — Responsive GUI Polish

Project: **DDS — Discord Data Snatcher**  
Authors: **Mr_Dexter_Morgan, Masya**

> Are you sure your data is secure?

Status: **BUILT / LOCAL TESTING**

0.4.1 is a focused polish release over the live-tested 0.4.0 desktop interface.
The archive/import/watcher core is unchanged; this patch fixes the real Windows
layout and launcher issues found during the first GUI run.

## What changed

- Dashboard is now scroll-safe at laptop-height resolutions.
- Compact / Standard / Large layout profiles use screen geometry, DPI and DPR.
- 1366x768-class screens use a 2x2 metric grid and vertically stacked lower cards.
- Sidebar idle / hover / selected states are visually distinct.
- Duplicate **Open library** actions were removed from Topbar and Dashboard.
  Library page is the single **Open library folder** location.
- **Refresh** is a compact secondary button.
- Normal launch hands off to `pythonw.exe` / `run_companion.pyw` so a console is
  not kept open; `run_companion_debug.bat` intentionally keeps a console.

## Normal launch

Double-click:

```text
run_companion.bat
```

If PySide6 is already installed, the batch launcher performs a quick dependency
check and starts the GUI through `pythonw.exe`.  If PySide6 is missing, it keeps
the console available to offer first-time installation.

For diagnostics:

```text
run_companion_debug.bat
```

## Architecture boundary

```text
Discord Desktop
      ↓
DDS BetterDiscord plugin
      ↓
DDS_Data / capture.json
      ↓
Companion watcher + importer + SQLite
      ↓
Activity / Health / Stats / Library services
      ↓ plain dictionaries / observer events
PySide6 presentation layer
```

Qt does not own archive SQL.  The SQLite connection stays on one background
runtime thread; the GUI receives serializable snapshots through signals.

## Default paths

DDS plugin export:

```text
%APPDATA%\BetterDiscord\DDS_Data
```

Companion runtime data:

```text
%LOCALAPPDATA%\DDS_Companion
```

SQLite:

```text
%LOCALAPPDATA%\DDS_Companion\database\dds.sqlite3
```

## Responsive contract

The window evaluates usable screen geometry, `logicalDotsPerInch()`,
`devicePixelRatio()` and current window width.  It changes card flow/margins
rather than uniformly scaling every widget.

The Dashboard remains scrollable, so constrained displays favor readability and
non-overlap instead of trying to force every panel above the fold.

## Validation

- Python compileall: **PASS**
- Automated suite: **27/27 PASS**
- Previous 21 tests: **PASS**
- 1366x768 / 1080p / dense-4K layout-profile tests: **PASS**
- Launcher/action/scroll-safety source contracts: **PASS**

Actual 0.4.1 Qt rendering still requires the Windows live checklist because the
build container does not have PySide6 installed.  Do not promote this candidate
to VERIFIED until that check is complete.

See `VALIDATION.txt`, `UI_CONTRACT.md`, `CHANGELOG.txt` and
`LIVE_TEST_CHECKLIST_0.4.1.txt`.
