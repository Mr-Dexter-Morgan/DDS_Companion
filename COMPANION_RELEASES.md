# DDS Companion — Release Status Registry

**Synchronized:** 2026-09-18

| Version | Status | Result |
|---|---|---|
| `0.4.6` | **VERIFIED / LIVE TESTED / ROLLBACK BASELINE** | Dashboard/Storage/Settings foundation, persistence, cache safety and diagnostics passed live on Windows. |
| `0.5.0` | **VERIFIED / LIVE TESTED / CURRENT RECOMMENDED** | Media Backfill Core; real caching, manual-clear recovery, live growth and restart continuity/dedup accepted. |
| `0.5.1` | **LIVE FINDING / SUPERSEDED BEFORE PROMOTION** | UI/Settings polish rendered successfully; live pass exposed one permanent media-failure recovery/UX gap. |
| `0.5.2` | **CANDIDATE / 81/81 AUTOMATED PASS / WINDOWS LIVE PENDING** | Media Attention Recovery: Retry / Ignore / Details, durable ignored state, truthful labels and stable size-mismatch classification. |

## Current recommended Companion release

**`0.5.0` — VERIFIED / LIVE TESTED / CURRENT RECOMMENDED.**

## Current candidate

**`0.5.2` — CANDIDATE / 81/81 AUTOMATED PASS / WINDOWS LIVE PENDING.**

0.5.2 carries forward the 0.5.1 UI/Settings polish and closes the live media-attention finding. Promotion requires only the bounded 0.5.2 Windows live gate.
