# DDS Companion Roadmap

Current public baseline: **v0.8.8 Stable Release / User Accepted**.

## Неподвижные правила архитектуры

- SQLite/local archive остаётся долговечным источником истины.
- Медиакэш, экспортированные ZIP и update-пакеты являются производными слоями.
- BetterDiscord Plugin остаётся лёгким сборщиком; архив, media lifecycle, export, updater и desktop UX принадлежат Companion.
- Сетевые и optional-функции не должны блокировать чтение локального архива.
- Миграции остаются additive/transactional и обязаны быть безопасными при повторном и параллельном startup.
- Обновления не должны повреждать DataRoot, settings, cache, exports или DDS_Data.

## Текущий стабильный baseline — 0.8.8

Выпущено и принято пользователем:

- Home / Library / Status UI baseline.
- SOURCE_GONE lifecycle.
- Manual Re-cache / «Скачать снова».
- Persisted re-cache intent через expired URL → rediscovery.
- Binary-safe Discord process probe.
- SQLite startup/migration race hardening.
- Safe external updater + rollback.
- Single-instance / tray lifecycle.
- Square 16×12 Tetris-style Media Cache.
- Unlimited-cache adaptive display scale.
- Python 3.11 reproducible Windows release pipeline.

## Следующий Companion release

Версия повышается только при реальном изменении Companion.

Перед релизом обязательны:

1. sandbox regression;
2. Windows CI;
3. native Windows build/package verification;
4. live validation, если затронуты GUI, Windows integration, Discord/BetterDiscord или updater;
5. explicit user acceptance;
6. GitHub stable release gate.

## DDS Installer

DDS Installer развивается в отдельном репозитории и по собственной semver-линии. Он не определяет версию Companion.

Его ответственность:
- install / repair;
- shortcuts and ownership;
- preservation of user data;
- uninstall app-owned files only unless data removal explicitly requested.

## DDS 1.0 acceptance gate

Перед продуктовым 1.0:

- migration/backward-compatibility review;
- recovery/corruption-path tests;
- installer + companion + plugin integration gate;
- documentation/release-process review;
- full Windows CI + live acceptance.

## Позже

- автоматический export/sync в выбранную пользователем обычную папку;
- внешняя синхронизация этой папки сторонними клиентами;
- provider-specific OAuth/API не входит в текущий DDS baseline.
