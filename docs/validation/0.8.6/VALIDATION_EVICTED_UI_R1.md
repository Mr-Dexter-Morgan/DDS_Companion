# DDS Companion 0.8.6 — EVICTED UI observability patch (ui-r1)

Date: 2026-10-22

## Result

**TARGET PATCH: PASS**

This result applies to the EVICTED UI/observability patch only.
The broader 0.8.6 SOURCE_GONE release state remains separate and is not promoted by this patch.

## Baseline

- Source: `DDS_Companion_0.8.6-source.zip`
- Baseline SHA-256: `1ad30c3c8c340161fbed1f557819e1e80fa2e28c0977b7360d4ba5a41067308f`
- Internal version remains: `0.8.6`
- SOURCE_GONE lifecycle semantics unchanged.

## User-visible change

The Media Lifecycle page now has a separate **«Кэш очищен»** metric for `EVICTED` media.

For the real reproduced state:

- total: 149
- known: 143
- cached: 30
- evicted / cache cleared: 113
- awaiting rediscovery: 6
- source gone: 0

the UI now explicitly shows where the known-but-not-cached media went.

Additional observability:

- media runtime summary includes `кэш очищен: N`;
- Library branch summaries and tooltips include cache-cleared counts;
- EVICTED attachment details distinguish:
  - `evicted_policy` → «кэш очищен по настройкам хранения»;
  - `evicted_manual_clear` → «кэш очищен вручную».

## Lifecycle safety

No planner or retention behavior was changed.

Verified invariant:

- EVICTED remains EVICTED;
- EVICTED does not enter QUEUED automatically;
- known-count semantics remain unchanged;
- UNRESOLVED and SOURCE_GONE remain separate states.

## Source changes

Modified:

- `CHANGELOG_0.8.6.md`
- `README.md`
- `dds_companion/gui/pages.py`
- `dds_companion/services/library_service.py`
- `dds_companion/services/media_runtime.py`

Added:

- `dds_companion/tests/test_evicted_ui_086.py`

## Validation

### Target tests

4/4 PASS on native Windows with PySide6 6.12.0.

### Full regression

**209/209 PASS** on Windows 10, Python 3.11.0, PySide6 6.12.0.

Includes:

- existing SOURCE_GONE 0.8.6 tests;
- media backfill lifecycle;
- updater and rollback;
- single-instance;
- Library/UI contracts;
- new EVICTED observability tests.

### Windows build

`build_windows.bat` — PASS.

Generated:

- DDS.exe — ProductVersion 0.8.6
- DDSApp.exe — ProductVersion 0.8.6
- DDSUpdater.exe — ProductVersion 0.8.6
- full Windows ZIP — PASS
- update ZIP / manifest — build PASS (not published as renamed standalone artifacts)

Executable SHA-256:

- DDS.exe: `3a14d69a0d9ce75771ecdbfeb0aab186a7cf69f822d460e30f26bc0743479efb`
- DDSApp.exe: `3ac5b658957930492adaec1dd469ae750c7cfaa6a5c4668aa3b58c18548ab2a1`
- DDSUpdater.exe: `1143337743c7056fb3eac88aadf5e5868c24961b1f0cac95bbf0c81bef970b7f`

## Candidate artifacts

- `DDS_Companion_0.8.6-ui-r1-source.zip`
  - SHA-256: `86164949910d33907ca2edbe43c38181474e04dd39d69e533bb4dd5ac92a80e0`
- `DDS-0.8.6-windows-x64-ui-r1.zip`
  - SHA-256: `76d2222554bde540e7489a9aaa9eb294f46833447ae44373233e7483998a95a0`

## Deployment

The currently installed DDS 0.8.6 on MAINFRAME was **not replaced** during this work.
The candidate is ready for an explicit live UI test.
