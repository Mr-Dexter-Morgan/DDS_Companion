# DDS Companion 0.8.6 — release state

Recorded: 2026-10-22.
Result: **PARTIAL / NEEDS FIX** (live integration acceptance still pending).
State: SOURCE PATCH CANDIDATE / AUTOMATED TARGETED PASS / NOT RELEASED.
Linked component: DDS Plugin 0.5.4 candidate.

The SOURCE_GONE lifecycle implementation and test evidence are complete locally.
Native Discord HTTP/dispatcher adapter and the real historical six-file case have
not been checked on Windows. Therefore this is not a full product/live PASS.
No Windows 0.8.6 EXE was built and no GitHub push/tag/Release was performed.
Accepted 0.8.5 and Plugin 0.5.3 baselines remain unchanged.

Full regression has one environment-blocked IPC test also failing on unchanged
0.8.5. AF_UNIX socket creation is denied with EPERM in this sandbox. All remaining
regressions and target tests pass; details are in VALIDATION_0.8.6.md.
An exploratory wheel build also fails identically on baseline (multiple top-level
packages); the established product build is Windows PyInstaller, not wheel packaging.
These pre-existing issues were recorded without unrelated fixes.
