from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from dds_companion import __version__
from dds_companion.core.paths import build_runtime_paths, ensure_runtime_dirs
from dds_companion.services.health_service import collect_health
from dds_companion.services.import_service import ImportResult, ImportService
from dds_companion.services.stats_service import collect_stats
from dds_companion.storage.database import connect_database
from dds_companion.watcher.capture_watcher import CaptureWatcher
from dds_companion.watcher.file_events import WatcherEvent


def human_size(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{value} B"


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DDS Companion — local DDS archive processor")
    parser.add_argument("--dds-data", help="Path to DDS_Data. Defaults to BetterDiscord/DDS_Data.")
    parser.add_argument("--app-data", help="DDS Companion runtime data root.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one full import and exit instead of watching DDS_Data continuously.",
    )
    parser.add_argument(
        "--poll-ms",
        type=int,
        default=750,
        help="Watcher scan interval in milliseconds (default: 750).",
    )
    parser.add_argument(
        "--settle-ms",
        type=int,
        default=500,
        help="How long a changed capture must remain stable before import (default: 500).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON. In watch mode, events are emitted as JSON Lines.",
    )
    parser.add_argument("--version", action="version", version=f"DDS Companion {__version__}")
    return parser


def relative_capture(path: Path, dds_data: Path) -> str:
    try:
        return str(path.resolve().relative_to(dds_data.resolve()))
    except ValueError:
        return str(path)


def summary_payload(paths, import_result: ImportResult, stats: dict, health: dict, *, mode: str) -> dict:
    return {
        "type": "startup",
        "version": __version__,
        "mode": mode,
        "dds_data": str(paths.dds_data),
        "app_data": str(paths.app_data),
        "database": str(paths.database),
        "import": import_result.__dict__,
        "stats": stats,
        "health": health,
    }


def print_summary(paths, import_result: ImportResult, stats: dict, health: dict, *, watching: bool, poll_ms: int, settle_ms: int) -> None:
    print(f"DDS Companion v{__version__}  [{health['state']}]")
    print(f"DDS_Data : {paths.dds_data}")
    print(f"Database : {paths.database}")
    if watching:
        print(f"Watcher  : ACTIVE  poll={poll_ms} ms, settle={settle_ms} ms")
    else:
        print("Watcher  : OFF (--once)")
    print()
    print(
        "Import   : "
        f"seen={import_result.files_seen}, imported={import_result.imported}, "
        f"unchanged={import_result.skipped_unchanged}, failed={import_result.failed}"
    )
    print(
        "Messages : "
        f"+{import_result.messages_inserted} new, {import_result.messages_updated} existing refreshed; "
        f"archive total={stats['messages']}"
    )
    print(f"Context  : guilds={stats['guilds']}, channels={stats['channels']}, threads={stats['threads']}")
    print(f"Media    : attachments={stats['attachments']}, embeds={stats['embeds']} (metadata only)")
    print(
        f"Storage  : SQLite={human_size(int(stats['sqlite_bytes']))}, "
        f"DDS JSON={human_size(int(stats['dds_json_bytes']))}, "
        f"known total={human_size(int(stats['total_known_storage_bytes']))}"
    )
    if health["last_error"]:
        print(f"Last err : {health['last_error']}")
    if watching:
        print()
        print("Watching DDS_Data. Press Ctrl+C to stop cleanly.")


def make_event_printer(dds_data: Path, as_json: bool):
    def emit(event: WatcherEvent) -> None:
        rel = relative_capture(event.path, dds_data)
        stamp = datetime.now().strftime("%H:%M:%S")
        result = event.result

        if as_json:
            payload = {
                "type": "watcher_event",
                "time": stamp,
                "kind": event.kind,
                "path": rel,
                "detail": event.detail,
                "result": result.__dict__ if result else None,
            }
            print(json.dumps(payload, ensure_ascii=False), flush=True)
            return

        if event.kind == "created":
            print(f"[{stamp}] WATCH   new capture: {rel} (settling)", flush=True)
        elif event.kind == "changed":
            print(f"[{stamp}] WATCH   changed: {rel} (settling)", flush=True)
        elif event.kind == "deleted":
            print(f"[{stamp}] WATCH   removed: {rel}; archive preserved", flush=True)
        elif event.kind == "unchanged":
            print(f"[{stamp}] SKIP    unchanged fingerprint: {rel}", flush=True)
        elif event.kind == "imported" and result is not None:
            print(
                f"[{stamp}] IMPORT  {rel} -> +{result.messages_inserted} new, "
                f"{result.messages_updated} existing refreshed, "
                f"attachments={result.attachments_registered}, embeds={result.embeds_registered}",
                flush=True,
            )
        elif event.kind == "failed":
            print(f"[{stamp}] ERROR   {rel} -> {event.detail}", flush=True)

    return emit


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    if args.poll_ms < 100:
        raise SystemExit("--poll-ms must be at least 100")
    if args.settle_ms < 50:
        raise SystemExit("--settle-ms must be at least 50")

    paths = build_runtime_paths(args.dds_data, args.app_data)
    ensure_runtime_dirs(paths)

    connection = connect_database(paths.database)
    try:
        importer = ImportService(connection)
        watching = not args.once
        watcher = None

        if watching:
            watcher = CaptureWatcher(
                paths.dds_data,
                importer,
                connection,
                poll_interval=args.poll_ms / 1000.0,
                settle_seconds=args.settle_ms / 1000.0,
                on_event=make_event_printer(paths.dds_data, args.json),
            )
            # Snapshot before the initial import. If DDS changes a file while the
            # full scan is running, the first watcher scan will still detect it.
            watcher.prime()

        import_result = importer.import_all(paths.dds_data)
        stats = collect_stats(connection, paths.database, paths.dds_data)
        health = collect_health(connection, paths.dds_data)

        if args.json:
            print(
                json.dumps(
                    summary_payload(paths, import_result, stats, health, mode="watch" if watching else "once"),
                    ensure_ascii=False,
                ),
                flush=True,
            )
        else:
            print_summary(
                paths,
                import_result,
                stats,
                health,
                watching=watching,
                poll_ms=args.poll_ms,
                settle_ms=args.settle_ms,
            )

        if not watching:
            return 0 if health["database_ok"] else 2

        assert watcher is not None
        # Catch changes that occurred during the initial full import.
        watcher.scan_once()

        try:
            counters = watcher.run()
        except KeyboardInterrupt:
            if not args.json:
                print("\nStopping DDS Companion watcher cleanly...", flush=True)
            counters = watcher.counters

        if args.json:
            print(
                json.dumps(
                    {"type": "shutdown", "version": __version__, "watcher": counters.__dict__},
                    ensure_ascii=False,
                ),
                flush=True,
            )
        else:
            print(
                "Watcher stopped: "
                f"scans={counters.scans}, changed={counters.changed}, new={counters.discovered}, "
                f"imports={counters.imported}, failed={counters.failed}"
            )

        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
