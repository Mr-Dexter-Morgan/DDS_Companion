# DDS Companion 0.8.7

DDS Companion 0.8.7 is the accepted UI and lifecycle release built from the user-tested 0.8.7-r2 candidate.

## Highlights

- redesigned Home dashboard with clearer visual hierarchy and local SVG icons;
- eight media lifecycle states presented as a balanced 2×4 dashboard;
- separate terminal **Источник удалён / SOURCE_GONE** state;
- cleaner Current Session and Last Activity panels;
- Library redesign with **НАВИГАЦИЯ | ПРОСМОТР** full-width modes;
- Status page consolidated into one diagnostic view;
- media loading summary and attention items moved into Status;
- SOURCE_GONE, EVICTED, retry blocking, and cache semantics preserved.

## Validation

- user live acceptance: PASS on 2026-10-22;
- Windows CI regression suite: PASS;
- native Windows build: PASS;
- release package verification: PASS;
- SOURCE_GONE live validation: PASS;
- Plugin 0.5.4 integration: PASS.

## Compatibility

Recommended companion plugin: DDS Plugin 0.5.4 or newer.
