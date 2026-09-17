# DDS Companion 0.4.6 — UI Contract

## Navigation
Dashboard / Library / Activity / Health / Settings.

## Dashboard
Dashboard is for current state, archive growth, recent activity and storage overview.
It must not duplicate the detailed subsystem Health page and must not expose raw maintenance shortcuts.

## Global Health
The top status is the quick state indicator. Outside Health it is a shortcut to Health.
Health itself owns subsystem truth, reasons, timestamps and last-error context.

## Settings
Tabs: General / Data & Storage / Archive / Diagnostics.
Only controls with real behavior and persistence may be editable.

## Data safety
SQLite and DDS JSON are archive/source-of-truth data, never cache.
Only media binary cache can be cleared by the 0.4.6 UI.
No generic Clear all exists.

## Responsive behavior
1366x768 uses compact layout. Dashboard remains vertically scroll-safe.
Startup foreground is a one-shot action and may never become persistent TOPMOST/focus stealing.
