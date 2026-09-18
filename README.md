# DDS Companion 0.5.3 — Library UX Candidate

Status: **CANDIDATE / AUTOMATED PASS / WINDOWS LIVE PENDING**

0.5.3 is a deliberately small usability patch built on the live-tested 0.5.2 code line. It turns **Библиотека** from a developer-style tree/table into a human archive browser without changing SQLite schema, Watcher, importer or Media Runtime behavior.

## User-facing changes

- tree remains **server → channel → thread**;
- main columns are now **Раздел / Сообщений / Медиа**;
- technical Discord IDs are removed from the main tree;
- selecting a node opens a details panel with type, location, message count, media count, last activity and technical ID;
- technical ID can be copied explicitly from the details panel;
- search wording is now **Поиск по серверу, каналу или теме…**;
- server/channel/thread selection is preserved across refresh when possible;
- if nothing is selected, the details panel shows a clear empty state;
- no user-facing action opens the internal application-data root from Library.

## Scope boundary

No schema migration. No media/downloader change. No Watcher/import redesign. No message full-text search yet.
