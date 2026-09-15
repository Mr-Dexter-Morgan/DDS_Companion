# DDS Companion 0.4.4 — Health Truthfulness & Plugin Heartbeat Candidate

Project: **DDS — Discord Data Snatcher**  
Authors: **Mr_Dexter_Morgan, Masya**

> Are you sure your data is secure?

Status: **BUILT / LOCAL TESTING**

0.4.4 is the follow-up to the Windows live review of 0.4.3. The accepted
Dashboard / Library / Activity layout and archive pipeline stay intact; the
Health layer is tightened so it reports the state of the full capture chain,
not merely whether Companion's own worker threads are alive.

## What changed

- Sidebar branding is split into `DDS` / `Companion` / version lines so the
  product name remains readable without widening the navigation rail.
- User-facing **DEGRADED** wording is replaced by **LIMITED**. Legacy persisted
  DEGRADED rows are still accepted and normalized on read for compatibility.
- Health now shows a dedicated **DDS Plugin** card in addition to Database,
  DDS_Data, Importer, Watcher, Discord and Update check.
- DDS Plugin health consumes the `plugin_heartbeat.json` contract introduced by
  the 0.5.3 plugin candidate:
  - fresh RUNNING heartbeat -> RUNNING;
  - clean STOPPED heartbeat -> NOT RUNNING;
  - old heartbeat -> STALE / NOT RUNNING according to age;
  - heartbeat-capable plugin with missing/invalid heartbeat -> LIMITED;
  - pre-heartbeat plugin -> UPDATE AVAILABLE rather than a false failure.
- When `DDS_Data` disappears, Watcher is presented as **WAITING** instead of
  misleadingly remaining RUNNING merely because its thread is alive.
- Discord being closed now makes the capture chain **LIMITED** while preserving
  access to the local archive. It is still not treated as an application error.
- Importer timing is labeled **Last import** instead of the misleading
  `Heartbeat` wording.
- Overall Health produces a structured list of reasons and a tooltip. Hovering
  the overall status or an individual state word explains why the current state
  is shown.
- Activity records Health state transitions and reason changes only. A stable
  repeated LIMITED state does not spam the journal; recovery is logged once.
- The existing DDS_Data removal/recovery behavior remains automatic: source
  loss limits capture, source restoration returns Health to RUNNING without a
  Companion restart.

## Plugin compatibility

The current stable plugin remains **0.5.2** until the new heartbeat candidate
passes live BetterDiscord testing. With 0.5.2, Companion 0.4.4 shows
**UPDATE AVAILABLE** for the plugin health capability rather than declaring the
plugin broken.

The intended companion update flow is documented but is not enabled in this
candidate: once a newer plugin has a verified GitHub Release, Companion may
offer to download it, back up the current `.plugin.js`, replace it safely,
verify the new heartbeat and roll back on failure.

## What did not change

- No archive schema migration.
- Import/dedup/capture semantics are unchanged.
- No Media Backfill or cache policy yet.
- No live GitHub updater yet.
- No AI export or Google Drive synchronization in this release.

## Validation

- Python compileall: **PASS**
- Full automated suite: **38/38 PASS**
- Plugin compatibility states covered: old plugin, fresh heartbeat, STOPPED,
  STALE, missing source.
- Health reason/tooling and source-loss WAITING behavior covered by regression
  tests.

Native Windows + BetterDiscord live validation is still required. Follow
`LIVE_TEST_CHECKLIST_0.4.4.txt` one scenario at a time.
