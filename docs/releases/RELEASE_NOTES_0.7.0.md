# DDS Companion v0.7.0 - Safe Updater Foundation

Release-ready source/artifact freeze. Public GitHub v0.7.0 publication is pending explicit approval.

## Highlights

- Separate DDSUpdater.exe; the running application never overwrites itself.
- Stable DDS.exe bootstrap for versioned application payloads.
- Versioned release manifest with exact size, SHA-256, updater protocol and package format.
- ZIP validation rejects traversal, symlinks, Windows path collisions and protected user-data targets.
- Transactional promotion with startup acknowledgement and automatic rollback.
- Recoverable/idempotent pointer handoff across crash/power-loss windows plus orphan-version cleanup.
- OS-backed update lock, free-space checks, bounded retry/cancel, durable journal and updater log.
- Failed PyInstaller candidates are terminated as a Windows process tree.
- Manual update controls, once-per-day background checking, optional auto-download and opt-in auto-install at natural exit.
- Window/presentation state is carried across updater restart.
- GUI single-instance guard prevents duplicate archive runtimes.
- Windows build metadata is generated from the current source version on every build.
- Build cleanup fails closed rather than continuing from a partially deleted dist tree.
- A Windows named mutex rejects concurrent build pipelines before they can race over build/dist.
- ZIP packaging retries bounded transient file-read races and validates the finished archive before success.

## Data-safety contract

Updater ownership is application payload only. SQLite/archive data, settings, media/cache, exports and DDS_Data are outside updater ownership.

Automated regressions verify user files remain byte-identical after successful promotion and forced rollback.

## Windows download

For a ready-to-run Windows build, use DDS-0.7.0-windows-x64.zip from the release assets.

Do not use GitHub's automatically generated Source code (zip) / Source code (tar.gz) as the Windows application package. Those are developer sources and expect Python/build tooling. The ready-built Windows ZIP does not require the user to install Python.

## Final validation

- 174 tests x3 after the final build-tooling changes.
- compileall PASS.
- Native Windows build PASS.
- Concurrent-build gate PASS: primary exit 0; overlapping secondary exit 16.
- DDS.exe, DDSUpdater.exe and DDSApp.exe FileVersion/ProductVersion = 0.7.0.
- Full ZIP SHA-256: e3cfd2307b83230c4cbf3fec7adf17015311f9596c19c37bd9b9054a51704e80
- Update ZIP SHA-256: b870d6a0fa8a934fa7e26ab4611cbe56a73220ad6b40bd91e366c0ff0e1cec56
- Both ZIPs pass integrity validation; update manifest hash/size/version match.
- Final single-instance EXE smoke PASS.
- Final updater smoke PASS: 0.7.0 -> synthetic 0.7.1, ACK, journal COMPLETE.
- Forced-timeout rollback PASS on the same updater logic: broken candidate removed, prior working version restored, journal FAILED.

## Scope boundary

0.7.0 does not add tray/autostart, Setup/Repair/Installer UX, provider-specific cloud OAuth/API, or Library redesign.
