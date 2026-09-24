# DDS Companion development history

This Git history was reconstructed from preserved DDS Companion source snapshots because Git was introduced after development had already begun. The version commits preserve the archived source state (with generated `__pycache__`/`.pyc` files intentionally omitted and the app-icon master normalized losslessly-for-use to 512 px for a practical public Git history). Historical commit timestamps come from the newest file timestamp recorded inside each preserved ZIP.

| Version | Date | Main focus |
|---|---|---|
| `v0.1.0` | 2026-09-13 | Local archive foundation |
| `v0.2.0` | 2026-09-13 | Watcher and import pipeline |
| `v0.3.0` | 2026-09-13 | Observability and live-test contract |
| `v0.4.0` | 2026-09-13 | Desktop dashboard foundation |
| `v0.4.1` | 2026-09-13 | Responsive GUI polish |
| `v0.4.2` | 2026-09-14 | Settings information architecture |
| `v0.4.3` | 2026-09-15 | Health telemetry patch |
| `v0.4.4` | 2026-09-15 | Truthful health + plugin heartbeat |
| `v0.4.5` | 2026-09-16 | Startup / foreground reliability |
| `v0.4.6` | 2026-09-17 | UI and storage foundation; live-tested baseline |
| `v0.5.0` | 2026-09-17 | Media backfill core |
| `v0.5.1` | 2026-09-18 | UI and settings polish |
| `v0.5.2` | 2026-09-18 | Media attention / recovery states |
| `v0.5.3` | 2026-09-18 | Two-pane Library UX |
| `v0.5.4` | 2026-09-18 | Library message viewer + export selection |
| `v0.5.5` | 2026-09-19 | Library UX + media lifecycle visibility |
| `v0.5.6` | 2026-09-19 | Live UX cleanup + Activity dedup |
| `v0.5.7` | 2026-09-19 | Final BAT-era Library/Diagnostics polish |
| `v0.5.8` | 2026-09-19 | Explicit Library selection hotfix; live-tested prototype |
| `v0.6.0` | 2026-09-20 | Application foundation + native Windows EXE |
| `v0.6.1` | 2026-09-21 | Archive reset boundary + passive media rediscovery |
| `v0.6.2` | 2026-09-21 | Manual ZIP export + branch management + branding + redirected Documents + Windows recovery hardening |
| `v0.7.0` | 2026-09-24 | Safe updater foundation + transactional rollback + single-instance/runtime/build hardening |
| `v0.7.1` | 2026-09-24 | Media-cache race fix + truthful updater status telemetry |

The archived `CHANGELOG.txt`, validation files, live-test checklists and contracts inside each tagged tree provide the detailed record for that milestone.

`v0.6.2` is tagged on the validated Public Preview release commit. That commit layers release documentation, Windows CI hardening and packaging metadata on top of the preserved candidate-r2 source snapshot.

`v0.7.1` is the current Public Preview release line. It carries the validated 0.7 updater foundation plus the manual-test fixes for media-cache scan races and updater status telemetry.
