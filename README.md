# DDS Companion 0.4.2 — Settings IA Patch

Project: **DDS — Discord Data Snatcher**  
Authors: **Mr_Dexter_Morgan, Masya**

> Are you sure your data is secure?

Status: **BUILT / LOCAL TESTING**

0.4.2 is a focused patch over the live-tested 0.4.1 GUI. It reorganizes the
Settings page so important user/runtime settings have the primary space and
filesystem paths are kept in a separate secondary tab.

## What changed

Settings now opens on **Основные**. The existing watcher policy is shown there,
and this tab is reserved for future user-facing options as they become safely
persistent and validated.

All service locations moved to **Paths & Storage**:

- Library / Companion data
- DDS_Data plugin export
- SQLite database
- Logs
- Media cache
- Cache
- Backups

The path page keeps its own vertical scrolling and the existing Copy/Open
actions.

## What did not change

The archive/import/watcher core is unchanged. Dashboard, Library, Activity,
Health, responsive layout profiles and the normal no-console launcher remain as
in 0.4.1.

## Validation

- Python compileall: **PASS**
- Automated suite: **28/28 PASS**
- Regression suite from 0.4.1: **PASS**
- Settings two-tab source contract: **PASS**

Actual Qt rendering of the new Settings tabs still requires the Windows live
check because PySide6 is not installed in the build container.

See `CHANGELOG.txt`, `VALIDATION.txt`, `UI_CONTRACT.md` and
`LIVE_TEST_CHECKLIST_0.4.2.txt`.
