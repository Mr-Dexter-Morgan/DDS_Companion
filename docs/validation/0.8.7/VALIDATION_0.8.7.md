# DDS Companion 0.8.7 — Final Validation

Status: **RELEASED / STABLE / USER ACCEPTED**

## Accepted candidate

- Candidate: `DDS Companion 0.8.7-r2`
- User live acceptance: 2026-10-22
- Accepted source candidate SHA-256: `3070da0a1a3ba7a6ff578af033f0b7e3376f24f5092f00a706154335568f5d44`
- Accepted runtime changes: Home visual hierarchy/icons, 8-state lifecycle dashboard, Library NAVIGATION/VIEWER redesign, consolidated Status page.
- SOURCE_GONE remained integrated with DDS Plugin 0.5.4 and was user-accepted before the 0.8.7 release.

## GitHub promotion

- PR: `#7` — DDS Companion 0.8.7-r2 accepted candidate
- Accepted candidate commit: `f57aa80d89a086bcf1e04d2972f8569879c1d5d5`
- Test-only follow-up commit: `746119bc837a86547c0549696ed89cd546a63235`
- Merge commit: `d9610d6cd1db7158184ba65d8cf207999b162766`
- Release target commit: `0df1244375f9c40aafc3e9f1d4803f317148ecb3`

The only post-live change before merge updated an obsolete UI test expectation from uppercase `КЭШ ОЧИЩЕН` to the accepted r2 label `Кэш очищен`. Runtime/UI code was not changed by that correction.

## Windows CI

- Initial PR CI run `39850029181`: FAIL — one stale test assertion only.
- Corrected PR CI run `39850305855`: PASS.
- Regression suite: PASS.
- Compile/version verification: PASS.
- Native Windows build: PASS.
- Package verification: PASS.
- Artifact upload: PASS.

## Stable release workflow

- Publish run: `39850816081` — PASS.
- Release: https://github.com/Mr-Dexter-Morgan/DDS_Companion/releases/tag/v0.8.7
- Full Windows asset: `DDS-0.8.7-windows-x64.zip`
- Full Windows ZIP SHA-256: `292c2fb0532d155302c0dc32c19f75def77c5bc1d27812003482ba7554305fc0`
- Update ZIP SHA-256: `d107b0a8b17c61ac5ca9a309a75dd32517b6cf05f7cdef0c1515d0643aa3837a`
- Update manifest asset: `DDS-0.8.7-update.json`

## Integration baseline

- Recommended DDS Plugin: `0.5.4`
- Plugin release: https://github.com/Mr-Dexter-Morgan/DDS_BD_Plugin/releases/tag/v0.5.4
- Plugin SHA-256: `3add179053cfb7d1f9b11b4c2ebbf52f8236948fac4aab954479679e6559e87b`

Final result: **PASS / RELEASED / USER ACCEPTED**.
