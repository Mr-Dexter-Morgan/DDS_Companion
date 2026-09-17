# DDS Companion — Release Status Registry

**Synchronized:** 2026-09-17

| Version | Status | Result |
|---|---|---|
| `0.1.0` | **VERIFIED / STABLE FOUNDATION** | Accumulating SQLite foundation live-tested. |
| `0.2.0` | **VERIFIED** | Continuous watcher live-tested. |
| `0.3.0` | **VERIFIED / SUPERSEDED** | Activity / Health core live-tested. |
| `0.4.0` | **LIVE-TESTED / SUPERSEDED** | First Qt GUI; superseded after 1366x768 findings. |
| `0.4.1` | **LIVE-TESTED / SUPERSEDED** | Responsive GUI polish rendered successfully on Windows. |
| `0.4.2` | **LIVE UI REVIEW / SUPERSEDED** | Settings IA and primary pages visually reviewed. |
| `0.4.3` | **LIVE-TESTED / SUPERSEDED** | Discord process detection and DDS_Data loss/recovery worked live. |
| `0.4.4` | **LIVE-TESTED / SUPERSEDED** | Health truthfulness and Plugin 0.5.3 heartbeat integration validated live. |
| `0.4.5` | **VERIFIED / LIVE TESTED / SUPERSEDED** | Startup/no-focus-steal and final Health regression passed. |
| `0.4.6` | **VERIFIED / LIVE TESTED / CURRENT RECOMMENDED** | Dashboard/Storage/Settings foundation, persistence, cache safety and diagnostics passed live on Windows. |
| `0.5.0` | **CANDIDATE r2 / AUTOMATED PASS / LIVE PENDING** | Media Backfill Core. r1 passed real 6/6 caching + restart dedup; r2 fixes manual-clear recovery, toggle observability and storage color correlation. |

## Current recommended Companion release

**`0.4.6` — VERIFIED / LIVE TESTED / CURRENT RECOMMENDED.**

0.4.6 live validation confirmed Dashboard/Storage rendering, settings persistence, Health shortcut, Discord/Plugin recovery, clean shutdown, selective media-cache clear, System report and SQLite `PASS — ok`. Final automated baseline: 52/52 PASS.

## Current candidate

**`0.5.0` — CANDIDATE r2 / AUTOMATED PASS / WINDOWS LIVE PENDING.**

Automated gate: **70/70 PASS repeated three consecutive runs**, plus compileall and CLI version PASS. Windows r1 live results already confirmed migration, 67-message preservation, real 6/6 caching and restart dedup. r1 then exposed a manual-clear requeue gap; r2 fixes it and must pass the remaining live checks before promotion. Until then 0.4.6 remains rollback/current baseline.
