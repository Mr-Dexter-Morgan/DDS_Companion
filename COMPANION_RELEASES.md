# DDS Companion — Release Status Registry (0.4.5 candidate snapshot)

| Version | Status | Result |
|---|---|---|
| `0.1.0` | **VERIFIED / STABLE FOUNDATION** | Accumulating SQLite foundation live-tested. |
| `0.2.0` | **VERIFIED** | Continuous watcher live-tested. |
| `0.3.0` | **VERIFIED** | Activity / Health core live-tested. |
| `0.4.0` | **LIVE-TESTED / SUPERSEDED** | First Qt GUI; superseded after 1366x768 findings. |
| `0.4.1` | **LIVE-TESTED / SUPERSEDED** | Responsive GUI polish rendered successfully on Windows. |
| `0.4.2` | **LIVE UI REVIEW / SUPERSEDED** | Settings IA and primary pages visually reviewed. |
| `0.4.3` | **LIVE-TESTED / SUPERSEDED** | Discord process detection and DDS_Data loss/recovery worked live. |
| `0.4.4` | **LIVE-TESTED CANDIDATE / SUPERSEDED BY 0.4.5 CANDIDATE** | Health truthfulness and Plugin 0.5.3 heartbeat integration validated live. |
| `0.4.5` | **BUILT / LOCAL TESTING** | One-shot startup foreground fix; automated and Windows live validation required. |

## Current recommended Companion release

**`0.3.0`** remains the last fully promoted recommendation.

## Current candidate

**`0.4.5`** — small Windows startup UX patch on top of 0.4.4.

Required before promotion decision:
- Explorer launch brings Companion to foreground once;
- no later focus stealing;
- short Health/plugin/source regression remains clean.

## Current plugin dependency

**DDS Plugin `0.5.3` is VERIFIED / LIVE TESTED / RELEASED and is the recommended
plugin for heartbeat-aware Health.**
