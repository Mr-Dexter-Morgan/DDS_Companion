# DDS Companion — Release Status Registry

Project: **DDS — Discord Data Snatcher**  
Authors: **Mr_Dexter_Morgan, Masya**

| Version | Status | Scope / result |
|---|---|---|
| `0.1.0` | **VERIFIED / STABLE FOUNDATION** | Foundation importer passed live Windows testing against real `%APPDATA%\BetterDiscord\DDS_Data`: 3 captures recognized, 25-message accumulating SQLite archive, guild/channel/thread relations and media metadata confirmed, zero failures. |
| `0.2.0` | **BUILT / LOCAL TESTING** | Continuous Watcher Layer: new/changed capture detection, settle window, transient retry, failure isolation/recovery, archive-preserving delete behavior, heartbeat/state, clean Ctrl+C shutdown. 8/8 unit tests + integration smoke test pass. |

`0.2.0` requires one live Windows watcher test with DDS 0.5.2 before it is marked VERIFIED.

Historical release folders are immutable. Runtime defects are fixed in a new patch/release rather than rewriting an already-published version.
