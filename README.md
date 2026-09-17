# DDS Companion 0.4.6 — UI / Storage Foundation

Project: **DDS — Discord Data Snatcher**  
Authors: **Mr_Dexter_Morgan, Masya**

Status: **VERIFIED / LIVE TESTED / CURRENT RECOMMENDED**

0.4.6 turns the already-working 0.4.5 desktop Companion into a cleaner product surface and establishes real persistent storage/cache controls before Media Backfill.

## What changed

- Dashboard no longer duplicates subsystem Health.
- `Open DDS_Data` and `Open logs` are removed from Dashboard.
- Top global Health pill is now a shortcut to the Health page from every other page.
- Dashboard gets a storage ring + percentage/size breakdown.
- Storage accounting tracks SQLite/WAL/SHM, DDS JSON, media cache, logs and real Other storage.
- Settings is split into **General / Data & Storage / Archive / Diagnostics**.
- Media-cache policy is persistent and active: total cache limit, maximum single media file size, retention age and optional confirmation before manual clear.
- Settings are written atomically to `%LOCALAPPDATA%\DDS_Companion\config\settings.json` and corrupt JSON falls back safely to defaults.
- Manual media-cache cleanup deletes only binary cache files; SQLite, DDS JSON, messages and attachment metadata are preserved.
- Diagnostics includes System report, Copy report and SQLite `PRAGMA quick_check`.
- Existing one-shot startup foreground behavior and truthful Health semantics remain intact.
- Source/dev first-run bootstrap automatically installs PySide6 when absent, without a Y/N prompt.

## Validation

Automated validation: **52/52 PASS**.

Native Windows live validation: **PASS**.

Confirmed live:
- 0.4.6 launches and renders correctly on Windows;
- Dashboard storage ring and breakdown render correctly;
- Data & Storage settings persist across restart;
- global RUNNING Health shortcut opens Health;
- Discord and Plugin off/on state changes remain truthful and recover automatically;
- normal shutdown produces no traceback;
- System report shows all core subsystems RUNNING with zero unresolved failures;
- SQLite Database quick check returns `PASS — ok`;
- media-cache test file is detected, enables `Clear media cache`, prompts for confirmation, and is removed without touching archive data;
- archive/message count remains intact after media-cache cleanup.

Bootstrap note: the no-prompt PySide6 bootstrap revision is covered by automated regression. A clean-environment Windows rerun after the r2 change was not separately repeated because PySide6 was already installed during the first live session. This does not affect the validated Companion runtime/UI gate; final 1.0 packaging is still expected to bundle runtime dependencies.

## Next stage

**Media Backfill / media backend** after the now-validated cache/settings foundation.
