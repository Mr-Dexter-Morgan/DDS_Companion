# DDS Companion 0.5.2 — Media Attention Contract

## Principle

A failed media object is not an archive failure. DDS must keep the archive usable, explain the media problem, and give the user a bounded action.

## Actionable states

The Status media issue surface includes:
- `FAILED_PERMANENT` — requires attention;
- `STALE_URL` — requires attention;
- `IGNORED` — acknowledged by the user and no longer unresolved.

Transient `FAILED_RETRYABLE` remains automatic runtime behavior and is not treated as a persistent user-attention item until it becomes terminal.

## Retry contract

`Повторить` applies only to the selected media key. It resets retry bookkeeping and performs one immediate bounded download attempt. It does not enable global automatic media download and does not enqueue unrelated objects.

## Ignore contract

`Игнорировать` is durable, reversible through `Повторить`, and archive-safe. It changes only media lifecycle state. It never deletes the corresponding message, attachment metadata, media reference or SQLite archive data.

A later signed-URL refresh does not automatically undo `IGNORED`.

## Stable metadata mismatch

A fully received HTTP response with self-consistent `Content-Length` but a different Discord metadata size is not retried repeatedly as if it were a random network truncation. DDS records `metadata_size_mismatch`, does not promote the binary into cache, and asks for user attention.

## Health semantics

- Media Backfill can be `LIMITED` while Overall archive/capture health remains `RUNNING`.
- Ignored media is counted separately and does not keep Media Backfill `LIMITED`.
- Human UI wording and technical states are separate: technical identifiers remain stable for diagnostics.
