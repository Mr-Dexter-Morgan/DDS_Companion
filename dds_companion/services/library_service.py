from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


class LibraryService:
    """Archive navigation, message paging and future-export selection rules.

    The GUI never queries SQLite directly. Structural navigation, message pages and
    Drive-selection markers all pass through this service so Qt stays unaware of the
    archive schema and a future synchronizer can reuse the exact same rule resolver.
    """

    VALID_SCOPE_KINDS = {"guild", "channel", "thread"}
    VALID_EXPORT_MODES = {"DEFAULT", "INCLUDE", "EXCLUDE"}
    DEFAULT_EFFECTIVE_MODE = "EXCLUDE"

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def snapshot(self) -> list[dict]:
        rules = self._export_rules()
        guild_rows = self.connection.execute(
            """
            SELECT g.id,
                   COALESCE(NULLIF(g.name, ''), g.id) AS name,
                   COUNT(DISTINCT m.id) AS message_count,
                   COUNT(a.message_id) AS media_count,
                   MAX(m.timestamp) AS last_activity
            FROM guilds g
            LEFT JOIN messages m ON m.guild_id = g.id
            LEFT JOIN attachments a ON a.message_id = m.id
            GROUP BY g.id, g.name
            ORDER BY name COLLATE NOCASE, g.id
            """
        ).fetchall()

        result: list[dict] = []
        for guild in guild_rows:
            guild_rule = rules.get(("guild", guild["id"]), "DEFAULT")
            guild_effective = self._resolve_mode(guild_rule, self.DEFAULT_EFFECTIVE_MODE)
            channel_rows = self.connection.execute(
                """
                SELECT c.id,
                       COALESCE(NULLIF(c.name, ''), c.id) AS name,
                       c.type,
                       COUNT(DISTINCT CASE WHEN m.thread_id IS NULL THEN m.id END) AS direct_message_count,
                       COUNT(DISTINCT m.id) AS message_count,
                       COUNT(a.message_id) AS media_count,
                       MAX(m.timestamp) AS last_activity
                FROM channels c
                LEFT JOIN messages m ON m.parent_channel_id = c.id
                LEFT JOIN attachments a ON a.message_id = m.id
                WHERE c.guild_id = ?
                GROUP BY c.id, c.name, c.type
                ORDER BY name COLLATE NOCASE, c.id
                """,
                (guild["id"],),
            ).fetchall()

            channels: list[dict] = []
            for channel in channel_rows:
                channel_rule = rules.get(("channel", channel["id"]), "DEFAULT")
                channel_effective = self._resolve_mode(channel_rule, guild_effective)
                thread_rows = self.connection.execute(
                    """
                    SELECT t.id,
                           COALESCE(NULLIF(t.name, ''), t.id) AS name,
                           COUNT(DISTINCT m.id) AS message_count,
                           COUNT(a.message_id) AS media_count,
                           MAX(m.timestamp) AS last_activity
                    FROM threads t
                    LEFT JOIN messages m ON m.thread_id = t.id
                    LEFT JOIN attachments a ON a.message_id = m.id
                    WHERE t.guild_id = ? AND t.parent_channel_id = ?
                    GROUP BY t.id, t.name
                    ORDER BY name COLLATE NOCASE, t.id
                    """,
                    (guild["id"], channel["id"]),
                ).fetchall()
                threads = []
                for row in thread_rows:
                    thread_rule = rules.get(("thread", row["id"]), "DEFAULT")
                    thread_effective = self._resolve_mode(thread_rule, channel_effective)
                    threads.append(
                        {
                            "id": row["id"],
                            "name": row["name"],
                            "message_count": int(row["message_count"]),
                            "media_count": int(row["media_count"]),
                            "last_activity": row["last_activity"],
                            "export_rule": thread_rule,
                            "default_export_rule": channel_effective,
                            "effective_export_rule": thread_effective,
                        }
                    )
                channels.append(
                    {
                        "id": channel["id"],
                        "name": channel["name"],
                        "type": channel["type"],
                        "direct_message_count": int(channel["direct_message_count"]),
                        "message_count": int(channel["message_count"]),
                        "media_count": int(channel["media_count"]),
                        "last_activity": channel["last_activity"],
                        "export_rule": channel_rule,
                        "default_export_rule": guild_effective,
                        "effective_export_rule": channel_effective,
                        "threads": threads,
                    }
                )

            result.append(
                {
                    "id": guild["id"],
                    "name": guild["name"],
                    "message_count": int(guild["message_count"]),
                    "media_count": int(guild["media_count"]),
                    "last_activity": guild["last_activity"],
                    "export_rule": guild_rule,
                    "default_export_rule": self.DEFAULT_EFFECTIVE_MODE,
                    "effective_export_rule": guild_effective,
                    "channels": channels,
                }
            )
        return result

    def set_export_rule(self, scope_kind: str, scope_id: str, mode: str) -> None:
        scope_kind = str(scope_kind or "").strip().lower()
        scope_id = str(scope_id or "").strip()
        mode = str(mode or "").strip().upper()
        if scope_kind not in self.VALID_SCOPE_KINDS:
            raise ValueError(f"unsupported export scope: {scope_kind}")
        if not scope_id:
            raise ValueError("export scope id is empty")
        if mode not in self.VALID_EXPORT_MODES:
            raise ValueError(f"unsupported export mode: {mode}")

        if mode == "DEFAULT":
            self.connection.execute(
                "DELETE FROM archive_export_rules WHERE scope_kind=? AND scope_id=?",
                (scope_kind, scope_id),
            )
        else:
            now = datetime.now(timezone.utc).isoformat()
            self.connection.execute(
                """
                INSERT INTO archive_export_rules(scope_kind, scope_id, mode, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(scope_kind, scope_id)
                DO UPDATE SET mode=excluded.mode, updated_at=excluded.updated_at
                """,
                (scope_kind, scope_id, mode, now),
            )
        self.connection.commit()

    def message_page(
        self,
        scope_kind: str,
        scope_id: str,
        *,
        limit: int = 50,
        before_timestamp: str | None = None,
        before_id: str | None = None,
    ) -> dict:
        """Return one chronological page of messages for a channel or thread.

        Pages are fetched newest-first in SQL, then reversed for Discord-like
        chronological display. A cursor requests older messages in batches of 50.
        Channel pages intentionally contain only direct channel messages; thread
        messages stay inside their own tree node instead of being duplicated.
        """
        scope_kind = str(scope_kind or "").strip().lower()
        scope_id = str(scope_id or "").strip()
        if scope_kind not in {"channel", "thread"}:
            return {"messages": [], "has_more": False, "oldest_timestamp": None, "oldest_id": None}
        if not scope_id:
            raise ValueError("message scope id is empty")
        limit = max(1, min(200, int(limit)))

        if scope_kind == "thread":
            where = "m.thread_id = ?"
        else:
            where = "m.parent_channel_id = ? AND m.thread_id IS NULL"
        params: list[object] = [scope_id]
        sort_expr = "COALESCE(m.timestamp, m.first_seen_at, '')"
        if before_timestamp is not None and before_id is not None:
            where += f" AND ({sort_expr} < ? OR ({sort_expr} = ? AND m.id < ?))"
            params.extend([before_timestamp, before_timestamp, before_id])
        params.append(limit + 1)

        rows = self.connection.execute(
            f"""
            SELECT m.id,
                   m.timestamp,
                   m.edited_timestamp,
                   m.content,
                   m.author_id,
                   {sort_expr} AS sort_time,
                   COALESCE(NULLIF(u.display_name, ''), NULLIF(u.global_name, ''),
                            NULLIF(u.username, ''), m.author_id, 'Неизвестный автор') AS author_name
            FROM messages m
            LEFT JOIN users u ON u.id = m.author_id
            WHERE {where}
            ORDER BY {sort_expr} DESC, m.id DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()

        has_more = len(rows) > limit
        selected = list(rows[:limit])
        selected.reverse()
        message_ids = [row["id"] for row in selected]
        attachments = self._attachments_for(message_ids)
        embeds = self._embeds_for(message_ids)

        messages = []
        for row in selected:
            messages.append(
                {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "sort_time": row["sort_time"],
                    "edited_timestamp": row["edited_timestamp"],
                    "author_id": row["author_id"],
                    "author_name": row["author_name"],
                    "content": row["content"] or "",
                    "attachments": attachments.get(row["id"], []),
                    "embeds": embeds.get(row["id"], []),
                }
            )

        oldest = messages[0] if messages else None
        return {
            "messages": messages,
            "has_more": has_more,
            "oldest_timestamp": oldest.get("sort_time") if oldest else None,
            "oldest_id": oldest.get("id") if oldest else None,
        }

    def _export_rules(self) -> dict[tuple[str, str], str]:
        rows = self.connection.execute(
            "SELECT scope_kind, scope_id, mode FROM archive_export_rules"
        ).fetchall()
        return {(str(row["scope_kind"]), str(row["scope_id"])): str(row["mode"]) for row in rows}

    @staticmethod
    def _resolve_mode(explicit: str, inherited: str) -> str:
        return inherited if explicit == "DEFAULT" else explicit

    def _attachments_for(self, message_ids: list[str]) -> dict[str, list[dict]]:
        if not message_ids:
            return {}
        placeholders = ",".join("?" for _ in message_ids)
        rows = self.connection.execute(
            f"""
            SELECT a.message_id, a.position, a.attachment_id, a.filename, a.title,
                   a.description, a.content_type, a.size, a.width, a.height,
                   mr.media_key, mo.state AS media_state, mo.local_relpath,
                   mo.local_size
            FROM attachments a
            LEFT JOIN media_refs mr
                   ON mr.message_id=a.message_id AND mr.position=a.position
            LEFT JOIN media_objects mo ON mo.media_key=mr.media_key
            WHERE a.message_id IN ({placeholders})
            ORDER BY a.message_id, a.position
            """,
            tuple(message_ids),
        ).fetchall()
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            grouped.setdefault(row["message_id"], []).append(
                {
                    "position": int(row["position"]),
                    "attachment_id": row["attachment_id"],
                    "filename": row["filename"] or row["title"] or "Вложение",
                    "description": row["description"],
                    "content_type": row["content_type"],
                    "size": row["size"],
                    "width": row["width"],
                    "height": row["height"],
                    "media_key": row["media_key"],
                    "media_state": row["media_state"] or "KNOWN",
                    "local_relpath": row["local_relpath"],
                    "local_size": row["local_size"],
                }
            )
        return grouped

    def _embeds_for(self, message_ids: list[str]) -> dict[str, list[dict]]:
        if not message_ids:
            return {}
        placeholders = ",".join("?" for _ in message_ids)
        rows = self.connection.execute(
            f"""
            SELECT message_id, position, type, title, description, url,
                   thumbnail_json, image_json
            FROM embeds
            WHERE message_id IN ({placeholders})
            ORDER BY message_id, position
            """,
            tuple(message_ids),
        ).fetchall()
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            image_url = None
            for raw in (row["image_json"], row["thumbnail_json"]):
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                    if isinstance(payload, dict) and payload.get("url"):
                        image_url = str(payload["url"])
                        break
                except (TypeError, ValueError, json.JSONDecodeError):
                    pass
            grouped.setdefault(row["message_id"], []).append(
                {
                    "position": int(row["position"]),
                    "type": row["type"],
                    "title": row["title"],
                    "description": row["description"],
                    "url": row["url"],
                    "image_url": image_url,
                }
            )
        return grouped
