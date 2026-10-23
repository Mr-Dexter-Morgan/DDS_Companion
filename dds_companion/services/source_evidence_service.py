"""Persist positive Discord channel deletion evidence; never infer from absence.

Protocol constants below are named Discord API channel/audit-log enum values.
A missing ChannelStore entry, HTTP error, or missing audit entry is not evidence.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

GUILD_VOICE = 2
GUILD_STAGE_VOICE = 13
CHANNEL_DELETE = 12
SUPPORTED_CHANNEL_TYPES = frozenset({GUILD_VOICE, GUILD_STAGE_VOICE})
DISCORD_EPOCH_MS = 1420070400000


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp requires timezone")
    return result.astimezone(timezone.utc)


def usable_capture_url(url: str | None) -> bool:
    try:
        parsed = urlsplit(url or "")
        if parsed.scheme != "https" or parsed.hostname not in {"cdn.discordapp.com", "media.discordapp.net"}:
            return False
        if not parsed.path.startswith("/attachments/") or parsed.username or parsed.password:
            return False
        expiry = parse_qs(parsed.query).get("ex")
        return not expiry or int(expiry[0], 16) > datetime.now(timezone.utc).timestamp()
    except (ValueError, TypeError, OverflowError):
        return False


class SourceEvidenceService:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def import_file(self, path: Path) -> bool:
        # Keep this envelope separate from immutable message captures.
        if path.stat().st_size > 64 * 1024:
            raise ValueError("source evidence exceeds 64 KiB")
        data = json.loads(path.read_text(encoding="utf-8"))
        guild, channel = data.get("guildId"), data.get("channelId")
        if not all(isinstance(v, str) and v.isdecimal() and 0 < len(v) <= 20 for v in (guild, channel)):
            raise ValueError("source evidence requires Discord guild/channel IDs")
        if path.parts[-5:] != ("guilds", guild, "channels", channel, "source_evidence.json"):
            raise ValueError("source evidence path/identity mismatch")
        channel_type = data.get("channelType")
        if (data.get("schemaVersion") != 1 or data.get("availability") != "GONE_VERIFIED"
                or data.get("kind") != "discord-audit-log-channel-delete"
                or type(channel_type) is not int or channel_type not in SUPPORTED_CHANNEL_TYPES):
            raise ValueError("unsupported source evidence")
        entry = data.get("auditEntry") or {}
        entry_id = entry.get("id")
        if (not isinstance(entry_id, str) or not entry_id.isdecimal() or len(entry_id) > 20
                or entry.get("target_id") != channel or type(entry.get("action_type")) is not int
                or entry["action_type"] != CHANNEL_DELETE):
            raise ValueError("positive CHANNEL_DELETE audit entry required")
        deleted_at = datetime.fromtimestamp(((int(entry_id) >> 22) + DISCORD_EPOCH_MS) / 1000, timezone.utc)
        observed_at = timestamp(data["observedAt"])
        if deleted_at > observed_at + timedelta(seconds=5) or observed_at > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("invalid source evidence time")
        for change in entry.get("changes") or []:
            if change.get("key") == "type" and change.get("old_value") != channel_type:
                raise ValueError("audit channel type mismatch")
        previous = self.connection.execute(
            "SELECT audit_entry_id FROM source_channel_evidence WHERE guild_id=? AND channel_id=?", (guild, channel)
        ).fetchone()
        if previous and int(previous[0]) >= int(entry_id):
            self.apply_verified()
            return False
        self.connection.execute(
            """INSERT INTO source_channel_evidence VALUES(?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, channel_id) DO UPDATE SET
              channel_type=excluded.channel_type, deleted_at=excluded.deleted_at,
              observed_at=excluded.observed_at, audit_entry_id=excluded.audit_entry_id,
              evidence_json=excluded.evidence_json""",
            (guild, channel, channel_type, deleted_at.isoformat(), observed_at.isoformat(), entry_id,
             json.dumps(data, ensure_ascii=False, sort_keys=True)),
        )
        self.apply_verified()
        return True

    def apply_verified(self) -> int:
        """Only passive unresolved media whose EVERY source is verified gone.

        KNOWN/queued/in-flight/cached states keep their existing behavior. Shared
        attachments remain recoverable if any archived reference has no proof.
        The retained attachments table supplies last-known URLs for diagnostics.
        Caller owns the transaction, so import and state change are atomic.
        """
        cursor = self.connection.execute("""
            UPDATE media_objects AS mo
            SET state='SOURCE_GONE', next_retry_at=NULL, manual_recache_requested=0,
                last_error='Источник удалён', failure_class='source_gone',
                updated_at=strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now'),
                current_url=COALESCE(current_url, (
                    SELECT a.url FROM media_refs r JOIN attachments a
                    ON a.message_id=r.message_id AND a.position=r.position
                    WHERE r.media_key=mo.media_key AND a.url IS NOT NULL LIMIT 1)),
                proxy_url=COALESCE(proxy_url, (
                    SELECT a.proxy_url FROM media_refs r JOIN attachments a
                    ON a.message_id=r.message_id AND a.position=r.position
                    WHERE r.media_key=mo.media_key AND a.proxy_url IS NOT NULL LIMIT 1))
            WHERE mo.state IN ('UNRESOLVED', 'STALE_URL')
              AND EXISTS(SELECT 1 FROM media_refs r WHERE r.media_key=mo.media_key)
              AND NOT EXISTS(
                SELECT 1 FROM media_refs r JOIN messages m ON m.id=r.message_id
                LEFT JOIN channels c ON c.id=m.source_channel_id AND c.guild_id=m.guild_id
                LEFT JOIN source_channel_evidence e
                  ON e.guild_id=m.guild_id AND e.channel_id=m.source_channel_id
                    AND e.channel_type=c.type
                WHERE r.media_key=mo.media_key
                  AND (e.channel_id IS NULL OR c.type NOT IN (:voice, :stage)))
        """, {"voice": GUILD_VOICE, "stage": GUILD_STAGE_VOICE})
        return cursor.rowcount

    def can_recover(self, media_key: str, message_id: str, url: str | None, observed_at: str, previous_url: str | None, gone_at: str) -> bool:
        if not url or url == previous_url or not usable_capture_url(url):
            return False
        rows = self.connection.execute("""
            SELECT e.deleted_at FROM messages m
            JOIN source_channel_evidence e ON e.guild_id=m.guild_id AND e.channel_id=m.source_channel_id
            WHERE m.id=? OR EXISTS(SELECT 1 FROM media_refs r WHERE r.message_id=m.id AND r.media_key=?)
        """, (message_id, media_key)).fetchall()
        try:
            return all(timestamp(observed_at) > timestamp(row[0]) for row in rows) if rows else timestamp(observed_at) > timestamp(gone_at)
        except (TypeError, ValueError):
            return False
