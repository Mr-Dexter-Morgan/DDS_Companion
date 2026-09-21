# DDS Companion v0.6.2 — Public Preview

This is the first public binary release of DDS Companion. DDS is still on the 0.x line, so this release is published as a **Public Preview / pre-release**, not as the 1.0 stable product.

## Highlights

- Package any Library thread/channel as **Text Only** or **Text + Cache**.
- Exported ZIPs preserve message hierarchy, authors, timestamps, text, links and attachment identity.
- Cached media is included with stable collision-safe names; unavailable media is declared instead of silently disappearing.
- Clear only a branch's media cache, delete only its archived data, or fully remove the local branch with separate semantics and confirmation.
- Manual export does not change future automatic-export rules.
- Windows default export path now follows the real redirected **Documents** Known Folder.
- Durable failed-capture recovery now normalizes Windows path spellings, preventing stale error records when the same file is seen through equivalent path forms.
- Public branding is consistently `DDS — Discord Data Snatcher`.

## Reliability model

SQLite/local archive remains source-of-truth. Export ZIPs and media cache are derived/rebuildable layers. Failures in export or external storage must not collapse capture/import/archive browsing.

## Validation gate

The GitHub Windows release job must pass before the release is created:

- focused Windows regressions for runtime cleanup, Discord probe isolation and failure recovery;
- 121-test suite, three consecutive passes;
- `compileall`;
- CLI version smoke for 0.6.2;
- native Windows PyInstaller onedir build;
- `DDS.exe` file-version check;
- release ZIP integrity check;
- SHA-256 generation.

Interactive Discord/GUI/live-data checks remain separate from CI and continue to be tracked in the included live-test checklist.

## Package

Download `DDS-0.6.2-windows-x64.zip`, extract it completely, then run `DDS.exe`. Keep the onedir folder intact.
