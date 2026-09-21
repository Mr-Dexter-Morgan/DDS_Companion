from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dds_companion.services.media_registry_service import MediaRegistryService


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class BranchMaintenanceResult:
    action: str
    scope_kind: str
    scope_id: str
    messages_removed: int = 0
    media_files_removed: int = 0
    media_bytes_removed: int = 0
    media_rows_removed: int = 0
    media_rows_reset: int = 0
    shared_media_skipped: int = 0
    rules_removed: int = 0
    structural_nodes_removed: int = 0
    errors: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BranchMaintenanceService:
    """Destructive operations scoped to one Library node.

    The service intentionally does not touch DDS_Data capture files. Historical
    capture_imports are retained as a dedup boundary so deleting one archive branch
    does not cause untouched old capture JSON to repopulate it immediately.
    """

    def __init__(self, connection: sqlite3.Connection, media_root: str | Path):
        self.connection = connection
        self.media_root = Path(media_root).expanduser().resolve()

    def clear_media_cache(self, scope_kind: str, scope_id: str) -> BranchMaintenanceResult:
        kind, sid = self._normalize_scope(scope_kind, scope_id)
        media = self._media_for_scope(kind, sid)
        removable = [row for row in media if int(row["outside_refs"]) == 0 and row["local_relpath"]]
        relpaths: list[str] = []
        files_removed = bytes_removed = errors = 0
        for row in removable:
            relpath = str(row["local_relpath"])
            path = self._safe_media_path(relpath)
            if path is None:
                continue
            try:
                size = path.stat().st_size
                path.unlink()
                files_removed += 1
                bytes_removed += int(size)
                relpaths.append(relpath.replace("\\", "/"))
            except OSError:
                errors += 1
        reset = MediaRegistryService(self.connection).reset_removed_cache_paths(
            relpaths, eviction_reason="manual_clear"
        )
        self._prune_empty_dirs()
        return BranchMaintenanceResult(
            action="clear_media_cache",
            scope_kind=kind,
            scope_id=sid,
            media_files_removed=files_removed,
            media_bytes_removed=bytes_removed,
            media_rows_reset=reset,
            shared_media_skipped=sum(int(row["outside_refs"]) > 0 for row in media),
            errors=errors,
        )

    def delete_data(self, scope_kind: str, scope_id: str) -> BranchMaintenanceResult:
        kind, sid = self._normalize_scope(scope_kind, scope_id)
        self._assert_scope_exists(kind, sid)
        candidate_media = self._media_keys_for_scope(kind, sid)
        count = self._message_count(kind, sid)
        with self.connection:
            self.connection.execute(
                f"DELETE FROM messages WHERE {self._scope_where(kind).replace('m.', '')}",
                (sid,),
            )
        files_removed, bytes_removed, rows_removed, errors = self._remove_orphan_media(candidate_media)
        return BranchMaintenanceResult(
            action="delete_data",
            scope_kind=kind,
            scope_id=sid,
            messages_removed=count,
            media_files_removed=files_removed,
            media_bytes_removed=bytes_removed,
            media_rows_removed=rows_removed,
            errors=errors,
        )

    def delete_branch(self, scope_kind: str, scope_id: str) -> BranchMaintenanceResult:
        kind, sid = self._normalize_scope(scope_kind, scope_id)
        self._assert_scope_exists(kind, sid)
        candidate_media = self._media_keys_for_scope(kind, sid)
        message_count = self._message_count(kind, sid)
        descendant_rules = self._rule_scopes(kind, sid)
        nodes = self._structural_node_count(kind, sid)
        with self.connection:
            # Thread FK uses ON DELETE SET NULL, so delete its messages first.
            if kind == "thread":
                self.connection.execute("DELETE FROM messages WHERE thread_id=?", (sid,))
                self.connection.execute("DELETE FROM threads WHERE id=?", (sid,))
            elif kind == "channel":
                self.connection.execute("DELETE FROM messages WHERE parent_channel_id=?", (sid,))
                self.connection.execute("DELETE FROM channels WHERE id=?", (sid,))
            else:
                self.connection.execute("DELETE FROM guilds WHERE id=?", (sid,))
            rules_removed = 0
            for rule_kind, rule_id in descendant_rules:
                cursor = self.connection.execute(
                    "DELETE FROM archive_export_rules WHERE scope_kind=? AND scope_id=?",
                    (rule_kind, rule_id),
                )
                rules_removed += int(cursor.rowcount or 0)
        files_removed, bytes_removed, rows_removed, errors = self._remove_orphan_media(candidate_media)
        return BranchMaintenanceResult(
            action="delete_branch",
            scope_kind=kind,
            scope_id=sid,
            messages_removed=message_count,
            media_files_removed=files_removed,
            media_bytes_removed=bytes_removed,
            media_rows_removed=rows_removed,
            rules_removed=rules_removed,
            structural_nodes_removed=nodes,
            errors=errors,
        )

    def _normalize_scope(self, kind: str, scope_id: str) -> tuple[str, str]:
        kind = str(kind or "").strip().lower()
        sid = str(scope_id or "").strip()
        if kind not in {"guild", "channel", "thread"}:
            raise ValueError(f"unsupported scope: {kind}")
        if not sid:
            raise ValueError("scope id is empty")
        return kind, sid

    @staticmethod
    def _scope_where(kind: str) -> str:
        return {
            "guild": "m.guild_id = ?",
            "channel": "m.parent_channel_id = ?",
            "thread": "m.thread_id = ?",
        }[kind]

    def _assert_scope_exists(self, kind: str, sid: str) -> None:
        table = {"guild": "guilds", "channel": "channels", "thread": "threads"}[kind]
        if self.connection.execute(f"SELECT 1 FROM {table} WHERE id=?", (sid,)).fetchone() is None:
            raise LookupError(f"{kind} not found")

    def _message_count(self, kind: str, sid: str) -> int:
        row = self.connection.execute(
            f"SELECT COUNT(*) FROM messages m WHERE {self._scope_where(kind)}", (sid,)
        ).fetchone()
        return int(row[0] if row else 0)

    def _media_keys_for_scope(self, kind: str, sid: str) -> list[str]:
        rows = self.connection.execute(
            f"""
            SELECT DISTINCT mr.media_key
            FROM media_refs mr JOIN messages m ON m.id=mr.message_id
            WHERE {self._scope_where(kind)}
            """,
            (sid,),
        ).fetchall()
        return [str(row[0]) for row in rows]

    def _media_for_scope(self, kind: str, sid: str) -> list[sqlite3.Row]:
        condition = self._scope_where(kind)
        rows = self.connection.execute(
            f"""
            SELECT mo.media_key, mo.local_relpath,
                   SUM(CASE WHEN {condition} THEN 1 ELSE 0 END) AS inside_refs,
                   SUM(CASE WHEN NOT ({condition}) THEN 1 ELSE 0 END) AS outside_refs
            FROM media_objects mo
            JOIN media_refs mr ON mr.media_key=mo.media_key
            JOIN messages m ON m.id=mr.message_id
            WHERE mo.media_key IN (
                SELECT mr2.media_key FROM media_refs mr2
                JOIN messages m2 ON m2.id=mr2.message_id
                WHERE {condition.replace('m.', 'm2.')}
            )
            GROUP BY mo.media_key, mo.local_relpath
            """,
            (sid, sid, sid),
        ).fetchall()
        return list(rows)

    def _remove_orphan_media(self, media_keys: list[str]) -> tuple[int, int, int, int]:
        files_removed = bytes_removed = rows_removed = errors = 0
        for key in media_keys:
            if self.connection.execute(
                "SELECT 1 FROM media_refs WHERE media_key=? LIMIT 1", (key,)
            ).fetchone() is not None:
                continue
            row = self.connection.execute(
                "SELECT local_relpath FROM media_objects WHERE media_key=?", (key,)
            ).fetchone()
            relpath = row["local_relpath"] if row else None
            if relpath:
                path = self._safe_media_path(str(relpath))
                if path is not None:
                    try:
                        size = path.stat().st_size
                        path.unlink()
                        files_removed += 1
                        bytes_removed += int(size)
                    except OSError:
                        errors += 1
            with self.connection:
                cursor = self.connection.execute("DELETE FROM media_objects WHERE media_key=?", (key,))
                rows_removed += int(cursor.rowcount or 0)
        self._prune_empty_dirs()
        return files_removed, bytes_removed, rows_removed, errors

    def _safe_media_path(self, relpath: str) -> Path | None:
        try:
            path = (self.media_root / relpath).resolve()
            path.relative_to(self.media_root)
        except (OSError, ValueError):
            return None
        return path if path.is_file() else None

    def _rule_scopes(self, kind: str, sid: str) -> list[tuple[str, str]]:
        scopes: list[tuple[str, str]] = [(kind, sid)]
        if kind == "guild":
            channels = [str(row[0]) for row in self.connection.execute("SELECT id FROM channels WHERE guild_id=?", (sid,))]
            threads = [str(row[0]) for row in self.connection.execute("SELECT id FROM threads WHERE guild_id=?", (sid,))]
            scopes.extend(("channel", value) for value in channels)
            scopes.extend(("thread", value) for value in threads)
        elif kind == "channel":
            threads = [str(row[0]) for row in self.connection.execute("SELECT id FROM threads WHERE parent_channel_id=?", (sid,))]
            scopes.extend(("thread", value) for value in threads)
        return scopes

    def _structural_node_count(self, kind: str, sid: str) -> int:
        if kind == "thread":
            return 1
        if kind == "channel":
            threads = int(self.connection.execute("SELECT COUNT(*) FROM threads WHERE parent_channel_id=?", (sid,)).fetchone()[0])
            return 1 + threads
        channels = int(self.connection.execute("SELECT COUNT(*) FROM channels WHERE guild_id=?", (sid,)).fetchone()[0])
        threads = int(self.connection.execute("SELECT COUNT(*) FROM threads WHERE guild_id=?", (sid,)).fetchone()[0])
        return 1 + channels + threads

    def _prune_empty_dirs(self) -> None:
        if not self.media_root.exists():
            return
        dirs = [p for p in self.media_root.rglob("*") if p.is_dir() and p.name != ".staging"]
        dirs.sort(key=lambda p: len(p.parts), reverse=True)
        for path in dirs:
            try:
                path.rmdir()
            except OSError:
                pass
