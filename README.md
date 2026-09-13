# DDS Companion 0.3.0 — Activity & Health Core

**Authors:** Mr_Dexter_Morgan, Masya  
**Companion status:** BUILT / LOCAL TESTING  
**Previous stable Companion:** 0.2.0 — VERIFIED  
**Upstream DDS Plugin:** 0.5.2 — VERIFIED / STABLE MILESTONE

DDS Companion 0.3.0 adds the observability core that the future GUI will consume. The archive/import/watcher pipeline from 0.1.0 and 0.2.0 remains intact; 0.3.0 adds durable human-readable Activity, subsystem Health, richer Stats and session deltas.

The important architectural rule is: **the future UI must display core state, not become the core.** A broken printer or GUI listener must not terminate DDS importing.

## What changed

### ActivityService

Activity is now a first-class internal API and SQLite entity, not only console text.

It provides:

- durable `activity_events` records;
- in-memory subscriptions for CLI today and PySide6 later;
- human summaries such as `+9 messages imported, 0 existing refreshed`;
- source capture path plus guild/channel/thread context when known;
- message/media counters per import event;
- severity + subsystem + event type;
- subscriber failure isolation: one broken presentation listener cannot stop archiving.

Transient filesystem chatter (`created`, `changed`, `unchanged`) is intentionally not persisted as Activity spam. Successful imports, failed imports, source removals, session lifecycle, and other meaningful events are persisted.

### HealthService

Health is persisted per subsystem in `subsystem_health`.

Current subsystem model:

- `database`
- `dds_data`
- `importer`
- `watcher`

Supported states:

```text
STARTING
RUNNING
DEGRADED
ERROR
STOPPED
UNKNOWN
```

Overall Companion state remains:

```text
RUNNING / DEGRADED / ERROR
```

A watcher heartbeat is persisted. If a prior process claimed `RUNNING` but the heartbeat becomes stale, Health can classify it as `DEGRADED` instead of trusting stale state forever.

### StatsService

Stats now has a stable snapshot API with a process-session baseline.

It exposes:

- total messages;
- guild/channel/thread/user counts;
- attachments / embeds;
- capture imports;
- Activity event count;
- failed jobs total + unresolved;
- known media vs cached media files;
- SQLite storage including `-wal` / `-shm` files;
- DDS_Data size;
- cache/media/log sizes;
- total known storage;
- last successful import;
- messages/imports/activity added this session;
- storage delta this session.

Until the dedicated Media milestone exists, `known_media` means registered attachment metadata rows. Embed metadata remains visible separately and is not falsely counted as a cached file.

## Database migration

Schema version is now:

```text
2
```

0.3.0 adds only:

```text
activity_events
subsystem_health
```

The existing archive tables are not rebuilt or reset.

A real 0.2.0-created SQLite database was upgraded in-place during local validation. Existing messages and capture fingerprints were preserved and the unchanged capture remained deduplicated.

## Expected Windows startup

Run:

```text
run_companion.bat
```

A healthy startup should resemble:

```text
DDS Companion v0.3.0  [RUNNING]
DDS_Data : C:\Users\...\AppData\Roaming\BetterDiscord\DDS_Data
Database : C:\Users\...\AppData\Local\DDS_Companion\database\dds.sqlite3
Watcher  : ACTIVE  poll=750 ms, settle=500 ms
Health   : DB=RUNNING | DDS=RUNNING | Importer=RUNNING | Watcher=RUNNING

Import   : seen=..., imported=..., unchanged=..., failed=0
Messages : +... new, ... existing refreshed; archive total=...
Context  : guilds=..., channels=..., threads=...
Media    : known=... attachments, cached=0 files; embeds=... (metadata only)
Storage  : SQLite=..., DDS JSON=..., known total=...
Session  : +... messages, +... imports, storage +...
Activity : total=..., session=+... events; failed jobs unresolved=0

Watching DDS_Data. Press Ctrl+C to stop cleanly.
```

When DDS changes a capture, the low-level watcher signal remains visible, followed by a human Activity event:

```text
[21:31:52] WATCH    changed: guilds\...\capture.json (settling)
[21:31:52] ACTIVITY +9 messages imported, 0 existing refreshed | guilds\...\capture.json
```

## Failure behavior

A malformed or otherwise failing capture:

1. is isolated from the watcher loop;
2. is recorded in `failed_jobs`;
3. creates an `ERROR` Activity record;
4. moves importer health to `DEGRADED`;
5. does not stop observation of other capture files.

When that capture later imports successfully, its unresolved failed job is resolved. Importer health returns to `RUNNING` only when no unresolved import failures remain.

## Presentation isolation

Activity subscribers are deliberately isolated:

```text
Core -> ActivityService -> [CLI printer]
                        -> [future PySide6 Dashboard]
                        -> [future tray/status surface]
```

If one subscriber throws an exception, other subscribers still receive the event and archive processing continues.

## Run modes

Persistent watcher:

```text
run_companion.bat
```

One-shot import:

```text
run_once.bat
```

or:

```text
python -m dds_companion.app --once
```

Machine-readable startup + event stream:

```text
python -m dds_companion.app --json
```

## Validation performed before publication

```text
Python compileall                                      PASS
0.1.x importer regression tests                       4/4 PASS
0.2.x watcher regression/lifecycle tests              7/7 PASS
0.3.0 observability tests                              7/7 PASS
Total unit tests                                      18/18 PASS
Activity persistence + subscriber isolation           PASS
Health RUNNING / DEGRADED + stale heartbeat            PASS
Failure recovery health transition                    PASS
Malformed capture -> corrected capture process test    PASS
Session stats / media split                           PASS
Watcher + Activity integration process smoke test     PASS
Clean SIGINT / Ctrl+C exit code 0                     PASS
0.2.0-created SQLite -> 0.3.0 in-place migration      PASS
Archive preservation across migration                 PASS
Unchanged capture dedup after migration               PASS
```

## Live Windows gate for VERIFIED

0.3.0 is intentionally **not** marked VERIFIED until it runs against the real Windows archive.

Live test:

1. start `run_companion.bat` over the existing Companion database;
2. confirm the startup `Health` row is all `RUNNING`;
3. confirm existing messages are still present and unchanged captures deduplicate;
4. open or scroll a Discord channel/thread so DDS 0.5.2 changes a capture;
5. confirm `WATCH` is followed by an `ACTIVITY ... imported` line;
6. press `Ctrl+C` and confirm clean shutdown.

No destructive failure injection is required on the real archive; malformed-capture and recovery paths are covered by automated tests.

## Scope deliberately NOT added in 0.3.0

- no PySide6 GUI yet;
- no media download;
- no full-text search;
- no Drive sync;
- no Discord credential/token access;
- no hidden-history fetching;
- no message-version/deletion classification yet.

The next intended milestone after live verification is **0.4.0 — first PySide6 Dashboard**, consuming these Activity/Health/Stats APIs rather than reaching into watcher/SQLite internals itself.
