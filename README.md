# DDS Companion — Discord Data Snatcher

[![Скачать DDS 0.8.8](https://img.shields.io/badge/%D0%A1%D0%9A%D0%90%D0%A7%D0%90%D0%A2%D0%AC_DDS-0.8.8-6C63FF?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/Mr-Dexter-Morgan/DDS_Companion/releases/download/v0.8.8/DDS-0.8.8-windows-x64.zip)

**Current stable:** **DDS Companion 0.8.8** · Windows x64 · User Accepted.

DDS Companion is the durable archive and desktop application of the DDS project. It imports local Plugin captures into SQLite, manages media lifecycle/cache, provides Library/Activity/Health UI and exports selected archive branches to ZIP.

## DDS components

| Component | Current public version | Role |
|---|---|---|
| **DDS Plugin** | **0.5.4 Stable** | Discord/BetterDiscord capture layer |
| **DDS Companion** | **0.8.8 Stable** | SQLite archive, Library, media lifecycle/cache, ZIP export, desktop UI |
| **DDS Installer** | **v0.9.0-rc.1 Preview** | Windows install/repair orchestration |

Repositories:

- Plugin: https://github.com/Mr-Dexter-Morgan/DDS_BD_Plugin
- Companion: https://github.com/Mr-Dexter-Morgan/DDS_Companion
- Installer: https://github.com/Mr-Dexter-Morgan/DDS_Installer

The three components use **independent version numbers**.

## Data flow

```text
Discord Desktop
      ↓
BetterDiscord
      ↓
DDS Plugin
      ↓
%APPDATA%\BetterDiscord\DDS_Data
      ↓
DDS Companion
      ↓
%LOCALAPPDATA%\DDS_Companion
      ↓
SQLite archive → media cache / ZIP export
```

DDS Installer sits beside this path as the setup/repair control plane. It does not own the archive.

## Installation

### Recommended

Use DDS Installer when its current preview scope matches the operation you need:

https://github.com/Mr-Dexter-Morgan/DDS_Installer/releases

### Manual / portable Companion setup

1. Install Discord Desktop and BetterDiscord.
2. Install and enable **DDS Plugin 0.5.4**:
   https://github.com/Mr-Dexter-Morgan/DDS_BD_Plugin/releases/tag/v0.5.4
3. Download **DDS-0.8.8-windows-x64.zip**:
   https://github.com/Mr-Dexter-Morgan/DDS_Companion/releases/tag/v0.8.8
4. Fully extract the ZIP.
5. Start **DDS.exe**.

Keep `DDS.exe`, `DDSUpdater.exe`, `current.json` and `versions/` together.

## Data ownership

Plugin hand-off data:

```text
%APPDATA%\BetterDiscord\DDS_Data
```

Companion durable data:

```text
%LOCALAPPDATA%\DDS_Companion
```

The SQLite archive is the durable source of truth. Media cache and exported ZIP files are derived/rebuildable layers.

## 0.8.8 highlights

- **Скачать снова / Manual Re-cache** for evicted media.
- Persisted re-cache intent through expired Discord URLs until fresh rediscovery.
- Binary-safe Discord process detection on localized Windows.
- Race-safe SQLite startup/migrations.
- Square **16×12 Tetris-style Media Cache**.
- Adaptive visual scale for unlimited media cache.
- Reproducible Windows build on Python 3.11.

Release notes: [docs/releases/RELEASE_NOTES_0.8.8.md](docs/releases/RELEASE_NOTES_0.8.8.md)

## Architecture

[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

Core rule:

```text
Plugin captures → Companion archives/processes → Installer installs/repairs
```

No component should silently take ownership of another component's durable data.

## Build from source

Requirements:

- Windows;
- Python 3.11.

```bat
python -m venv .venv-build
.venv-build\Scripts\python -m pip install -r requirements-build.txt
build_windows.bat
```

GitHub CI validates regression, versioning, native Windows build and release packages.

## Repository layout

```text
dds_companion/             runtime source + tests
assets/                    application resources
DDSApp.spec                application PyInstaller definition
DDSLauncher.spec           stable launcher definition
DDSUpdater.spec            updater definition
run_companion.pyw          application build entrypoint
run_launcher.pyw           launcher build entrypoint
run_updater.py             updater build entrypoint
build_windows.bat
tools/
docs/ARCHITECTURE.md
docs/releases/RELEASE_NOTES_0.8.8.md
.github/workflows/
README.md
ROADMAP.md
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](ROADMAP.md)
- [Release notes 0.8.8](docs/releases/RELEASE_NOTES_0.8.8.md)

## License

No separate open-source license has been granted. Public repository visibility alone does not grant general redistribution rights.
