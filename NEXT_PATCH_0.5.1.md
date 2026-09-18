# DDS Companion 0.5.1 — UI / Settings Polish

Status: **PLANNED / NEXT DEVELOPMENT PATCH**  
Date fixed: **2026-09-18**

## Goal

Polish the user-facing shell after 0.5.0 without changing archive/media architecture. This release is intentionally visual/organizational and should not become a hidden productization rewrite.

## Scope

### Main navigation — user-facing labels only
- `Dashboard` -> **Главная**
- `Library` -> **Библиотека**
- `Activity` -> **Активность**
- `Health` -> **Статус**
- `Settings` -> **Настройки**
- `Diagnostics` -> **Диагностика**

Do **not** rename internal route/page IDs, service names, modules, technical events or database/runtime identifiers.

### Главная
- remove the visible manual **Обновить** button;
- keep automatic data refresh behavior;
- keep internal refresh capability for tests/diagnostics/recovery;
- if not already guaranteed, returning/opening Главная should immediately render current model state without requiring a user refresh click.

### Настройки — sections
User-facing section labels:
- `General` -> **Общие**
- `Data / Storage` -> **Хранилище**
- `Archive` -> **Архив**
- `Diagnostics` -> **Диагностика**

### Общие
Move from the storage page:
- `Automatic Media Download` -> **Автоматическая загрузка медиа**
  - description: **Автоматически загружать вложения Discord в локальный медиакэш.**
- `Confirm Cache Cleanup` -> **Подтверждать очистку кэша**
  - description: **Запрашивать подтверждение перед очисткой медиакэша.**

These remain the same persisted settings/backend keys; only placement and user-facing copy change.

### Хранилище — order by importance
1. **Хранение медиа** (`Media Cache Policy`) — first and most prominent.
2. **Использование хранилища** (`Storage Usage`) — second.
3. **Расположение файлов** / open-folder controls — last, because they are rarely used technical access.

If moving controls leaves an empty `Media Backfill` group, remove the empty visual group only; do not remove media backend functionality.

## Localization boundary

Do not translate technical diagnostic/event/state identifiers solely for appearance. Examples that stay unchanged where used diagnostically:
`media_cached`, `STALE_URL`, `EVICTED`, `DOWNLOADING`, `RUNNING` and similar internal/status vocabulary where translation would reduce diagnostic precision.

## Non-goals

Not part of 0.5.1:
- Portable/Installed data-root refactor;
- tray/autostart implementation;
- EXE packaging rewrite;
- updater/installer;
- media schema/lifecycle redesign;
- new archive/search features.

Those start from 0.6.0 onward according to `ROADMAP.md`.

## Validation gate

- existing automated regression remains green;
- UI launches and all renamed navigation buttons route to the same underlying pages;
- moved settings persist across restart and still drive the same backend behavior;
- Главная remains current without the manual refresh button;
- no new traceback/shutdown/focus regression.
