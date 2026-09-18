from __future__ import annotations

import sqlite3


class LibraryService:
    """Read-only structural view used by the GUI Library page.

    The UI never queries archive tables directly. Keeping this boundary means a
    later message-search/index implementation can replace the internals without
    teaching Qt about the SQLite schema.
    """

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def snapshot(self) -> list[dict]:
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
                threads = [
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "message_count": int(row["message_count"]),
                        "media_count": int(row["media_count"]),
                        "last_activity": row["last_activity"],
                    }
                    for row in thread_rows
                ]
                channels.append(
                    {
                        "id": channel["id"],
                        "name": channel["name"],
                        "type": channel["type"],
                        "direct_message_count": int(channel["direct_message_count"]),
                        "message_count": int(channel["message_count"]),
                        "media_count": int(channel["media_count"]),
                        "last_activity": channel["last_activity"],
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
                    "channels": channels,
                }
            )
        return result
