# DDS Companion 0.4.5 — Startup Foreground Candidate

Project: **DDS — Discord Data Snatcher**  
Authors: **Mr_Dexter_Morgan, Masya**

> Are you sure your data is secure?

Status: **BUILT / LOCAL TESTING**

0.4.5 is a deliberately small UX patch on top of the live-tested 0.4.4 Health
candidate. It fixes the Windows launch case where Explorer can remain above the
Companion window after `run_companion.bat` starts the GUI.

## What changed

- On the first real window show, Companion schedules a **single** foreground
  request after the native Qt handle exists.
- Qt `raise_()` / `activateWindow()` is used first.
- On Windows only, a best-effort Win32 fallback briefly places the window at the
  top of Z-order and immediately removes TOPMOST before requesting foreground.
- The path is guarded by `_startup_foreground_attempted`, so restoring,
  unminimizing, Health refreshes, watcher events and background polling cannot
  steal focus later.
- Any foreground API failure is swallowed; presentation polish must never stop
  the archive/runtime pipeline.
- If Discord is definitely `NOT RUNNING`, a still-fresh/stale plugin heartbeat can no
  longer leave the Plugin card falsely green. The effective Plugin state becomes
  `NOT RUNNING` while the last heartbeat/version metadata stays visible.

## Retained from 0.4.4

- User-facing **LIMITED** Health semantics.
- DDS Plugin health card and `plugin-heartbeat-v1` consumer.
- Plugin 0.5.3 RUNNING / STOPPED / recovery handling.
- Discord process state in overall Health.
- Watcher **WAITING** while `DDS_Data` is unavailable.
- Importer **Last import** wording.
- Health reason tooltips and deduplicated Activity transitions.
- Existing archive/import/dedup behavior and local-first storage.

## What did not change

- No archive schema migration.
- No Media Backfill or cache policy yet.
- No updater backend yet.
- No AI export or Google Drive synchronization.

## Validation

Automated validation: **40/40 PASS**. The fresh-heartbeat/Discord-off contradiction now has a regression test.

Automated validation is run before packaging. Native Windows validation must
confirm two things: Explorer no longer covers the app at launch, and Companion
does not steal focus again after the startup moment.

Follow `LIVE_TEST_CHECKLIST_0.4.5.txt` one scenario at a time.
