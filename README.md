# DDS — Discord Data Snatcher

DDS Companion is the local-first desktop side of DDS. It imports captures from the BetterDiscord DDS plugin, stores a durable SQLite archive, keeps a recoverable media cache, browses Discord knowledge locally, packages selected branches into ZIP archives, and includes a recoverable Windows updater foundation.

> Release line: 0.x / Public Preview. Current public baseline: v0.6.2. Release-ready source freeze: v0.7.0 - Safe Updater Foundation. Public v0.7.0 has not been published yet.

## What 0.7.0 adds

- Separate DDSUpdater.exe; the running application never overwrites itself.
- Stable DDS.exe bootstrap and versioned application payloads under versions/<version>.
- Release-manifest contract with SHA-256, exact package size, updater protocol and package format.
- Staging and ZIP validation before promotion, including traversal/symlink/Windows collision/protected-data rejection.
- Transactional current.json / previous.json / pending_update.json pointers.
- Startup acknowledgement and automatic rollback when the candidate cannot prove core runtime readiness.
- Power-loss recovery, orphan-version cleanup and idempotent startup commit.
- Cross-process update lock, free-space preflight, bounded retries/cancellation, durable journal and updater log.
- Windows process-tree termination so failed PyInstaller candidates cannot strand locked payload files.
- Manual update flow, once-per-day background checks, optional auto-download and opt-in auto-install at natural exit.
- Window/presentation state capture for update restart.
- Single-instance protection: a second DDS launch activates the existing runtime instead of opening another archive process.
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
2. In GitHub Releases, download the ready-built Windows asset named DDS-<version>-windows-x64.zip.
3. **Do not download GitHub's Source code (zip) / Source code (tar.gz) if you only want to run DDS.** Those archives contain developer source and BAT/build tooling and therefore expect Python.
4. Extract the whole Windows ZIP.
5. Run DDS.exe.

The ready-built Windows ZIP already bundles the application runtime. **Python is not required on the user's PC.**

DDS is currently a PyInstaller onedir application payload behind a stable bootstrap launcher. Setup/Repair/Installer UX is planned for 0.9.0.

## Build from source

Requirements: Python 3.11+; Windows is required for native release binaries.

Run build_windows.bat.

The build pipeline:
- rejects overlapping builds with an OS-backed Windows named mutex before shared build/dist state is touched;
- fails closed if old build/dist files cannot be cleaned after bounded retry;
- regenerates Windows FileVersion/ProductVersion metadata from the current DDS source version;
- builds DDSApp.exe, DDS.exe and DDSUpdater.exe;
- produces the full Windows ZIP, update ZIP, SHA-256 files and update manifest;
- retries bounded transient Windows ZIP-read races and validates completed ZIPs before reporting success.

Expected output:
- dist/DDS/DDS.exe
- dist/DDS/DDSUpdater.exe
- dist/release/DDS-<version>-windows-x64.zip
- dist/release/DDS-<version>-update.zip
- dist/release/DDS-<version>-update.json

## Validation

The frozen v0.7.0 gate passed 174/174 tests three consecutive times after the final build-tooling changes, plus compileall, native Windows builds, a live concurrent-build rejection gate (primary exit 0 / secondary exit 16), package-integrity checks, final single-instance smoke, final update promotion smoke, and forced-timeout rollback validation.

Final local artifacts:
- DDS-0.7.0-windows-x64.zip SHA-256 e3cfd2307b83230c4cbf3fec7adf17015311f9596c19c37bd9b9054a51704e80
- DDS-0.7.0-update.zip SHA-256 b870d6a0fa8a934fa7e26ab4611cbe56a73220ad6b40bd91e366c0ff0e1cec56

Detailed status: VALIDATION.txt and LIVE_TEST_CHECKLIST_0.7.0.txt.

## Roadmap

0.7.0 Safe Updater Foundation is frozen and validated; only explicit public publication remains. Next planned layer: 0.8.0 Desktop Lifecycle (tray/autostart). See ROADMAP.md.

## History

Development snapshots from 0.1.0 onward are documented in HISTORY.md.

## License

No open-source license has been granted yet. The repository is public for distribution, inspection and project history.
