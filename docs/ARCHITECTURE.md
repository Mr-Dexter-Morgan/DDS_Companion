# DDS Companion Architecture

## Role in DDS

DDS is one product split into independently versioned components:

| Component | Responsibility |
|---|---|
| **DDS Plugin** | Observe the running Discord client and write local structured captures |
| **DDS Companion** | Durable archive, media lifecycle/cache, Library, ZIP export and desktop UX |
| **DDS Installer** | Windows installation/repair orchestration |

Primary data path:

```text
Discord Desktop → BetterDiscord → DDS Plugin → DDS_Data → DDS Companion → SQLite archive
```

Installer is the setup/repair control plane beside that data path.

## Durable archive boundary

DDS Companion owns the long-term normalized archive under:

```text
%LOCALAPPDATA%\DDS_Companion
```

The SQLite archive is the durable source of truth.

Derived layers include:

- media cache;
- exported ZIP packages;
- update staging/packages;
- rebuildable UI summaries.

A failure in a derived/network layer must not make the existing archive unreadable.

## Plugin import boundary

DDS Plugin writes capture data under:

```text
%APPDATA%\BetterDiscord\DDS_Data
```

Companion imports that hand-off data and deduplicates/normalizes it into SQLite.

Plugin contracts currently consumed by Companion include:

- capture schema v2;
- `plugin-heartbeat-v1`;
- `source-evidence-v1`.

## Media lifecycle

Companion owns media download/cache state.

Relevant states include known/cached/evicted/unresolved/terminal SOURCE_GONE outcomes.

Manual Re-cache in 0.8.8 preserves explicit user intent across an expired Discord URL until fresh rediscovery. SOURCE_GONE remains terminal only when positive imported deletion evidence exists.

## Health boundary

Discord process state, Plugin heartbeat, archive/runtime health and media worker state are separate signals.

A missing Discord/Plugin process can degrade overall Health without implying archive corruption.

## Update boundary

Companion uses a stable launcher + external updater + versioned application directories.

Update packages are verified before apply. Startup acknowledgement/rollback protects the previous working version.

User data under `%LOCALAPPDATA%\DDS_Companion` is outside application-version replacement.

## Installer boundary

DDS Installer may place/repair Companion program files and shortcuts, but must preserve the Companion data root by default.

Installer does not own SQLite migrations or archive semantics.

## Project-wide rules

- SQLite/local archive remains readable without network access.
- Capture/import/migrations are idempotent where practical.
- Schema migrations must be safe on repeated and concurrent startup.
- Runtime fixes require regression evidence.
- GUI/Windows/Discord integration changes receive native/live validation before stable release.
- Plugin, Companion and Installer versions advance independently.
