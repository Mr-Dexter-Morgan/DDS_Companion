# DDS Companion Roadmap

Current public baseline: **v0.7.1 Public Preview**. The 0.7 updater foundation is released; 0.8.0 Desktop Lifecycle is next.

## Non-negotiable architecture rules

- SQLite/local archive remains the source of truth.
- Media cache, ZIP packages and future sync output are derived/rebuildable layers.
- The BetterDiscord plugin stays lightweight; Companion owns archive, media, export, update and desktop UX.
- Optional/network layers must never make the local archive unreadable.
- Installed and Portable modes share application code; only DataRoot/lifecycle integration may differ.
- Migrations stay additive and transactional.
- User archive data, settings, cache, exports and DDS_Data must survive application updates.

## 0.7.0 - Safe Updater Foundation

Status: released through the 0.7.1 Public Preview patch line after full Windows CI and manual testing.

Implemented:
- External updater process and stable bootstrap launcher.
- GitHub Release metadata and versioned manifest contract.
- Verified download/staging with SHA-256, exact size and ZIP validation.
- Protected user-data boundary and byte-identical regression checks.
- Transactional current/previous/pending version pointers.
- Startup ACK tied to core runtime readiness.
- Automatic rollback on crash/startup timeout.
- Power-loss-safe/idempotent startup commit and orphan-version recovery.
- Durable journal and updater-specific log.
- OS-backed cross-process update lock and free-space preflight.
- Bounded retry/cancel behavior.
- Windows process-tree termination and failed-version cleanup.
- Manual update UI, optional once-per-day background checks, optional auto-download and opt-in auto-install at natural exit.
- Window/presentation state capture for update restart.
- Single-instance GUI boundary.
- Windows build metadata generated from the source version on every build.
- Fail-closed build/dist cleanup with bounded retry.
- Whole-pipeline Windows build mutex; concurrent builds are rejected before shared state is touched.
- Bounded transient ZIP-read retry plus completed-archive integrity validation.
- Real Windows EXE happy-path, final 0.7.0 update smoke and forced-timeout rollback validation.

0.7.1 patch follow-up:
- Fixed media-cache/statistics traversal races that could terminate the GUI runtime on WinError 3.
- Unified updater Status with the updater's persistent check state and corrected the 24-hour scheduler display.

## 0.8.0 - Desktop Lifecycle

Goal: make DDS unobtrusive for everyday use.
- Tray lifecycle.
- Optional autostart.
- Explicit running/stopped/status behavior.
- Clean shutdown/restart interactions with archive/media runtime.
- Reuse the 0.7.0 saved presentation/hidden-to-tray update state.
- No hidden network dependency.

## 0.9.0 - Setup / Repair / Installer

Goal: make installation/recovery understandable without sacrificing Portable mode.
- Setup and repair flow.
- Preserve DataRoot during repair/update.
- Correct shortcuts, identity and uninstall behavior.
- Uninstall removes app-owned files only unless user explicitly removes data.
- Portable distribution remains supported.

## 1.0 - Stable Contract

- Migration/backward-compatibility review.
- Recovery/corruption-path testing.
- Documentation and release-process cleanup.
- Full Windows CI plus interactive live gate.
- Versioned guarantees for archive readability and update safety.

## Later / deliberately unscheduled

- Automatic export/sync to a user-selected normal filesystem folder.
- External clients may sync that folder.
- Direct provider-specific OAuth/API is not part of current DDS direction.
