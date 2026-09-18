# DDS Companion 0.5.2 — Media Attention Recovery

Status: **IMPLEMENTED / CANDIDATE / 81/81 AUTOMATED PASS / WINDOWS LIVE PENDING**  
Date fixed: **2026-09-18**

## Triggering live finding

During the 0.5.1 Windows live pass, one real Discord attachment repeatedly returned:

- metadata expected size: `1304279` bytes;
- actual complete payload: `329666` bytes;
- repeated retries returned the same size;
- item eventually reached `FAILED_PERMANENT`;
- Media Backfill remained `LIMITED` with `failed 1` across restarts;
- the user had no normal UI path to inspect, retry or acknowledge the file.

The archive itself correctly remained operational. The defect was recovery/usability, not archive isolation.

## 0.5.2 contract

### 1. User-actionable media attention surface

On **Статус**, show a dedicated media issue area when terminal/acknowledged media items exist.

For each item show:
- filename;
- human reason;
- state;
- actions **Повторить / Игнорировать / Подробнее**.

The summary must use human wording such as **1 медиафайл требует внимания**.

### 2. Retry

An explicit user retry:
- re-arms only the selected media object;
- resets its bounded retry bookkeeping;
- performs one immediate download attempt even when automatic media download is Off;
- does not queue unrelated media;
- never mutates message/attachment archive rows.

### 3. Ignore

Ignore is a durable acknowledgement:
- selected issue becomes `IGNORED`;
- it no longer holds Media Backfill in `LIMITED`;
- metadata stays intact;
- it remains visible in the media issue list as ignored;
- the user can later select it and **Повторить**;
- a rotating signed URL must not silently undo the explicit Ignore decision.

### 4. Stable size-mismatch classification

If HTTP `Content-Length` equals the bytes fully received but Discord attachment metadata expected a different size, classify the completed transfer as `metadata_size_mismatch` and surface it after one attempt rather than retrying an identical complete payload five times.

Do not silently cache that mismatched payload.

If the response itself appears truncated/incomplete, keep the existing retryable failure behavior.

### 5. Library folder action

Remove the misleading **Открыть папку библиотеки** button from Библиотека. It opened the technical application data root, not a user-facing media/library view. Keep technical folder access in **Настройки -> Хранилище -> Расположение файлов**. Do not fold the still-unfinalized Library tree/details redesign into this patch.

### 6. Truthful labels

- Bottom status wording: **ошибок импорта**, not generic `unresolved failures`.
- Critical runtime/import error card is named **Последняя критическая ошибка**.
- Per-file media issues are shown separately and do not falsely imply archive failure.

## Non-goals

0.5.2 does **not** include the pending Library UX redesign, DataRoot/Portable architecture, tray/autostart, packaging, updater or installer work.

## Automated result

- full suite: **81/81 PASS repeated three consecutive runs**;
- `compileall` PASS;
- CLI version PASS: `DDS Companion 0.5.2`;
- new regression coverage includes:
  - stable complete size mismatch -> terminal attention after one attempt;
  - Ignore removes unresolved media warning but preserves visibility;
  - Ignore survives signed-URL rotation;
  - explicit Retry works with automatic media download disabled;
  - Status exposes Retry / Ignore / Details actions;
  - bottom status wording distinguishes import failures;
  - misleading Library folder button is absent.

## Windows promotion gate

Short live verification only:
1. existing 0.5.1 data root opens unchanged;
2. existing failed attachment appears under media attention with human reason;
3. **Подробнее** shows technical detail without crash;
4. **Повторить** makes one explicit attempt and state updates;
5. **Игнорировать** changes the item to ignored and Media Backfill no longer remains LIMITED solely because of that item;
6. restart preserves ignored acknowledgement;
7. normal close has no traceback.
