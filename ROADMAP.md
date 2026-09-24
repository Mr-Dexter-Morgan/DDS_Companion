# DDS Companion Roadmap

Current public baseline: v0.6.2 Public Preview. Active validated candidate: 0.7.0.dev0 Safe Updater Foundation.

A candidate being implemented/validated does not mean its public GitHub tag/release already exists.

## Non-negotiable architecture rules

- SQLite/local archive remains the source of truth.
- Media cache, ZIP packages and future sync output are derived/rebuildable layers.
- The BetterDiscord plugin stays lightweight; Companion owns archive, media, export, update and desktop UX.
- Optional/network layers must never make the local archive unreadable.
- Installed and Portable modes share application code; only DataRoot/lifecycle integration may differ.
- Migrations stay additive and transactional.
- User archive data, settings, cache, exports and DDS_Data must survive application updates.

## 0.7.0 — Safe Updater Foundation

Status: candidate complete and Windows live-validated; public v0.7.0 release not yet published.

Implemented:
- External updater process and stable bootstrap launcher.
- GitHub Release metadata and versioned manifest contract.
- Verified download/staging with SHA-256, exact size and ZIP validation.
- Protected user-data boundary and byte-identical regression checks.
- Transactional current/previous/pending version pointers.
- Startup ACK tied to core runtime readiness.
- Automatic rollback on crash/startup timeout.
- Power-loss-safe/idempotent startup commit.
- Durable journal and updater-specific log.
- Cross-process update lock and free-space preflight.
- Bounded retry/cancel behavior.
- Windows process-tree termination and failed-version cleanup.
- Manual update UI, optional daily background check and opt-in automatic install.
- Real Windows EXE happy-path and forced-timeout rollback validation.

Remaining before publication:
- Freeze 0.7.0.dev0 to final 0.7.0.
- Re-run final release gate with final version metadata.
- Update HISTORY.md.
- Tag and publish GitHub pre-release only after explicit release approval.

## 0.8.0 — Desktop Lifecycle

Goal: make DDS unobtrusive for everyday use.
- Tray lifecycle.
- Optional autostart.
- Explicit running/stopped/status behavior.
- Clean shutdown/restart interactions with archive/media runtime.
- No hidden network dependency.

## 0.9.0 — Setup / Repair / Installer

Goal: make installation/recovery understandable without sacrificing Portable mode.
- Setup and repair flow.
- Preserve DataRoot during repair/update.
- Correct shortcuts, identity and uninstall behavior.
- Uninstall removes app-owned files only unless user explicitly removes data.
- Portable distribution remains supported.

## 1.0 — Stable Contract

- Migration/backward-compatibility review.
- Recovery/corruption-path testing.
- Documentation and release-process cleanup.
- Full Windows CI plus interactive live gate.
- Versioned guarantees for archive readability and update safety.

## Later / deliberately unscheduled

- Automatic export/sync to a user-selected normal filesystem folder.
- External clients may sync that folder.
- Direct provider-specific OAuth/API is not part of current DDS direction.
