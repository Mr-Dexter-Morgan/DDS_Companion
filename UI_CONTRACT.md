# DDS Companion 0.4.2 — UI Contract

## Settings information architecture

`Settings` MUST open with the **Основные** tab selected.

### Основные

Primary space for user-facing Companion behavior and policies. In 0.4.2 it
contains the current read-only Watcher policy plus a restrained explanatory
card. Do not add controls that look editable unless their values can actually
be persisted, validated and restored.

### Paths & Storage

Secondary service/diagnostic page containing only filesystem locations and
quick access actions:

- Library / Companion data
- DDS_Data
- SQLite database
- Logs
- Media cache
- Cache
- Backups

This tab MUST remain vertically scrollable and MUST preserve Copy/Open actions.

## Existing 0.4.1 contracts retained

- Dashboard is scroll-safe.
- Compact / Standard / Large profiles remain adaptive.
- Sidebar idle / hover / selected states remain visually distinct.
- Library is the single location for the main Open library folder action.
- Normal launch uses pythonw; debug launch keeps a console.
