# DDS — Discord Data Snatcher

[![Скачать DDS 0.7.1](https://img.shields.io/badge/%D0%A1%D0%9A%D0%90%D0%A7%D0%90%D0%A2%D0%AC_DDS-0.7.1-6C63FF?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/Mr-Dexter-Morgan/DDS_Companion/releases/download/v0.7.1/DDS-0.7.1-windows-x64.zip)

**Готовая сборка для Windows x64. Python устанавливать не нужно.**  
Текущая версия: **DDS Companion 0.7.1 Public Preview**. До появления полноценного DDS Setup установка выполняется вручную.

## Что такое DDS и зачем он нужен

**DDS — Discord Data Snatcher** — локальный архиватор Discord.

Проект создаётся для того, чтобы полезная информация из Discord не оставалась привязана только к самому Discord, конкретному серверу, каналу или временным ссылкам на медиа. DDS сохраняет увиденные Discord-клиентом данные на компьютере пользователя и постепенно собирает из них нормальный локальный архив, который можно просматривать независимо от сети и состояния исходного сервера.

DDS состоит из двух основных частей:

- **DDS Plugin** для BetterDiscord наблюдает сообщения, каналы и темы, которые Discord-клиент реально загрузил, и сохраняет структурированные capture-файлы;
- **DDS Companion** импортирует эти данные в долговечный локальный SQLite-архив, показывает их в Библиотеке, ведёт состояние архива и медиа, может локально кэшировать вложения и упаковывать выбранные ветки в ZIP.

DDS **не копирует весь Discord-сервер автоматически одним нажатием**. В архив попадает то, что Discord-клиент загрузил и что DDS Plugin успел увидеть. Поэтому для сохранения старой истории нужно открыть нужный канал или тему и пролистать интересующий диапазон сообщений.

Архив хранится локально. Сеть, GitHub, обновления и медиакэш не являются обязательными для чтения уже собранного архива.

## Быстрая установка

### 1. Установите Discord

Если Discord уже установлен — переходите к следующему шагу.

Официальная загрузка: [discord.com/download](https://discord.com/download)

### 2. Установите BetterDiscord

1. Скачайте BetterDiscord с официального сайта: [betterdiscord.app](https://betterdiscord.app/).
2. Запустите установщик.
3. Выберите **Install BetterDiscord**.
4. Выберите установленный Discord.
5. После завершения установки запустите или перезапустите Discord.

После успешной установки в настройках Discord появится раздел **BetterDiscord**.

### 3. Установите DDS Plugin

Текущая рекомендуемая версия плагина: **DDS Plugin 0.5.3**.

**[Скачать DDS.plugin.js](https://github.com/Mr-Dexter-Morgan/DDS_BD_Plugin/releases/download/v0.5.3/DDS.plugin.js)**  
[Страница релиза DDS Plugin 0.5.3](https://github.com/Mr-Dexter-Morgan/DDS_BD_Plugin/releases/tag/v0.5.3)

После загрузки:

1. Откройте Discord.
2. Перейдите в **Настройки пользователя → BetterDiscord → Plugins**.
3. Нажмите **Open Plugins Folder**.
4. Скопируйте туда файл `DDS.plugin.js`.
5. Вернитесь в список Plugins и включите **DDS**.

После включения плагин начинает сохранять захваченные Discord-данные в:

`%APPDATA%\BetterDiscord\DDS_Data`

### 4. Скачайте DDS Companion

Нажмите большую кнопку **СКАЧАТЬ DDS 0.7.1** в самом верху этой страницы.

Или откройте [релиз DDS Companion 0.7.1](https://github.com/Mr-Dexter-Morgan/DDS_Companion/releases/tag/v0.7.1) и скачайте:

`DDS-0.7.1-windows-x64.zip`

**Не скачивайте** автоматически созданные GitHub-файлы **Source code (zip)** или **Source code (tar.gz)**, если вам нужно просто запустить программу. Это исходный код для разработчиков.

### 5. Запустите DDS

1. Полностью распакуйте `DDS-0.7.1-windows-x64.zip` в отдельную папку.
2. Не вытаскивайте из сборки один `DDS.exe` отдельно — оставьте содержимое архива вместе.
3. Запустите **`DDS.exe`**.

Python для готовой Windows-сборки **не нужен**.

DDS Companion использует capture-файлы, созданные плагином, и переносит принятые данные в локальный архив.

## Как пользоваться

Обычный сценарий пока выглядит так:

1. Запустите Discord и убедитесь, что **DDS Plugin включён**.
2. Открывайте нужные серверы, каналы и темы. Если нужно сохранить старую историю — пролистывайте её, чтобы Discord реально загрузил сообщения.
3. Запустите **DDS.exe**.
4. Companion будет подхватывать новые capture-файлы и добавлять их в локальный архив.
5. Во вкладке **Библиотека** можно просматривать сохранённые серверы, каналы, темы и сообщения.
6. Во вкладке **Статус** можно проверить состояние основных подсистем и жизненный цикл медиа.
7. В **Настройках** можно управлять локальным хранением и автоматической загрузкой медиа.
8. В Библиотеке выбранную ветку можно упаковать через **Упаковать → Только текст** или **Упаковать → Текст + кэш**.

Можно одновременно держать Discord и DDS открытыми: плагин продолжает создавать capture-файлы, а Companion импортирует новые данные в архив.

<details>
<summary><strong>Где DDS хранит данные</strong></summary>

### DDS Plugin

Исходные capture-файлы:

`%APPDATA%\BetterDiscord\DDS_Data`

### DDS Companion

В обычном Installed-профиле постоянные данные Companion находятся под:

`%LOCALAPPDATA%\DDS_Companion`

SQLite-архив является основным долговечным хранилищем. Скачанные медиа — отдельный заменяемый кэш, а созданные ZIP-экспорты — производные файлы.

</details>

> **Важно:** DDS пока находится на линии **0.x / Public Preview**. Мы уже используем его как рабочий локальный архив, но установка, Repair и полный Setup ещё не доведены до будущего пользовательского установщика.

---

Ниже находится техническая информация о текущей версии, архитектуре, сборке и валидации.

## What 0.7.1 includes

- Separate DDSUpdater.exe; the running application never overwrites itself.
- Stable DDS.exe bootstrap and versioned application payloads under versions/<version>.
- Release-manifest contract with SHA-256, exact package size, updater protocol and package format.
- Staging and ZIP validation before promotion, including traversal/symlink/Windows collision/protected-data rejection.
- Transactional current.json / previous.json / pending_update.json pointers.
- Startup acknowledgement and automatic rollback when the candidate cannot prove core runtime readiness.
- Power-loss recovery, orphan-version cleanup and idempotent startup commit.
- Cross-process update lock, free-space preflight, bounded retries/cancellation, durable journal and updater log.
- Windows process-tree termination so failed PyInstaller candidates cannot strand locked payload files.
- Manual update flow, once-per-day background checks, optional auto-download and opt-in auto-install at natural exit.
- Window/presentation state capture for update restart.
- Single-instance protection: a second DDS launch activates the existing runtime instead of opening another archive process.
- Regression coverage proving user data remains byte-identical across successful update and forced rollback.

## Existing archive/export features

- Manual branch packaging: Text Only or Text + Cache.
- Canonical package contents: manifest.json, content.md, messages.json, media_index.json and optional media/.
- Honest incomplete-package reporting when media is unavailable.
- Branch-scoped cache clear, data deletion and full local branch deletion.
- Persistent export destination.
- Windows Known Folder support for redirected Documents.
- Public branding for DDS — Discord Data Snatcher.

## Architecture

DDS is deliberately layered:

Discord Desktop -> BetterDiscord -> DDS Plugin -> local capture files -> DDS Companion -> SQLite archive -> media cache / ZIP export

Updater ownership is a separate optional layer:

GitHub Release -> verified download -> staging -> DDSUpdater.exe -> versioned app payload -> startup ACK / rollback

The local SQLite archive is the durable source of truth. Media cache, exported ZIPs and update packages are derived/rebuildable layers. Export, network or updater failures must not damage or block archive readability.

BetterDiscord plugin repository: https://github.com/Mr-Dexter-Morgan/DDS_BD_Plugin

## Build from source

Requirements: Python 3.11+; Windows is required for native release binaries.

Run build_windows.bat.

The build pipeline:
- rejects overlapping builds with an OS-backed Windows named mutex before shared build/dist state is touched;
- fails closed if old build/dist files cannot be cleaned after bounded retry;
- regenerates Windows FileVersion/ProductVersion metadata from the current DDS source version;
- builds DDSApp.exe, DDS.exe and DDSUpdater.exe;
- produces the full Windows ZIP, update ZIP, SHA-256 files and update manifest;
- retries bounded transient Windows ZIP-read races and validates completed ZIPs before reporting success.

Expected output:
- dist/DDS/DDS.exe
- dist/DDS/DDSUpdater.exe
- dist/release/DDS-<version>-windows-x64.zip
- dist/release/DDS-<version>-update.zip
- dist/release/DDS-<version>-update.json

## Validation

The 0.7.1 patch line passed the full Windows CI gate on the final development head: three regression passes, compile/version verification, native Windows build, package integrity/SHA verification and artifact upload. Manual pre-release testing also verified the updater/status fixes that motivated 0.7.1.

Detailed historical validation remains in VALIDATION.txt and the 0.7.0 live-test checklist.

## Roadmap

0.7.1 is the current Public Preview release. Next planned layer: 0.8.0 Desktop Lifecycle (tray/autostart). See ROADMAP.md.

## History

Development snapshots from 0.1.0 onward are documented in HISTORY.md.

## License

No open-source license has been granted yet. The repository is public for distribution, inspection and project history.
