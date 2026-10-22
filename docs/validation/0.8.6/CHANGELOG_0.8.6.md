# DDS Companion 0.8.6 — candidate changelog

- Add positive, persisted voice/stage source-deletion evidence and SOURCE_GONE.
- Keep cached files and all archive metadata; retain last-known terminal URLs.
- Remove verified deleted sources from awaiting/actionable counts; add passive
  «Источник удалён» in Dashboard, Library, attachment details and exports.
- Keep terminal objects out of retry/planning; allow only fresh usable source recovery.
- Extend settled import/watcher delivery without changing capture-v2.
- Bump package/runtime/overlay/About and generated Windows metadata to 0.8.6.
- Linked Plugin 0.5.4 adds bounded positive audit-log evidence and cancellation cleanup.
- Make EVICTED media visible in the UI as «Кэш очищен» without changing planner or retention semantics.
- Show evicted counts in Status/runtime and Library scope summaries; attachment details distinguish policy cleanup from manual cleanup.

Installer, updater protocol, CDN download strategy, user installations and caches
were not changed. Existing product features and visual assets remain inherited
from the accepted 0.8.5 baseline.
