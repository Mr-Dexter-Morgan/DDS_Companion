from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from dds_companion import __version__
from dds_companion.core.paths import build_runtime_paths, ensure_runtime_dirs
from dds_companion.services.activity_service import ActivityRecord, ActivityService
from dds_companion.services.health_service import HealthService
from dds_companion.services.import_service import ImportResult, ImportService
from dds_companion.services.runtime_monitor import RuntimeMonitor
from dds_companion.services.stats_service import StatsService
from dds_companion.storage.database import connect_database
from dds_companion.watcher.capture_watcher import CaptureWatcher
from dds_companion.watcher.file_events import WatcherEvent


def human_size(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(abs(value))
    for unit in units:
        if size < 1024 or unit == units[-1]:
            text = f"{size:.2f} {unit}" if unit != "B" else f"{int(size)} B"
            return f"-{text}" if value < 0 else text
        size /= 1024
    return f"{value} B"


def signed_size(value: int) -> str:
    prefix = "+" if value >= 0 else ""
    return f"{prefix}{human_size(value)}"


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DDS Companion — local DDS archive processor")
    parser.add_argument("--dds-data", help="Path to DDS_Data. Defaults to BetterDiscord/DDS_Data.")
    parser.add_argument("--app-data", help="DDS Companion runtime data root.")
    parser.add_argument("--portable", action="store_true", help="Use Data next to DDS.exe as the Companion data root.")
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
        help="Print JSON. In watch mode, runtime events are emitted as JSON Lines.",
    )
    parser.add_argument("--version", action="version", version=f"DDS Companion {__version__}")
    return parser


def relative_capture(path: Path, dds_data: Path) -> str:
    try:
        return str(path.resolve().relative_to(dds_data.resolve()))
    except ValueError:
        return str(path)


def summary_payload(paths, import_result: ImportResult, stats: dict, health: dict, *, mode: str, activity_count: int) -> dict:
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
        "activity_count": activity_count,
    }


def _subsystem_state(health: dict, name: str) -> str:
    return str(health.get("subsystems", {}).get(name, {}).get("state", "UNKNOWN"))


def print_summary(paths, import_result: ImportResult, stats: dict, health: dict, *, watching: bool, poll_ms: int, settle_ms: int, activity_count: int) -> None:
    print(f"DDS Companion v{__version__}  [{health['state']}]")
    print(f"DDS_Data : {paths.dds_data}")
    print(f"Database : {paths.database}")
    if watching:
        print(f"Watcher  : ACTIVE  poll={poll_ms} ms, settle={settle_ms} ms")
    else:
        print("Watcher  : OFF (--once)")
    print(
        "Health   : "
        f"DB={_subsystem_state(health, 'database')} | "
        f"DDS={_subsystem_state(health, 'dds_data')} | "
        f"Importer={_subsystem_state(health, 'importer')} | "
        f"Watcher={_subsystem_state(health, 'watcher')}"
    )
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
    print(
        f"Media    : known={stats['known_media']} attachments, "
        f"cached={stats['cached_media_files']} files; embeds={stats['embeds']} (metadata only)"
    )
    print(
        f"Storage  : SQLite={human_size(int(stats['sqlite_bytes']))}, "
        f"DDS JSON={human_size(int(stats['dds_json_bytes']))}, "
        f"known total={human_size(int(stats['total_known_storage_bytes']))}"
    )
    print(
        "Session  : "
        f"+{stats['session_messages_added']} messages, "
        f"+{stats['session_imports_added']} imports, "
        f"storage {signed_size(int(stats['session_storage_delta_bytes']))}"
    )
    print(
        f"Activity : total={activity_count}, session=+{stats['session_activity_events_added']} events; "
        f"failed jobs unresolved={stats['failed_jobs_unresolved']}"
    )
    if health["last_error"]:
        print(f"Last err : {health['last_error']}")
    if watching:
        print()
        print("Watching DDS_Data. Press Ctrl+C to stop cleanly.")


def make_activity_printer(dds_data: Path, as_json: bool):
    def emit(record: ActivityRecord) -> None:
        stamp = datetime.fromisoformat(record.occurred_at).astimezone().strftime("%H:%M:%S")
        rel = relative_capture(Path(record.capture_path), dds_data) if record.capture_path else None
        if as_json:
            print(json.dumps({"type": "activity", **record.to_dict(), "path": rel}, ensure_ascii=False), flush=True)
            return

        prefix = "ERROR" if record.level == "ERROR" else "ACTIVITY"
        suffix = f" | {rel}" if rel else ""
        persisted = "" if record.persisted else " [memory-only]"
        print(f"[{stamp}] {prefix:<8} {record.summary}{suffix}{persisted}", flush=True)

    return emit


def make_watcher_sink(dds_data: Path, as_json: bool, monitor: RuntimeMonitor):
    def emit(event: WatcherEvent) -> None:
        # First translate the event into the durable Activity/Health model. Activity
        # subscribers handle imported/failed/deleted presentation.
        monitor.handle_watcher_event(event)

        rel = relative_capture(event.path, dds_data)
        stamp = datetime.now().strftime("%H:%M:%S")

        # Persisted Activity already covers these. Avoid duplicate console noise.
        if event.kind in {"imported", "failed", "deleted"}:
            return

        if as_json:
            payload = {
                "type": "watcher_event",
                "time": stamp,
                "kind": event.kind,
                "path": rel,
                "detail": event.detail,
                "result": event.result.__dict__ if event.result else None,
            }
            print(json.dumps(payload, ensure_ascii=False), flush=True)
            return

        if event.kind == "created":
            print(f"[{stamp}] WATCH    new capture: {rel} (settling)", flush=True)
        elif event.kind == "changed":
            print(f"[{stamp}] WATCH    changed: {rel} (settling)", flush=True)
        elif event.kind == "unchanged":
            print(f"[{stamp}] SKIP     unchanged fingerprint: {rel}", flush=True)

    return emit


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    if args.poll_ms < 100:
        raise SystemExit("--poll-ms must be at least 100")
    if args.settle_ms < 50:
        raise SystemExit("--settle-ms must be at least 50")

    paths = build_runtime_paths(args.dds_data, args.app_data, portable=args.portable)
    ensure_runtime_dirs(paths)

    connection = connect_database(paths.database)
    activity: ActivityService | None = None
    health: HealthService | None = None
    try:
        importer = ImportService(connection)
        # Baseline is captured before this session writes Activity or imports data.
        stats_service = StatsService(
            connection,
            paths.database,
            paths.dds_data,
            cache_path=paths.cache,
            media_path=paths.media,
            logs_path=paths.logs,
        )
        activity = ActivityService(connection)
        health = HealthService(connection, paths.dds_data)
        monitor = RuntimeMonitor(activity, health)
        watching = not args.once
        watcher = None

        health.refresh_core(watcher_expected=watching, watcher_state="STARTING" if watching else None)
        health.set_subsystem("importer", "STARTING", "initial DDS_Data synchronization")
        activity.publish(
            subsystem="runtime",
            event_type="session_started",
            summary=f"DDS Companion {__version__} session started",
            details={"mode": "watch" if watching else "once"},
        )

        if watching:
            watcher = CaptureWatcher(
                paths.dds_data,
                importer,
                connection,
                poll_interval=args.poll_ms / 1000.0,
                settle_seconds=args.settle_ms / 1000.0,
                on_event=None,  # attached after monitor/printers are ready below
                on_state=monitor.watcher_state,
                on_heartbeat=monitor.watcher_heartbeat,
            )
            # Snapshot before the initial import. If DDS changes a file while the
            # full scan is running, the first watcher scan will still detect it.
            watcher.prime()

        import_result = importer.import_all(paths.dds_data)
        if import_result.failed:
            health.set_subsystem(
                "importer",
                "LIMITED",
                f"initial sync completed with {import_result.failed} failed capture(s)",
            )
        else:
            health.set_subsystem("importer", "RUNNING", "initial sync completed successfully")

        activity.publish(
            level="WARNING" if import_result.failed else "INFO",
            subsystem="importer",
            event_type="startup_sync",
            summary=(
                f"Initial sync: +{import_result.messages_inserted} new, "
                f"{import_result.messages_updated} refreshed, {import_result.failed} failed"
            ),
            details={
                "files_seen": import_result.files_seen,
                "imported": import_result.imported,
                "unchanged": import_result.skipped_unchanged,
                "failed": import_result.failed,
            },
            messages_new=import_result.messages_inserted,
            messages_refreshed=import_result.messages_updated,
            attachments_registered=import_result.attachments_registered,
            embeds_registered=import_result.embeds_registered,
        )

        if watching:
            # The watcher is fully constructed and primed; mark it healthy for the
            # startup snapshot. CaptureWatcher.run() immediately takes over heartbeat.
            health.set_subsystem("watcher", "RUNNING", "watcher armed and ready")

        stats = stats_service.snapshot().to_dict()
        health_snapshot = health.snapshot(watcher_expected=watching)
        activity_count = activity.count()

        if args.json:
            print(
                json.dumps(
                    summary_payload(
                        paths,
                        import_result,
                        stats,
                        health_snapshot,
                        mode="watch" if watching else "once",
                        activity_count=activity_count,
                    ),
                    ensure_ascii=False,
                ),
                flush=True,
            )
        else:
            print_summary(
                paths,
                import_result,
                stats,
                health_snapshot,
                watching=watching,
                poll_ms=args.poll_ms,
                settle_ms=args.settle_ms,
                activity_count=activity_count,
            )

        # From this point onward the CLI is merely a subscriber to core Activity.
        activity.subscribe(make_activity_printer(paths.dds_data, args.json))

        if not watching:
            activity.publish(
                subsystem="runtime",
                event_type="session_completed",
                summary="One-shot session completed cleanly",
            )
            return 0 if health_snapshot["database_ok"] else 2

        assert watcher is not None
        watcher.on_event = make_watcher_sink(paths.dds_data, args.json, monitor)
        # Catch changes that occurred during the initial full import.
        watcher.scan_once()

        exit_code = 0
        try:
            counters = watcher.run()
        except KeyboardInterrupt:
            if not args.json:
                print("\nStopping DDS Companion watcher cleanly...", flush=True)
            counters = watcher.counters
        except Exception as exc:
            exit_code = 2
            monitor.watcher_state("ERROR")
            activity.publish(
                level="ERROR",
                subsystem="watcher",
                event_type="watcher_crashed",
                summary="Watcher stopped because of an unexpected runtime error",
                details={"error_type": type(exc).__name__, "error": str(exc)},
            )
            counters = watcher.counters

        final_stats = stats_service.snapshot().to_dict()
        final_health = health.snapshot(watcher_expected=False)
        activity.publish(
            level="INFO" if exit_code == 0 else "ERROR",
            subsystem="runtime",
            event_type="session_stopped",
            summary=(
                f"Session stopped: scans={counters.scans}, imports={counters.imported}, "
                f"failed={counters.failed}, session messages=+{final_stats['session_messages_added']}"
            ),
            details={"exit_code": exit_code, "health": final_health["state"]},
        )

        if args.json:
            print(
                json.dumps(
                    {
                        "type": "shutdown",
                        "version": __version__,
                        "watcher": counters.__dict__,
                        "stats": final_stats,
                        "health": final_health,
                    },
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

        return exit_code
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
