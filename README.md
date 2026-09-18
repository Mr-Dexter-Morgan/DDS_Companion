# DDS Companion 0.5.2 — Media Attention Recovery Candidate

Status: **CANDIDATE / 80/80 AUTOMATED PASS / WINDOWS LIVE PENDING**  
Baseline: **0.5.0 — VERIFIED / LIVE TESTED / CURRENT RECOMMENDED**  
Supersedes before promotion: **0.5.1 candidate**  
Date: **2026-09-18**

## What this release is

0.5.2 keeps the 0.5.1 UI/Settings polish and closes a real Windows live finding in the Media Backfill layer: one attachment reached `FAILED_PERMANENT` after a repeated size mismatch and left Media Backfill permanently `LIMITED` without a user-facing recovery path.

This patch turns that terminal media state into an explicit, bounded user workflow instead of an unexplained permanent warning.

## User-facing behavior

On **Статус**, media problems now have a dedicated **Медиафайлы, требующие внимания** surface. For each actionable item DDS shows:
- filename;
- human-readable reason;
- state;
- **Повторить**;
- **Игнорировать**;
- **Подробнее**.

`Игнорировать` is durable and removes the item from the unresolved Media Backfill warning count without deleting messages, attachment metadata or SQLite rows. Ignored items remain visible and can later be retried.

`Повторить` performs one explicit retry even if automatic media download is disabled.

## Size-mismatch hardening

When Discord/CDN returns a complete HTTP payload whose `Content-Length` matches the bytes actually received, but Discord attachment metadata advertises a different expected size, DDS now classifies that as a stable metadata/CDN mismatch after one completed transfer instead of blindly downloading the identical payload up to five times.

The binary is still not accepted into cache automatically: the item becomes user-actionable and the archive continues running.

## Library path usability

The misleading **Открыть папку библиотеки** button is removed from Библиотека. It opened the technical application-data root (`config`, `database`, `logs`, `media`, backups/cache internals), not a human-readable library. Technical folder access remains under **Настройки → Хранилище → Расположение файлов**. The broader Library tree/details redesign remains separate until its UX is finalized.

## Truthful status text

- Media Backfill may be `LIMITED` while archive/capture overall remains `RUNNING`; media failure isolation is preserved.
- The bottom status bar now says **ошибок импорта** instead of the ambiguous `unresolved failures`.
- The former **Последняя ошибка** card is now **Последняя критическая ошибка**; media-file problems live in their own block.

## Safety invariants preserved

1. SQLite messages, DDS JSON and attachment metadata remain durable archive/source-of-truth data.
2. Media binaries remain replaceable cache.
3. Ignore/retry actions never delete archived messages or attachment metadata.
4. One bad media object cannot stop Watcher/import/archive/UI runtime.
5. Existing schema v3 remains additive; 0.5.2 requires no schema rewrite.
6. Internal technical states remain stable; the new durable state is `IGNORED` for explicit user acknowledgement.

## Validation

Automated gate: **81/81 PASS repeated three consecutive runs**.  
`compileall`: PASS.  
CLI version: `DDS Companion 0.5.2` PASS.

Windows live gate is intentionally short and targets only the new media-attention workflow plus normal shutdown.

See:
- `VALIDATION.txt`
- `LIVE_TEST_CHECKLIST_0.5.2.txt`
- `NEXT_PATCH_0.5.2.md`
- `MEDIA_ATTENTION_CONTRACT_0.5.2.md`
- historical `NEXT_PATCH_0.5.1.md` / `UI_CONTRACT.md`
- `MEDIA_BACKFILL_CONTRACT.md`
