from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NormalizedContext:
    guild_id: str
    guild_name: str | None
    parent_channel_id: str
    parent_channel_name: str | None
    parent_channel_type: int | None
    thread_id: str | None
    thread_name: str | None
    effective_channel_id: str


def normalize_context(capture: dict[str, Any]) -> NormalizedContext:
    guild = capture["guild"]
    channel = capture["channel"]
    thread = capture.get("thread")

    if thread:
        parent_id = str(thread["parentChannelId"])
        return NormalizedContext(
            guild_id=str(guild["id"]),
            guild_name=guild.get("name"),
            parent_channel_id=parent_id,
            parent_channel_name=thread.get("parentChannelName"),
            parent_channel_type=thread.get("parentChannelType"),
            thread_id=str(thread["id"]),
            thread_name=thread.get("name"),
            effective_channel_id=str(channel["id"]),
        )

    return NormalizedContext(
        guild_id=str(guild["id"]),
        guild_name=guild.get("name"),
        parent_channel_id=str(channel["id"]),
        parent_channel_name=channel.get("name"),
        parent_channel_type=channel.get("type"),
        thread_id=None,
        thread_name=None,
        effective_channel_id=str(channel["id"]),
    )


def json_text(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
