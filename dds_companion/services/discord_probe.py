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


def _parse_tasklist_csv(output: bytes | str | None) -> tuple[str, ...]:
    """Return Discord-family process names from raw `tasklist /FO CSV /NH` output.

    Keep the production probe byte-oriented. Windows console utilities emit text in
    the active Windows code page, while Python 3.15 enables UTF-8 mode by default.
    Decoding the whole stream is unnecessary here because the process image names we
    care about are ASCII. Parsing bytes avoids locale/UTF-8 failures completely.
    """
    if isinstance(output, str):
        raw_output = output.encode("utf-8", errors="surrogatepass")
    else:
        raw_output = output or b""

    targets = {b"discord.exe", b"discordcanary.exe", b"discordptb.exe"}
    found: list[str] = []
    for raw_line in raw_output.splitlines():
        line = raw_line.strip()
        if not line or line.upper().startswith(b"INFO:"):
            continue
        first = line.split(b",", 1)[0].strip().strip(b'"')
        lowered = first.lower()
        if lowered in targets:
            found.append(first.decode("ascii"))
    return tuple(dict.fromkeys(found))



def _tasklist_executable() -> str:
    system_root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT")
    if system_root:
        return os.path.join(system_root, "System32", "tasklist.exe")
    return "tasklist"

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
            [_tasklist_executable(), "/FO", "CSV", "/NH"],
            capture_output=True,
            text=False,
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

    if completed.returncode != 0:
        return DiscordProbeResult(
            state="UNKNOWN",
            summary=f"Discord process probe failed: tasklist exit {completed.returncode}",
            checked_at=stamp,
        )

    if completed.stdout is None:
        return DiscordProbeResult(
            state="UNKNOWN",
            summary="Discord process probe failed: tasklist stdout unavailable",
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
