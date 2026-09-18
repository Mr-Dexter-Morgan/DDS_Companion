# DDS Companion 0.5.1 — UI Contract

## Navigation
User-facing sidebar labels:
**Главная / Библиотека / Активность / Статус / Настройки**.

Internal page IDs remain:
`Dashboard / Library / Activity / Health / Settings`.
UI localization must not rename routing/service/runtime identifiers.

## Главная
Главная is for current state, archive growth, recent activity and storage overview.
It must not duplicate detailed subsystem status or expose raw maintenance shortcuts.

There is no visible manual refresh button. Automatic refresh remains the normal behavior; reopening Главная requests a fresh model snapshot through the existing runtime.

The Media metric remains registry-backed: known media / successfully cached media. Storage usage uses actual filesystem bytes and keeps consistent category colors.

## Global status
The top status pill remains a quick state indicator. Outside the Статус page it opens that page.
Technical state vocabulary (`RUNNING`, `LIMITED`, `STALE`, etc.) remains unchanged.

## Настройки
Tabs: **Общие / Хранилище / Архив / Диагностика**.
Only controls with real behavior and persistence may be editable.

### Общие
- **Автоматическая загрузка медиа** -> existing `media_autodownload_enabled`.
- **Подтверждать очистку кэша** -> existing `confirm_media_cache_clear`.
- Future tray/autostart controls are not shown until their backend exists.

### Хранилище
Order is intentional:
1. **Хранение медиа** — cache limit / max file / retention / cleanup.
2. **Использование хранилища** — storage breakdown.
3. **Расположение файлов** — direct technical folder access.

### Архив
Informational only. Archive/source-of-truth data is not cache and has no destructive clear control.

### Диагностика
User-facing action labels may be Russian, but diagnostic/state/event identifiers remain technically precise.

## Data safety
SQLite and DDS JSON are archive/source-of-truth data, never cache.
Media binaries are replaceable cache.
No generic Clear all exists.

## Responsive behavior
1366x768 uses compact layout. Главная and Настройки remain vertically scroll-safe.
Startup foreground is a one-shot action and may never become persistent TOPMOST/focus stealing.
