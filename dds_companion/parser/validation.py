from __future__ import annotations

from typing import Any


CAPTURE_SCHEMA_VERSION = 2


class CaptureValidationError(ValueError):
    pass


def _require_dict(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CaptureValidationError(f"{name} must be an object")
    return value


def _snowflake(value: Any, name: str, *, required: bool = True) -> str | None:
    if value in (None, ""):
        if required:
            raise CaptureValidationError(f"{name} is required")
        return None
    text = str(value)
    if not text.isdigit():
        raise CaptureValidationError(f"{name} must be a numeric Discord ID")
    return text


def validate_capture(data: Any) -> dict[str, Any]:
    capture = _require_dict(data, "capture")

    schema_version = capture.get("schemaVersion")
    if schema_version != CAPTURE_SCHEMA_VERSION:
        raise CaptureValidationError(
            f"Unsupported capture schemaVersion={schema_version!r}; "
            f"DDS Companion expects schemaVersion={CAPTURE_SCHEMA_VERSION}"
        )

    guild = _require_dict(capture.get("guild"), "guild")
    _snowflake(guild.get("id"), "guild.id")

    channel = _require_dict(capture.get("channel"), "channel")
    _snowflake(channel.get("id"), "channel.id")

    thread = capture.get("thread")
    if thread is not None:
        thread = _require_dict(thread, "thread")
        _snowflake(thread.get("id"), "thread.id")
        _snowflake(thread.get("parentChannelId"), "thread.parentChannelId")

    messages = capture.get("messages")
    if not isinstance(messages, list):
        raise CaptureValidationError("messages must be an array")

    for index, message in enumerate(messages):
        msg = _require_dict(message, f"messages[{index}]")
        _snowflake(msg.get("id"), f"messages[{index}].id")
        _snowflake(msg.get("channelId"), f"messages[{index}].channelId")
        if msg.get("guildId") not in (None, ""):
            _snowflake(msg.get("guildId"), f"messages[{index}].guildId")

        author = msg.get("author")
        if author is not None:
            author = _require_dict(author, f"messages[{index}].author")
            _snowflake(author.get("id"), f"messages[{index}].author.id")

        attachments = msg.get("attachments", [])
        embeds = msg.get("embeds", [])
        if not isinstance(attachments, list):
            raise CaptureValidationError(f"messages[{index}].attachments must be an array")
        if not isinstance(embeds, list):
            raise CaptureValidationError(f"messages[{index}].embeds must be an array")

    return capture
