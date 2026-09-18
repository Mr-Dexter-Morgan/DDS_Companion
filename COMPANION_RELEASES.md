# DDS Companion — Release Status Registry

**Synchronized:** 2026-09-18

| Version | Status | Result |
|---|---|---|
| `0.4.6` | **VERIFIED / LIVE TESTED / ROLLBACK BASELINE** | Dashboard/Storage/Settings foundation, persistence, cache safety and diagnostics passed live on Windows. |
| `0.5.0` | **VERIFIED / LIVE TESTED / CURRENT RECOMMENDED** | Media Backfill Core; real caching, manual-clear recovery, live growth and restart continuity/dedup accepted. |
| `0.5.1` | **CANDIDATE / AUTOMATED PASS / WINDOWS LIVE PENDING** | UI / Settings Polish; localized shell, Главная refresh cleanup, settings reorganization with unchanged backend keys. |

## Current recommended Companion release

**`0.5.0` — VERIFIED / LIVE TESTED / CURRENT RECOMMENDED.**

## Current candidate

**`0.5.1` — CANDIDATE / 74/74 AUTOMATED PASS / WINDOWS LIVE PENDING.**

Promotion requires only the bounded 0.5.1 Windows UI/live gate; 0.5.0 media validation is not repeated unless a relevant regression appears.
