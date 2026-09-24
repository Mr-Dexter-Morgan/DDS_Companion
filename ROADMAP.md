# DDS Companion Roadmap

Current baseline: **v0.6.2 Public Preview**.

This roadmap describes the intended order after 0.6.2. It is not a promise that an item is already implemented.

## Non-negotiable architecture rules

- SQLite/local archive remains the source of truth.
- Media cache, ZIP packages and future sync output are derived/rebuildable layers.
- The BetterDiscord plugin stays lightweight; Companion owns archive, media, export, update and desktop UX.
- Optional/network layers must never make the local archive unreadable.
- Installed and Portable modes share the same application code; only DataRoot/lifecycle integration may differ.
- Migrations stay additive and transactional.
- User archive data, settings, cache, exports and DDS_Data must survive application updates.

## 0.7.0 — Safe Updater Foundation

Goal: a recoverable updater that cannot corrupt DDS or user data.

- External updater process; DDS never overwrites its own running executable.
- Read release metadata, stage the candidate package, verify SHA-256, then validate the staged layout.
- Atomic promotion with rollback to the previous application build on failure.
- Update only application files; never touch SQLite, settings, cache, exports or DDS_Data.
- Clear failure reporting and retry behavior.
- Fault-injection/regression coverage for interrupted download, bad hash, incomplete package and failed promotion.
- Manual update flow first; background convenience must not weaken the safety model.

## 0.8.0 — Desktop Lifecycle

Goal: make DDS unobtrusive for everyday use.

- Tray lifecycle.
- Optional autostart.
- Explicit running/stopped/status behavior.
- Clean shutdown/restart interactions with archive/media runtime.
- No hidden dependency on network availability.

## 0.9.0 — Setup / Repair / Installer

Goal: make installation and recovery understandable without sacrificing Portable mode.

- Setup and repair flow for the installed profile.
- Preserve DataRoot and user data during repair/update.
- Correct shortcuts, application identity and uninstall behavior.
- Uninstall removes application-owned files only unless the user explicitly chooses to remove data.
- Portable distribution remains supported and behaviorally equivalent where Windows integration is not required.

## 1.0 — Stable Contract

Goal: freeze a dependable public contract.

- Migration/backward-compatibility review.
- Recovery and corruption-path testing.
- Documentation and release-process cleanup.
- Full Windows CI plus interactive live gate.
- Versioned public guarantees for archive readability and update safety.

## Later / deliberately unscheduled

- Automatic export/sync to a user-selected normal filesystem folder.
- External clients (Google Drive for Desktop, OneDrive, Dropbox, Yandex Disk, etc.) may sync that folder.
- Direct provider-specific OAuth/API integration is not part of the current DDS direction.

The ordering may change only when a real blocker justifies it. Architecture safety rules above do not.
