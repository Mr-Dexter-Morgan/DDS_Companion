# DDS Companion 0.5.1 — UI / Settings Polish Candidate

Status: **CANDIDATE / AUTOMATED PASS / WINDOWS LIVE PENDING**  
Baseline: **0.5.0 — VERIFIED / LIVE TESTED / CURRENT RECOMMENDED**  
Date: **2026-09-18**

## What this release is

0.5.1 is a deliberately bounded user-interface release. It keeps the verified 0.5.0 archive/media runtime intact and cleans up the user-facing shell before the productization work begins in 0.6.x.

No database schema, media lifecycle, downloader, Watcher, capture contract or internal page/service identifier is renamed in this patch.

## Changes in 0.5.1

### Main navigation
User-facing labels are localized while internal page IDs stay unchanged:
- Dashboard → **Главная**
- Library → **Библиотека**
- Activity → **Активность**
- Health → **Статус**
- Settings → **Настройки**

### Главная
- removed the visible manual **Обновить** button;
- automatic snapshot refresh remains active;
- returning to Главная explicitly requests a fresh snapshot from the existing runtime;
- internal refresh capability is preserved.

### Настройки
Tabs are now:
- **Общие**
- **Хранилище**
- **Архив**
- **Диагностика**

**Общие** now owns behavior toggles:
- **Автоматическая загрузка медиа** — same persisted `media_autodownload_enabled` backend key;
- **Подтверждать очистку кэша** — same persisted `confirm_media_cache_clear` backend key.

**Хранилище** is ordered by user importance:
1. **Хранение медиа** — cache size / max file / retention / cleanup;
2. **Использование хранилища** — SQLite, DDS JSON, media, other, logs;
3. **Расположение файлов** — direct folder access last.

Technical diagnostic states/events such as `RUNNING`, `STALE_URL`, `EVICTED`, `DOWNLOADING`, `media_cached` remain unchanged.

## Data-safety invariants preserved

1. SQLite messages, DDS JSON and attachment metadata remain archive/source-of-truth data.
2. Media binaries remain replaceable cache.
3. Media clear/eviction cannot delete archived messages or attachment metadata.
4. Media failures remain isolated from the healthy local archive.
5. Existing 0.5.0 settings keys and media behavior are preserved.

## Run

Normal source/dev desktop launch:

`run_companion.bat`

The final 1.0 product will replace the BAT-facing workflow with packaged EXE/Installed/Portable flows according to the project roadmap.

## Validation

Automated gate for this candidate: **74/74 PASS**.

Run:

`python -m unittest discover -s dds_companion/tests -v`

Also see:
- `VALIDATION.txt`
- `NEXT_PATCH_0.5.1.md`
- `UI_CONTRACT.md`
- `MEDIA_BACKFILL_CONTRACT.md` — verified 0.5.0 media foundation retained unchanged
- `OBSERVABILITY_CONTRACT.md`

0.5.1 must pass the short Windows visual/live gate before promotion.
