from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dds_companion.core.paths import RuntimePaths


@dataclass(frozen=True)
class UpdaterPaths:
    workspace: Path
    downloads: Path
    staging: Path
    backup: Path
    journal: Path
    lock: Path
    check_state: Path
    log: Path


def build_updater_paths(paths: RuntimePaths) -> UpdaterPaths:
    """Build updater-owned paths without making updater a core dependency."""
    if paths.application_dir is None:
        raise ValueError("application_dir is required for updater paths")

    if paths.deployment_profile == "portable":
        app_dir = paths.application_dir.resolve()
        workspace = app_dir.parent / f".{app_dir.name}.dds-update"
    else:
        workspace = paths.app_data / "update"

    return UpdaterPaths(
        workspace=workspace,
        downloads=workspace / "downloads",
        staging=workspace / "staging",
        backup=workspace / "backup",
        journal=workspace / "journal.json",
        lock=workspace / "update.lock",
        check_state=workspace / "check_state.json",
        log=paths.logs / "updater.log",
    )


def ensure_updater_dirs(paths: UpdaterPaths) -> None:
    for directory in (paths.workspace, paths.downloads, paths.staging, paths.backup, paths.log.parent):
        directory.mkdir(parents=True, exist_ok=True)
