# DDS — Discord Data Snatcher

DDS Companion is the local-first desktop side of DDS. It imports captures from the BetterDiscord DDS plugin, stores a durable SQLite archive, keeps a recoverable media cache, browses Discord knowledge locally, packages selected branches into ZIP archives, and now includes a recoverable Windows updater foundation.

> Release line: 0.x / Public Preview. Current public baseline: v0.6.2. Active validated candidate: 0.7.0.dev0 — Safe Updater Foundation. Public v0.7.0 has not been published yet.

## What 0.7.0 adds

- External DDSUpdater.exe; the running DDS process never overwrites itself.
- Stable DDS.exe bootstrap and versioned application payloads under versions/<version>.
- Release-manifest contract with SHA-256, exact package size, updater protocol and package format.
- Staging and ZIP validation before promotion, including traversal/symlink/Windows collision/protected-data rejection.
- Transactional current.json / previous.json / pending_update.json pointers.
- Startup acknowledgement and automatic rollback when the candidate cannot prove core runtime readiness.
- Power-loss recovery for the pending/current pointer handoff.
- Cross-process update lock, free-space preflight, bounded retries/cancellation, durable journal and updater log.
- Windows process-tree termination so failed PyInstaller candidates cannot strand locked payload files.
- Manual update flow plus optional bounded background checks.
- Regression coverage proving user data remains byte-identical across successful update and forced rollback.

## Existing archive/export features

- Manual branch packaging: Text Only or Text + Cache.
- Canonical package contents: manifest.json, content.md, messages.json, media_index.json and optional media/.
- Honest incomplete-package reporting when media is unavailable.
- Branch-scoped cache clear, data deletion and full local branch deletion.
- Persistent export destination.
- Windows Known Folder support for redirected Documents.
- Public branding for DDS — Discord Data Snatcher.

## Architecture

DDS is deliberately layered:

Discord Desktop -> BetterDiscord -> DDS Plugin -> local capture files -> DDS Companion -> SQLite archive -> media cache / ZIP export

Updater ownership is a separate optional layer:

GitHub Release -> verified download -> staging -> DDSUpdater.exe -> versioned app payload -> startup ACK / rollback

The local SQLite archive is the durable source of truth. Media cache, exported ZIPs and update packages are derived/rebuildable layers. Export, network or updater failures must not damage or block archive readability.

BetterDiscord plugin repository: https://github.com/Mr-Dexter-Morgan/DDS_BD_Plugin

## Windows quick start

1. Install and configure the DDS BetterDiscord plugin.
2. Download the Windows ZIP from the latest GitHub Release.
3. Extract the whole ZIP.
4. Run DDS.exe.

DDS is currently a PyInstaller onedir application payload behind a stable bootstrap launcher. Setup/Repair is planned for 0.9.0.

## Build from source

Requirements: Python 3.11+; Windows is required for native release binaries.

Run build_windows.bat.

Expected output:
- dist\DDS\DDS.exe
- dist\DDS\DDSUpdater.exe
- dist\release\DDS-<version>-windows-x64.zip
- dist\release\DDS-<version>-update.zip
- dist\release\DDS-<version>-update.json

## Validation

The active 0.7.0 candidate gate includes three consecutive full unittest passes, compileall, native Windows builds for the app/bootstrap/updater, package integrity checks, and interactive EXE tests for successful promotion and watchdog rollback.

Current validated source: 170/170 tests x3 before the final native build/live gate.

Detailed status: VALIDATION.txt and LIVE_TEST_CHECKLIST_0.7.0.txt.

## Roadmap

0.7.0 Safe Updater Foundation is implemented and live-validated as a development candidate; publication/freeze is the remaining release step. Next planned layer: 0.8.0 Desktop Lifecycle (tray/autostart). See ROADMAP.md.

## History

Development snapshots from 0.1.0 through 0.6.2 are documented in HISTORY.md. Add v0.7.0 only when it is actually frozen/tagged.

## License

No open-source license has been granted yet. The repository is public for distribution, inspection and project history.
