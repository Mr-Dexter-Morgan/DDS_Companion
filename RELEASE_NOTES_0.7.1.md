# DDS Companion 0.7.1

Public Preview patch release built on the 0.7 updater foundation after manual testing.

## Fixed

- **Media-cache race no longer stops DDS.** If cache maintenance removes a media shard while storage statistics are scanning it, the scan skips the vanished entry and continues. The archive runtime is no longer terminated by that normal cache race.
- **Update Status now reflects real checks.** The Status page reads the same persistent updater check-state used by the update engine, so a successful manual check no longer leaves the card at `NEVER`.
- **Correct 24-hour scheduler display.** The update card now reports the actual once-per-24-hours background interval instead of the stale 6-hour fallback.
- **Immediate UI refresh after manual checks.** Check completion requests a fresh runtime snapshot so Status updates without waiting for an unrelated archive event.

## Compatibility

- No archive schema change.
- No DDS Plugin change.
- No user-data migration.
- Existing 0.7.0 `check_state.json` is read backward-compatibly.
- Published after the final Windows CI and manual usability gate passed.
