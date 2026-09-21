# DDS — Discord Data Snatcher

**DDS Companion** is the local-first desktop side of DDS. It imports captures produced by the BetterDiscord DDS plugin, stores a durable SQLite archive, keeps a recoverable media cache, lets you browse Discord knowledge locally, and can package selected branches into portable ZIP archives for AI analysis or normal storage.

> **Release line:** 0.x / Public Preview. The archive core and 0.6.2 export workflow are usable, but the updater, tray/autostart and installer layers are still planned before 1.0.

## What 0.6.2 adds

- Manual branch packaging: **Text Only** or **Text + Cache**.
- Canonical package contents: `manifest.json`, `content.md`, `messages.json`, `media_index.json`, and optional `media/`.
- Honest incomplete-package reporting when media is unavailable.
- Branch-scoped cache clear, data deletion, and full local branch deletion.
- Persistent export destination.
- Windows Known Folder support, so a redirected **Documents** folder is respected instead of assuming `C:\Users\<user>\Documents`.
- Branding cleanup for the public `DDS — Discord Data Snatcher` application.
- Repository/runtime icon master normalized to 512 px; displayed app identity is unchanged.

## Architecture

DDS is deliberately layered:

`Discord Desktop -> BetterDiscord -> DDS Plugin -> local capture files -> DDS Companion -> SQLite archive -> media cache / ZIP export`

The local SQLite archive is the durable source of truth. Media cache and exported ZIP files are derived layers. Export or network failures must not damage the archive.

The BetterDiscord plugin lives in the companion repository: [DDS_BD_Plugin](https://github.com/Mr-Dexter-Morgan/DDS_BD_Plugin).

## Windows quick start

1. Install and configure the DDS BetterDiscord plugin.
2. Download the Windows ZIP from the latest GitHub Release.
3. Extract the whole ZIP to a folder.
4. Run `DDS.exe`.

DDS is currently distributed as a **PyInstaller onedir** build, so keep the extracted folder together. A proper Setup/Repair installer is planned later.

## Build from source

Requirements: Python 3.11+; Windows is required for the native release executable.

```bat
build_windows.bat
```

Expected output:

```text
dist\DDS\DDS.exe
```

## Validation

The 0.6.2 release gate runs the full test suite three times, `compileall`, the CLI version smoke, a native Windows PyInstaller build, Windows file-version verification, ZIP integrity verification and SHA-256 generation. Real interactive Discord/GUI behavior remains a separate live-validation layer.

## History

Development snapshots from **0.1.0 through 0.6.2** were reconstructed into chronological Git history from preserved project archives. See [HISTORY.md](HISTORY.md). Every historical version has a Git tag pointing to the corresponding archived source snapshot; `v0.6.2` points to the public-release preparation commit built from candidate-r2.

## License

No open-source license has been granted yet. The repository is public for distribution, inspection and project history.
