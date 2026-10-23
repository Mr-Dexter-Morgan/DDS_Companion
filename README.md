# DDS — Discord Data Snatcher

[![Скачать DDS 0.8.8](https://img.shields.io/badge/%D0%A1%D0%9A%D0%90%D0%A7%D0%90%D0%A2%D0%AC_DDS-0.8.8-6C63FF?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/Mr-Dexter-Morgan/DDS_Companion/releases/download/v0.8.8/DDS-0.8.8-windows-x64.zip)

**Текущая стабильная версия: DDS Companion 0.8.8.**  
Готовая Windows x64-сборка не требует установленного Python.

## Что такое DDS

DDS — локальный архиватор Discord.

- **DDS Plugin** для BetterDiscord сохраняет данные, которые реально загрузил Discord-клиент.
- **DDS Companion** импортирует их в локальный SQLite-архив, показывает Библиотеку, ведёт медиакэш и умеет упаковывать выбранные ветки в ZIP.

DDS не выгружает сервер целиком через Discord API. В архив попадает то, что Discord-клиент фактически увидел и что Plugin успел сохранить.

## Установка

1. Установите Discord.
2. Установите BetterDiscord.
3. Установите и включите **DDS Plugin 0.5.4**:
   https://github.com/Mr-Dexter-Morgan/DDS_BD_Plugin/releases/tag/v0.5.4
4. Скачайте **DDS-0.8.8-windows-x64.zip**:
   https://github.com/Mr-Dexter-Morgan/DDS_Companion/releases/tag/v0.8.8
5. Полностью распакуйте ZIP в отдельную папку.
6. Запустите **DDS.exe**.

Не запускайте отдельный `DDS.exe`, вытащенный из сборки: рядом должны оставаться `DDSUpdater.exe`, `current.json` и каталог `versions`.

## Где хранятся данные

DDS Plugin:

`%APPDATA%\BetterDiscord\DDS_Data`

DDS Companion:

`%LOCALAPPDATA%\DDS_Companion`

SQLite-архив — долговечный источник истины. Медиакэш и экспортированные ZIP-файлы являются производными данными.

## Что вошло в 0.8.8

- **Скачать снова / Manual Re-cache** для очищенных медиа.
- Сохранение re-cache намерения через протухшую Discord-ссылку до fresh rediscovery.
- Исправление ложного **Discord NOT RUNNING** на локализованной Windows.
- Race-safe SQLite startup/migrations.
- Новый квадратный **16×12 Tetris-style Media Cache**.
- Адаптивный визуальный масштаб для режима медиакэша **Без ограничений**.
- Reproducible Windows build на Python 3.11.

Полные release notes: [docs/releases/RELEASE_NOTES_0.8.8.md](docs/releases/RELEASE_NOTES_0.8.8.md)

## Архитектура

`Discord → BetterDiscord → DDS Plugin → DDS_Data → DDS Companion → SQLite archive → media cache / ZIP export`

Обновление приложения идёт отдельным безопасным слоем:

`GitHub Release → verified update ZIP → DDSUpdater.exe → versioned app → startup ACK / rollback`

Сетевые функции, GitHub и медиакэш не должны мешать чтению уже существующего локального архива.

## Сборка из исходников

Требования:
- Windows;
- Python 3.11.

```bat
python -m venv .venv-build
.venv-build\Scripts\python -m pip install -r requirements-build.txt
build_windows.bat
```

Основные выходные файлы:

- `dist/DDS/DDS.exe`
- `dist/DDS/DDSUpdater.exe`
- `dist/release/DDS-<version>-windows-x64.zip`
- `dist/release/DDS-<version>-update.zip`
- `dist/release/DDS-<version>-update.json`

## Что лежит в корне репозитория и зачем

- `DDSApp.spec`, `DDSLauncher.spec`, `DDSUpdater.spec` — PyInstaller build definitions.
- `run_companion.pyw`, `run_launcher.pyw`, `run_updater.py` — реальные build entrypoints.
- `build_windows.bat`, `tools/`, `requirements-build.txt` — native Windows build/release pipeline.
- `dds_companion/` и `dds_companion_patchxx.py` — runtime source.
- `assets/` — ресурсы приложения.
- `.github/workflows/` — CI и публикация релизов.
- `ROADMAP.md` и текущие release notes — минимальная проектная документация.

## Документация

- [ROADMAP.md](ROADMAP.md)
- [Release notes 0.8.8](docs/releases/RELEASE_NOTES_0.8.8.md)

## Лицензия

Отдельная open-source лицензия пока не предоставлена. Репозиторий публичен для распространения, проверки и истории проекта.
