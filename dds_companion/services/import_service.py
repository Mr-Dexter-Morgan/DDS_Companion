from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from dds_companion.parser.capture_parser import ParsedCapture, parse_capture
from dds_companion.parser.normalizer import json_text, normalize_context
from dds_companion.services.media_registry_service import MediaRegistryService


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ImportResult:
    files_seen: int = 0
    imported: int = 0
    skipped_unchanged: int = 0
    failed: int = 0
    messages_inserted: int = 0
    messages_updated: int = 0
    attachments_registered: int = 0
    embeds_registered: int = 0

    def merge(self, other: "ImportResult") -> None:
        for field in self.__dataclass_fields__:
            setattr(self, field, getattr(self, field) + getattr(other, field))


class ImportService:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.media_registry = MediaRegistryService(connection)

    def discover_capture_files(self, dds_data_root: str | Path) -> Iterable[Path]:
        root = Path(dds_data_root)
        guilds = root / "guilds"
        if not guilds.is_dir():
            return []
        return sorted(guilds.glob("**/capture.json"))

    def import_all(self, dds_data_root: str | Path) -> ImportResult:
        result = ImportResult()
        for path in self.discover_capture_files(dds_data_root):
            result.files_seen += 1
            try:
                result.merge(self.import_file(path))
            except Exception as exc:  # isolation is intentional: one bad capture must not stop the scan
                result.failed += 1
                self.record_failure("capture_import", str(path), exc)
        return result

    def import_file(self, path: str | Path) -> ImportResult:
        parsed = parse_capture(path)
        if self._already_imported(parsed):
            return ImportResult(skipped_unchanged=1)

        capture = parsed.data
        context = normalize_context(capture)
        now = utc_now()
        captured_at = capture.get("capturedAt") or now

        inserted = updated = attachments = embeds = 0

        try:
            with self.connection:
                account = capture.get("account")
                if account and account.get("id"):
                    self.connection.execute(
                        """
                        INSERT INTO accounts(id, username, global_name, last_seen_at)
                        VALUES(?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            username=excluded.username,
                            global_name=excluded.global_name,
                            last_seen_at=excluded.last_seen_at
                        """,
                        (str(account["id"]), account.get("username"), account.get("globalName"), captured_at),
                    )

                self.connection.execute(
                    """
                    INSERT INTO guilds(id, name, last_seen_at) VALUES(?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET name=excluded.name, last_seen_at=excluded.last_seen_at
                    """,
                    (context.guild_id, context.guild_name, captured_at),
                )

                self.connection.execute(
                    """
                    INSERT INTO channels(id, guild_id, name, type, last_seen_at)
                    VALUES(?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        guild_id=excluded.guild_id,
                        name=COALESCE(excluded.name, channels.name),
                        type=COALESCE(excluded.type, channels.type),
                        last_seen_at=excluded.last_seen_at
                    """,
                    (
                        context.parent_channel_id,
                        context.guild_id,
                        context.parent_channel_name,
                        context.parent_channel_type,
                        captured_at,
                    ),
                )

                if context.thread_id:
                    self.connection.execute(
                        """
                        INSERT INTO threads(id, guild_id, parent_channel_id, name, last_seen_at)
                        VALUES(?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            guild_id=excluded.guild_id,
                            parent_channel_id=excluded.parent_channel_id,
                            name=COALESCE(excluded.name, threads.name),
                            last_seen_at=excluded.last_seen_at
                        """,
                        (
                            context.thread_id,
                            context.guild_id,
                            context.parent_channel_id,
                            context.thread_name,
                            captured_at,
                        ),
                    )

                for message in capture.get("messages", []):
                    message_id = str(message["id"])
                    author = message.get("author")
                    author_id = None
                    if author and author.get("id"):
                        author_id = str(author["id"])
                        self.connection.execute(
                            """
                            INSERT INTO users(id, username, global_name, display_name, bot, last_seen_at)
                            VALUES(?, ?, ?, ?, ?, ?)
                            ON CONFLICT(id) DO UPDATE SET
                                username=excluded.username,
                                global_name=excluded.global_name,
                                display_name=excluded.display_name,
                                bot=excluded.bot,
                                last_seen_at=excluded.last_seen_at
                            """,
                            (
                                author_id,
                                author.get("username"),
                                author.get("globalName"),
                                author.get("displayName"),
                                int(bool(author.get("bot"))),
                                captured_at,
                            ),
                        )

                    existed = self.connection.execute(
                        "SELECT 1 FROM messages WHERE id=?", (message_id,)
                    ).fetchone() is not None

                    self.connection.execute(
                        """
                        INSERT INTO messages(
                            id, guild_id, source_channel_id, parent_channel_id, thread_id, author_id,
                            type, timestamp, edited_timestamp, content, pinned, tts,
                            first_seen_at, last_seen_at, last_capture_revision
                        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            guild_id=excluded.guild_id,
                            source_channel_id=excluded.source_channel_id,
                            parent_channel_id=excluded.parent_channel_id,
                            thread_id=excluded.thread_id,
                            author_id=excluded.author_id,
                            type=excluded.type,
                            timestamp=excluded.timestamp,
                            edited_timestamp=excluded.edited_timestamp,
                            content=excluded.content,
                            pinned=excluded.pinned,
                            tts=excluded.tts,
                            last_seen_at=excluded.last_seen_at,
                            last_capture_revision=excluded.last_capture_revision
                        """,
                        (
                            message_id,
                            context.guild_id,
                            str(message.get("channelId") or context.effective_channel_id),
                            context.parent_channel_id,
                            context.thread_id,
                            author_id,
                            message.get("type"),
                            message.get("timestamp"),
                            message.get("editedTimestamp"),
                            message.get("content") or "",
                            int(bool(message.get("pinned"))),
                            int(bool(message.get("tts"))),
                            captured_at,
                            captured_at,
                            capture.get("captureRevision"),
                        ),
                    )
                    if existed:
                        updated += 1
                    else:
                        inserted += 1

                    self.media_registry.remove_refs_for_message(message_id)
                    self.connection.execute("DELETE FROM attachments WHERE message_id=?", (message_id,))
                    for position, attachment in enumerate(message.get("attachments") or []):
                        if attachment is None:
                            continue
                        self.connection.execute(
                            """
                            INSERT INTO attachments(
                                message_id, position, attachment_id, filename, title, description,
                                content_type, size, url, proxy_url, width, height, ephemeral
                            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                message_id,
                                position,
                                str(attachment["id"]) if attachment.get("id") is not None else None,
                                attachment.get("filename"),
                                attachment.get("title"),
                                attachment.get("description"),
                                attachment.get("contentType"),
                                attachment.get("size"),
                                attachment.get("url"),
                                attachment.get("proxyUrl"),
                                attachment.get("width"),
                                attachment.get("height"),
                                int(bool(attachment.get("ephemeral"))),
                            ),
                        )
                        self.media_registry.register_attachment(
                            message_id=message_id,
                            position=position,
                            attachment=attachment,
                            observed_at=captured_at,
                        )
                        attachments += 1

                    self.connection.execute("DELETE FROM embeds WHERE message_id=?", (message_id,))
                    for position, embed in enumerate(message.get("embeds") or []):
                        if embed is None:
                            continue
                        self.connection.execute(
                            """
                            INSERT INTO embeds(
                                message_id, position, type, url, title, description, timestamp, color,
                                provider_json, author_json, thumbnail_json, image_json, fields_json, footer_json
                            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                message_id,
                                position,
                                embed.get("type"),
                                embed.get("url"),
                                embed.get("title"),
                                embed.get("description"),
                                embed.get("timestamp"),
                                embed.get("color"),
                                json_text(embed.get("provider")),
                                json_text(embed.get("author")),
                                json_text(embed.get("thumbnail")),
                                json_text(embed.get("image")),
                                json_text(embed.get("fields")),
                                json_text(embed.get("footer")),
                            ),
                        )
                        embeds += 1

                    reference = message.get("messageReference")
                    if reference:
                        self.connection.execute(
                            """
                            INSERT INTO message_references(
                                message_id, referenced_message_id, referenced_channel_id, referenced_guild_id
                            ) VALUES(?, ?, ?, ?)
                            ON CONFLICT(message_id) DO UPDATE SET
                                referenced_message_id=excluded.referenced_message_id,
                                referenced_channel_id=excluded.referenced_channel_id,
                                referenced_guild_id=excluded.referenced_guild_id
                            """,
                            (
                                message_id,
                                str(reference["messageId"]) if reference.get("messageId") is not None else None,
                                str(reference["channelId"]) if reference.get("channelId") is not None else None,
                                str(reference["guildId"]) if reference.get("guildId") is not None else None,
                            ),
                        )
                    else:
                        self.connection.execute("DELETE FROM message_references WHERE message_id=?", (message_id,))

                self.connection.execute(
                    """
                    INSERT INTO capture_imports(
                        capture_path, sha256, captured_at, imported_at, dds_version, schema_version,
                        capture_revision, guild_id, parent_channel_id, thread_id, message_count,
                        file_size_bytes, status, detail
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'imported', NULL)
                    """,
                    (
                        str(parsed.path.resolve()),
                        parsed.sha256,
                        capture.get("capturedAt"),
                        now,
                        capture.get("ddsVersion"),
                        capture.get("schemaVersion"),
                        capture.get("captureRevision"),
                        context.guild_id,
                        context.parent_channel_id,
                        context.thread_id,
                        len(capture.get("messages") or []),
                        parsed.size_bytes,
                    ),
                )

                self._set_state("last_successful_import", now)
                self._resolve_failures_for_target(str(parsed.path.resolve()), now)

        except Exception:
            raise

        return ImportResult(
            imported=1,
            messages_inserted=inserted,
            messages_updated=updated,
            attachments_registered=attachments,
            embeds_registered=embeds,
        )

    def _already_imported(self, parsed: ParsedCapture) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM capture_imports WHERE capture_path=? AND sha256=? AND status='imported'",
            (str(parsed.path.resolve()), parsed.sha256),
        ).fetchone() is not None

    def _set_state(self, key: str, value: str) -> None:
        self.connection.execute(
            """
            INSERT INTO application_state(key, value, updated_at) VALUES(?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (key, value, utc_now()),
        )

    def _resolve_failures_for_target(self, target: str, resolved_at: str | None = None) -> None:
        stamp = resolved_at or utc_now()
        self.connection.execute(
            "UPDATE failed_jobs SET resolved_at=? WHERE target=? AND resolved_at IS NULL",
            (stamp, target),
        )
        unresolved = self.connection.execute(
            "SELECT COUNT(*) FROM failed_jobs WHERE resolved_at IS NULL"
        ).fetchone()[0]
        if unresolved == 0:
            self.connection.execute(
                "DELETE FROM application_state WHERE key='last_error'"
            )

    def record_failure(self, job_kind: str, target: str, exc: Exception) -> None:
        error_type = type(exc).__name__
        error_message = str(exc)
        with self.connection:
            duplicate = self.connection.execute(
                """
                SELECT 1 FROM failed_jobs
                WHERE job_kind=? AND target=? AND error_type=? AND error_message=?
                  AND resolved_at IS NULL
                LIMIT 1
                """,
                (job_kind, target, error_type, error_message),
            ).fetchone()
            if duplicate is None:
                self.connection.execute(
                    """
                    INSERT INTO failed_jobs(job_kind, target, error_type, error_message, created_at)
                    VALUES(?, ?, ?, ?, ?)
                    """,
                    (job_kind, target, error_type, error_message, utc_now()),
                )
            self._set_state("last_error", f"{error_type}: {error_message}")
