from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXPORT_SCHEMA_VERSION = 1
PACKAGE_MODES = {"TEXT_ONLY", "TEXT_AND_CACHE"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(value: str, *, fallback: str = "export") -> str:
    text = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", str(value or "").strip())
    text = re.sub(r"\s+", " ", text).strip(" ._")
    return (text or fallback)[:100]


def _json_dump(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


@dataclass(frozen=True)
class ExportPackageResult:
    scope_kind: str
    scope_id: str
    scope_name: str
    mode: str
    output_path: str
    message_count: int
    media_total: int
    media_included: int
    media_missing: int
    bytes_written: int
    complete: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExportPackageService:
    """Provider-independent DDS export serializer.

    SQLite remains source-of-truth. This service only reads archive state and creates
    a derived ZIP package. It never mutates archive/export rules or media lifecycle.
    """

    def __init__(self, connection: sqlite3.Connection, media_root: str | Path):
        self.connection = connection
        self.media_root = Path(media_root).expanduser().resolve()

    def package(
        self,
        scope_kind: str,
        scope_id: str,
        *,
        mode: str,
        output_dir: str | Path,
        app_version: str,
    ) -> ExportPackageResult:
        scope_kind = str(scope_kind or "").strip().lower()
        scope_id = str(scope_id or "").strip()
        mode = str(mode or "").strip().upper()
        if scope_kind not in {"guild", "channel", "thread"}:
            raise ValueError(f"unsupported export scope: {scope_kind}")
        if not scope_id:
            raise ValueError("export scope id is empty")
        if mode not in PACKAGE_MODES:
            raise ValueError(f"unsupported package mode: {mode}")

        scope = self._scope_info(scope_kind, scope_id)
        messages = self._messages(scope_kind, scope_id)
        message_ids = [str(row["id"]) for row in messages]
        attachments = self._attachments(message_ids)
        embeds = self._embeds(message_ids)

        output_root = Path(output_dir).expanduser().resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().astimezone().strftime("%Y-%m-%d_%H-%M-%S")
        base_name = f"{_safe_name(scope['name'])}_{stamp}"
        final_path = self._unique_destination(output_root, base_name, ".zip")

        media_index: list[dict[str, Any]] = []
        media_included = 0
        media_missing = 0
        package_bytes = 0

        staging_parent = output_root / ".dds_staging"
        staging_parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix="package_", dir=staging_parent))
        temp_zip = final_path.with_name(f".{final_path.name}.tmp")
        try:
            media_dir = staging / "media"
            if mode == "TEXT_AND_CACHE":
                media_dir.mkdir(parents=True, exist_ok=True)

            by_message: dict[str, list[dict[str, Any]]] = {}
            for attachment in attachments:
                item = dict(attachment)
                item["package_relpath"] = None
                state = str(item.get("media_state") or "KNOWN").upper()
                source = self._safe_media_source(item.get("local_relpath"))
                include = mode == "TEXT_AND_CACHE" and state == "CACHED" and source is not None
                if include:
                    packaged_name = self._packaged_media_name(item)
                    destination = media_dir / packaged_name
                    shutil.copy2(source, destination)
                    item["package_relpath"] = f"media/{packaged_name}"
                    item["package_state"] = "included"
                    media_included += 1
                else:
                    if state in {"UNRESOLVED", "STALE_URL"}:
                        package_state = "awaiting_rediscovery"
                    elif state == "CACHED" and source is None:
                        package_state = "cache_file_missing"
                    elif mode == "TEXT_ONLY":
                        package_state = "not_included_text_only"
                    else:
                        package_state = "not_cached"
                    item["package_state"] = package_state
                    if mode == "TEXT_AND_CACHE":
                        media_missing += 1
                media_index.append(item)
                by_message.setdefault(str(item["message_id"]), []).append(item)

            machine_messages: list[dict[str, Any]] = []
            embed_by_message: dict[str, list[dict[str, Any]]] = {}
            for embed in embeds:
                embed_by_message.setdefault(str(embed["message_id"]), []).append(dict(embed))
            for message in messages:
                payload = dict(message)
                mid = str(payload["id"])
                payload["attachments"] = by_message.get(mid, [])
                payload["embeds"] = embed_by_message.get(mid, [])
                machine_messages.append(payload)

            content_md = self._render_markdown(scope, machine_messages, mode)
            (staging / "content.md").write_text(content_md, encoding="utf-8")
            _json_dump(staging / "messages.json", machine_messages)
            _json_dump(staging / "media_index.json", media_index)

            manifest = {
                "dds_export_schema": EXPORT_SCHEMA_VERSION,
                "dds_app_version": str(app_version),
                "created_at": _utc_now(),
                "scope": scope,
                "mode": mode,
                "counts": {
                    "messages": len(machine_messages),
                    "media_total": len(media_index),
                    "media_included": media_included,
                    "media_missing": media_missing,
                },
                "complete": mode == "TEXT_ONLY" or media_missing == 0,
                "files": {
                    "human_readable": "content.md",
                    "messages": "messages.json",
                    "media_index": "media_index.json",
                    "media_directory": "media/" if mode == "TEXT_AND_CACHE" else None,
                },
            }
            _json_dump(staging / "manifest.json", manifest)

            required = {"manifest.json", "content.md", "messages.json", "media_index.json"}
            with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for path in sorted(staging.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(staging).as_posix())
            with zipfile.ZipFile(temp_zip, "r") as archive:
                names = set(archive.namelist())
                if not required.issubset(names):
                    missing = sorted(required - names)
                    raise RuntimeError(f"package validation failed; missing: {', '.join(missing)}")
                bad = archive.testzip()
                if bad is not None:
                    raise RuntimeError(f"package validation failed at {bad}")
                parsed = json.loads(archive.read("manifest.json").decode("utf-8"))
                if int(parsed.get("dds_export_schema", -1)) != EXPORT_SCHEMA_VERSION:
                    raise RuntimeError("package manifest schema validation failed")
            package_bytes = temp_zip.stat().st_size
            os.replace(temp_zip, final_path)
            return ExportPackageResult(
                scope_kind=scope_kind,
                scope_id=scope_id,
                scope_name=str(scope["name"]),
                mode=mode,
                output_path=str(final_path),
                message_count=len(machine_messages),
                media_total=len(media_index),
                media_included=media_included,
                media_missing=media_missing,
                bytes_written=package_bytes,
                complete=bool(manifest["complete"]),
            )
        finally:
            try:
                temp_zip.unlink(missing_ok=True)
            except OSError:
                pass
            shutil.rmtree(staging, ignore_errors=True)
            try:
                staging_parent.rmdir()
            except OSError:
                pass

    @staticmethod
    def _unique_destination(root: Path, stem: str, suffix: str) -> Path:
        candidate = root / f"{stem}{suffix}"
        index = 2
        while candidate.exists():
            candidate = root / f"{stem}_{index}{suffix}"
            index += 1
        return candidate

    def _scope_info(self, kind: str, scope_id: str) -> dict[str, Any]:
        if kind == "guild":
            row = self.connection.execute(
                "SELECT id, COALESCE(NULLIF(name,''), id) AS name FROM guilds WHERE id=?",
                (scope_id,),
            ).fetchone()
            if row is None:
                raise LookupError("guild not found")
            return {"kind": kind, "id": str(row["id"]), "name": str(row["name"])}
        if kind == "channel":
            row = self.connection.execute(
                """
                SELECT c.id, COALESCE(NULLIF(c.name,''), c.id) AS name,
                       c.guild_id, COALESCE(NULLIF(g.name,''), g.id) AS guild_name
                FROM channels c JOIN guilds g ON g.id=c.guild_id WHERE c.id=?
                """,
                (scope_id,),
            ).fetchone()
            if row is None:
                raise LookupError("channel not found")
            return {
                "kind": kind, "id": str(row["id"]), "name": str(row["name"]),
                "guild_id": str(row["guild_id"]), "guild_name": str(row["guild_name"]),
            }
        row = self.connection.execute(
            """
            SELECT t.id, COALESCE(NULLIF(t.name,''), t.id) AS name,
                   t.guild_id, t.parent_channel_id,
                   COALESCE(NULLIF(g.name,''), g.id) AS guild_name,
                   COALESCE(NULLIF(c.name,''), c.id) AS channel_name
            FROM threads t
            JOIN guilds g ON g.id=t.guild_id
            JOIN channels c ON c.id=t.parent_channel_id
            WHERE t.id=?
            """,
            (scope_id,),
        ).fetchone()
        if row is None:
            raise LookupError("thread not found")
        return {
            "kind": kind, "id": str(row["id"]), "name": str(row["name"]),
            "guild_id": str(row["guild_id"]), "guild_name": str(row["guild_name"]),
            "channel_id": str(row["parent_channel_id"]), "channel_name": str(row["channel_name"]),
        }

    def _scope_where(self, kind: str) -> str:
        return {
            "guild": "m.guild_id = ?",
            "channel": "m.parent_channel_id = ?",
            "thread": "m.thread_id = ?",
        }[kind]

    def _messages(self, kind: str, scope_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            f"""
            SELECT m.*, COALESCE(NULLIF(u.display_name,''), NULLIF(u.global_name,''),
                   NULLIF(u.username,''), m.author_id, 'Неизвестный автор') AS author_name,
                   COALESCE(NULLIF(c.name,''), c.id) AS channel_name,
                   COALESCE(NULLIF(t.name,''), t.id) AS thread_name
            FROM messages m
            LEFT JOIN users u ON u.id=m.author_id
            LEFT JOIN channels c ON c.id=m.parent_channel_id
            LEFT JOIN threads t ON t.id=m.thread_id
            WHERE {self._scope_where(kind)}
            ORDER BY COALESCE(m.timestamp, m.first_seen_at, ''), m.id
            """,
            (scope_id,),
        ).fetchall()
        result = []
        for row in rows:
            result.append({key: row[key] for key in row.keys()})
        return result

    def _attachments(self, message_ids: list[str]) -> list[dict[str, Any]]:
        if not message_ids:
            return []
        placeholders = ",".join("?" for _ in message_ids)
        rows = self.connection.execute(
            f"""
            SELECT a.*, mr.media_key, mo.state AS media_state, mo.local_relpath,
                   mo.local_size, mo.sha256, mo.last_http_status, mo.failure_class
            FROM attachments a
            LEFT JOIN media_refs mr ON mr.message_id=a.message_id AND mr.position=a.position
            LEFT JOIN media_objects mo ON mo.media_key=mr.media_key
            WHERE a.message_id IN ({placeholders})
            ORDER BY a.message_id, a.position
            """,
            tuple(message_ids),
        ).fetchall()
        return [{key: row[key] for key in row.keys()} for row in rows]

    def _embeds(self, message_ids: list[str]) -> list[dict[str, Any]]:
        if not message_ids:
            return []
        placeholders = ",".join("?" for _ in message_ids)
        rows = self.connection.execute(
            f"SELECT * FROM embeds WHERE message_id IN ({placeholders}) ORDER BY message_id, position",
            tuple(message_ids),
        ).fetchall()
        return [{key: row[key] for key in row.keys()} for row in rows]

    def _safe_media_source(self, relpath: Any) -> Path | None:
        if not relpath:
            return None
        try:
            candidate = (self.media_root / str(relpath)).resolve()
            candidate.relative_to(self.media_root)
        except (OSError, ValueError):
            return None
        return candidate if candidate.is_file() else None

    @staticmethod
    def _packaged_media_name(item: dict[str, Any]) -> str:
        filename = _safe_name(str(item.get("filename") or "attachment"), fallback="attachment")
        suffix = Path(filename).suffix[:16]
        stem = _safe_name(Path(filename).stem, fallback="attachment")[:60]
        identity = str(item.get("media_key") or item.get("attachment_id") or "media")
        stable = hashlib.sha256(identity.encode("utf-8", "replace")).hexdigest()[:16]
        return f"{stable}_{stem}{suffix}"

    @staticmethod
    def _render_markdown(scope: dict[str, Any], messages: list[dict[str, Any]], mode: str) -> str:
        hierarchy = [scope.get("guild_name"), scope.get("channel_name"), scope.get("name")]
        hierarchy = [str(item) for item in hierarchy if item]
        lines = [
            f"# DDS export — {scope.get('name', 'Без названия')}",
            "",
            f"- Scope: `{scope.get('kind')}` / `{scope.get('id')}`",
            f"- Path: {' → '.join(hierarchy) if hierarchy else scope.get('name')}",
            f"- Mode: `{mode}`",
            "",
            "---",
            "",
        ]
        for message in messages:
            author = str(message.get("author_name") or message.get("author_id") or "Неизвестный автор")
            stamp = str(message.get("timestamp") or message.get("first_seen_at") or "—")
            location = str(message.get("channel_name") or "")
            if message.get("thread_name"):
                location += f" → {message.get('thread_name')}"
            lines.extend([f"## {author} · {stamp}", ""])
            if location:
                lines.extend([f"_Раздел: {location}_", ""])
            content = str(message.get("content") or "").rstrip()
            lines.extend([content or "_(без текста)_", ""])
            for attachment in message.get("attachments") or []:
                name = str(attachment.get("filename") or attachment.get("attachment_id") or "Вложение")
                rel = attachment.get("package_relpath")
                state = str(attachment.get("package_state") or attachment.get("media_state") or "unknown")
                if rel:
                    lines.append(f"- Вложение: [{name}]({rel})")
                else:
                    lines.append(f"- Вложение: {name} — `{state}`")
            for embed in message.get("embeds") or []:
                title = str(embed.get("title") or embed.get("type") or "Embed")
                url = str(embed.get("url") or "")
                description = str(embed.get("description") or "")
                lines.append(f"- Embed: {title}{f' — {url}' if url else ''}")
                if description:
                    lines.append(f"  {description}")
            lines.extend(["", "---", ""])
        return "\n".join(lines).rstrip() + "\n"
