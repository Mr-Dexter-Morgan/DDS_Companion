# DDS Companion 0.8.8

DDS Companion 0.8.8 is the user-accepted stability, media-lifecycle, and Media Cache visualization release.

## Highlights

- fixes false Discord **NOT RUNNING** detection on localized Windows builds by making the process probe binary-safe;
- keeps the Windows build chain pinned to Python 3.11 and preserves reproducible release packaging;
- adds manual **Скачать снова / Re-cache** intent with persisted schema-v6 state and branch bulk re-cache;
- hardens concurrent SQLite startup/migration handling against transient `database is locked` races;
- replaces the old capsule-like Media Cache display with a square **16×12 Tetris-style** field and a jagged low-occupancy pile;
- keeps limited-mode fill tied to the real configured cache limit;
- adds an explicit adaptive visual scale for unlimited cache (1 → 2 → 4 → 8 GiB …) without imposing a storage limit.

## Validation

- user live acceptance: PASS on 2026-10-23;
- Windows regression suite: **239/239 PASS**;
- SQLite startup race stress: **5/5 PASS**;
- two clean native builds: reproducible **5/5 key artifacts**;
- native 139 MiB / 1 GiB Media Cache visual smoke: PASS;
- native build runtime: Python 3.11.

## Compatibility

Recommended companion plugin: DDS Plugin 0.5.4 or newer.
