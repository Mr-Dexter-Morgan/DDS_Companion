# DDS Companion 0.5.0 — UI Contract

## Navigation
Dashboard / Library / Activity / Health / Settings.

## Dashboard
Dashboard is for current state, archive growth, recent activity and storage overview.
It must not duplicate the detailed subsystem Health page and must not expose raw maintenance shortcuts.

The Media metric is registry-backed: known media / successfully cached media. Storage usage uses actual filesystem bytes. The horizontal category bars must use the same colors as their donut segments (SQLite, DDS JSON, Media cache, Other, Logs) so the chart reads as one visual system.

## Global Health
The top status is the quick state indicator. Outside Health it is a shortcut to Health.
Health itself owns subsystem truth, reasons, timestamps and last-error context.

0.5.0 adds `Media Backfill` as a dedicated Health card. Media failure is visible but non-critical to local archive availability.

## Settings
Tabs: General / Data & Storage / Archive / Diagnostics.
Only controls with real behavior and persistence may be editable.

### Data & Storage
- Automatic media download is a real persistent switch and defaults Off. Both explicit enable and disable actions are recorded in Activity.
- Cache size, max single file and retention settings are enforced by the real media backend.
- Clear media cache removes binaries only.

## Data safety
SQLite and DDS JSON are archive/source-of-truth data, never cache.
Media binaries are replaceable cache.
No generic Clear all exists.

## Responsive behavior
1366x768 uses compact layout. Dashboard and Settings remain vertically scroll-safe.
Startup foreground is a one-shot action and may never become persistent TOPMOST/focus stealing.
