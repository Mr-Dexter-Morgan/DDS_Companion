# DDS — Discord Data Snatcher

## DDS Companion 0.6.2 candidate-r1

0.6.2 is the first DDS build with a provider-independent manual export layer. It builds on the Windows-live-tested 0.6.1 local baseline and keeps the local archive as source-of-truth.

### Main changes

- Window title is now exactly `DDS — Discord Data Snatcher`.
- Sidebar branding is simplified: stronger centered `DDS`, then `Discord / Data / Snatcher` on separate lines; version moved out of normal chrome.
- Library context menu adds:
  - `Упаковать -> Только текст`;
  - `Упаковать -> Текст + кэш`;
  - `Очистить медиакэш этой ветки`;
  - `Удалить данные ветки`;
  - `Полностью удалить ветку`.
- Manual export creates validated ZIP packages with:
  - `manifest.json`;
  - `content.md`;
  - `messages.json`;
  - `media_index.json`;
  - optional `media/`.
- Missing media is declared explicitly instead of being silently omitted.
- Manual packaging is independent from Library `Выгружать / Не выгружать` rules and does not mutate them.
- Settings adds a persistent manual-export folder.
- Branch destructive operations are separated by meaning and protected by confirmation/runtime stop where necessary.
- ZIP creation uses staging, archive verification and atomic promotion.
- No Google OAuth/API integration is included. Future automatic external sync will target a normal filesystem folder.

### Reliability contract

SQLite/local archive remains source-of-truth. ZIP and future sync-folder output are derived layers. Export failure must not damage capture/import/archive/media operation. Deleting an exported copy must never delete SQLite archive data.

### Build

Windows onedir build:

```bat
build_windows.bat
```

Expected output:

```text
dist\DDS\DDS.exe
```

### Validation state

- Automated regression suite: source gate required.
- `compileall`: required.
- CLI version smoke: required.
- Windows native build/live validation: still required before 0.6.2 is frozen or published.
- Intended first public GitHub binary Release: `v0.6.2`, only after the live gate passes.
