from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class DiscordProbeResult:
    state: str
    summary: str
    checked_at: str
    detected_processes: tuple[str, ...] = ()


def _parse_tasklist_csv(output: str) -> tuple[str, ...]:
    """Return Discord-family process names from `tasklist /FO CSV /NH` output."""
    found: list[str] = []
    for raw_line in (output or "").splitlines():
        line = raw_line.strip()
        if not line or line.upper().startswith("INFO:"):
            continue
        # CSV output starts with the image name in quotes. Keep the parser deliberately
        # tiny so this probe stays dependency-free.
        first = line.split(",", 1)[0].strip().strip('"')
        lowered = first.lower()
        if lowered in {"discord.exe", "discordcanary.exe", "discordptb.exe"}:
            found.append(first)
    return tuple(dict.fromkeys(found))


def probe_discord_process() -> DiscordProbeResult:
    stamp = utc_now()
    if os.name != "nt":
        return DiscordProbeResult(
            state="UNKNOWN",
            summary="Discord process probe is available on Windows only",
            checked_at=stamp,
        )

    try:
        completed = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return DiscordProbeResult(
            state="UNKNOWN",
            summary=f"Discord process probe failed: {type(exc).__name__}",
            checked_at=stamp,
        )

    found = _parse_tasklist_csv(completed.stdout)
    if found:
        return DiscordProbeResult(
            state="RUNNING",
            summary=f"Discord process detected: {', '.join(found)}",
            checked_at=stamp,
            detected_processes=found,
        )
    return DiscordProbeResult(
        state="NOT RUNNING",
        summary="Discord is not running — archived data remains available",
        checked_at=stamp,
    )
