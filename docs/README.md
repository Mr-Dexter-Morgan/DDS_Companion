# DDS Companion — Documentation

This directory keeps historical documentation out of the repository root without deleting release evidence.

## Current information
- [README / download](../README.md) — product, installation and current Stable Release.
- [ROADMAP](../ROADMAP.md) — current engineering direction and release gates.

## Release history
- [Release notes 0.8.5](releases/RELEASE_NOTES_0.8.5.md) — current Stable Release.
- [Release notes 0.8.0](releases/RELEASE_NOTES_0.8.0.md) — previous Stable Release.
- [Release notes 0.7.1](releases/RELEASE_NOTES_0.7.1.md) — historical Public Preview.
- [Release notes 0.7.0](releases/RELEASE_NOTES_0.7.0.md) — frozen, not published as a standalone Release.
- [Release notes 0.6.2](releases/RELEASE_NOTES_0.6.2.md) — first public Windows binary release.

## Validation evidence
- [0.7.0 final validation](validation/0.7.0/VALIDATION.txt).
- [0.7.0 Windows live checklist](validation/0.7.0/LIVE_TEST_CHECKLIST.txt).
- [0.6.2 Windows live checklist](validation/0.6.2/LIVE_TEST_CHECKLIST.txt).

## History
- [Release chronology](history/HISTORY.md).
- [Engineering changelog](history/CHANGELOG.txt).

## Working-file rules
- The GitHub release workflow reads `docs/releases/RELEASE_NOTES_<version>.md`.
- `build_windows.bat`, PyInstaller specs and dependency files remain at the repository root because active Windows build commands reference them.
- Historical documentation is preserved and moved, not rewritten to represent a different past.
