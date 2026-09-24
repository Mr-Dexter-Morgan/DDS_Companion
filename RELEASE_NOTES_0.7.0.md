# DDS Companion v0.7.0 — Safe Updater Foundation

Release-candidate draft. Current source version is 0.7.0.dev0; public v0.7.0 has not been created yet.

## Highlights

- Separate DDSUpdater.exe; the running application never overwrites itself.
- Stable DDS.exe bootstrap for versioned application payloads.
- Versioned release manifest with exact size, SHA-256, updater protocol and package format.
- ZIP validation rejects traversal, symlinks, Windows path collisions and protected user-data targets.
- Transactional promotion with startup acknowledgement and automatic rollback.
- Recoverable/idempotent pointer handoff across crash/power-loss windows.
- Cross-process update lock, free-space checks, bounded retry/cancel, durable journal and updater log.
- Failed PyInstaller candidates are terminated as a Windows process tree.
- Manual update controls, optional bounded background checking and opt-in automatic install.

## Data-safety contract

Updater ownership is application payload only. SQLite/archive data, settings, media/cache, exports and DDS_Data are outside updater ownership.

Automated regressions verify user files remain byte-identical after successful promotion and forced rollback.

## Candidate validation

- 170 tests x3.
- compileall PASS.
- Native Windows build PASS.
- Live success: dev0 -> synthetic dev1, ACK, journal COMPLETE.
- Live failure: dev1 -> broken dev2 -> watchdog rollback, dev1 restored, dev0 backup preserved, failed candidate removed, journal FAILED.

Final release freeze will repeat the gate after version metadata changes from 0.7.0.dev0 to 0.7.0.

## Scope boundary

0.7.0 does not add tray/autostart, Setup/Repair/Installer UX, provider-specific cloud OAuth/API, or Library redesign.
