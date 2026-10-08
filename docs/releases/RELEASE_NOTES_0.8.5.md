# DDS Companion 0.8.5

Stable release. This is the public promotion of the live-tested local 0.8.5 line.

## What changed since 0.8.0

- Refined DDS branding and made the Updates page user-facing instead of implementation-facing.
- Added the About page with Companion / Plugin / capture-contract identity.
- Added Media Lifecycle reliability fixes and passive stale-link rediscovery behavior.
- Added Network Recovery QoL: human-readable connection failures, Retry All, and slow automatic retry after transient network recovery.
- Reworked Home Media Cache into complete I/O/T/L/J/S/Z tetromino pieces with falling-piece startup animation.
- Preserved the local-first archive model, existing SQLite archive ownership, Desktop Lifecycle, updater rollback model and DDS Plugin 0.5.3 contract.

## Validation

- 0.8.5-r1 sandbox/candidate gate: PASS.
- Windows live gate: PASS.
- Accepted local candidate SHA-256: `bca3633a5d38a254621ee161af6d058de29eb5bf81ad7e8a706e7dc14f358d57`.
- The accepted live visual result includes two non-blocking cosmetic notes: one tetromino can visually appear suspended above the stack, and the startup fall animation is fast.

No archive schema migration. No DDS Plugin change. User data and settings remain outside the replaceable application payload.
