from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dds_companion import __version__
from dds_companion.core.paths import build_runtime_paths, ensure_runtime_dirs
from dds_companion.services.health_service import collect_health
from dds_companion.services.import_service import ImportService
from dds_companion.services.stats_service import collect_stats
from dds_companion.storage.database import connect_database


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
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary.")
    parser.add_argument("--version", action="version", version=f"DDS Companion {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    paths = build_runtime_paths(args.dds_data, args.app_data)
    ensure_runtime_dirs(paths)

    connection = connect_database(paths.database)
    try:
        importer = ImportService(connection)
        import_result = importer.import_all(paths.dds_data)
        stats = collect_stats(connection, paths.database, paths.dds_data)
        health = collect_health(connection, paths.dds_data)

        payload = {
            "version": __version__,
            "dds_data": str(paths.dds_data),
            "app_data": str(paths.app_data),
            "database": str(paths.database),
            "import": import_result.__dict__,
            "stats": stats,
            "health": health,
        }

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"DDS Companion v{__version__}  [{health['state']}]")
            print(f"DDS_Data : {paths.dds_data}")
            print(f"Database : {paths.database}")
            print()
            print(
                "Import   : "
                f"seen={import_result.files_seen}, imported={import_result.imported}, "
                f"unchanged={import_result.skipped_unchanged}, failed={import_result.failed}"
            )
            print(
                "Messages : "
                f"+{import_result.messages_inserted} new, {import_result.messages_updated} updated; "
                f"archive total={stats['messages']}"
            )
            print(
                f"Context  : guilds={stats['guilds']}, channels={stats['channels']}, threads={stats['threads']}"
            )
            print(
                f"Media    : attachments={stats['attachments']}, embeds={stats['embeds']} (metadata only)"
            )
            print(
                f"Storage  : SQLite={human_size(int(stats['sqlite_bytes']))}, "
                f"DDS JSON={human_size(int(stats['dds_json_bytes']))}, "
                f"known total={human_size(int(stats['total_known_storage_bytes']))}"
            )
            if health["last_error"]:
                print(f"Last err : {health['last_error']}")

        return 0 if health["database_ok"] else 2
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
