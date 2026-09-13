# DDS Companion — Release Status Registry (snapshot at 0.3.0 build)

Project: **DDS — Discord Data Snatcher**  
Authors: **Mr_Dexter_Morgan, Masya**

| Version | Status | Scope / result |
|---|---|---|
| `0.1.0` | **VERIFIED / STABLE FOUNDATION** | Normalized accumulating SQLite importer, deduplication, thread relations, media metadata, failure isolation. |
| `0.2.0` | **VERIFIED** | Continuous Watcher Layer; live Windows test detected and imported new thread captures without restart, zero failures. |
| `0.3.0` | **BUILT / LOCAL TESTING** | Activity & Health Core: durable Activity API, subsystem health/heartbeat, richer Stats/session deltas, additive schema v2 migration. 18/18 tests + process integration + real 0.2->0.3 DB migration pass. |

Current live-verified release at build time: **0.2.0**  
Current candidate: **0.3.0**

Historical published release folders are immutable. 0.3.0 becomes VERIFIED only after a real Windows test against the existing DDS archive.
