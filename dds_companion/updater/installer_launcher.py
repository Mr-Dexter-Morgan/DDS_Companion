from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .controller import PreparedUpdate
from .paths import UpdaterPaths


def launch_external_updater(
    *,
    application_dir: str | Path,
    paths: UpdaterPaths,
    prepared: PreparedUpdate,
    parent_pid: int,
    resume_state_path: str | Path | None,
    launch_args: list[str] | tuple[str, ...] = (),
) -> subprocess.Popen:
    root = Path(application_dir).resolve()
    source = root / "DDSUpdater.exe"
    if not source.is_file():
        raise FileNotFoundError("DDSUpdater.exe is missing")

    runner_dir = paths.workspace / "runner"
    runner_dir.mkdir(parents=True, exist_ok=True)
    runner = runner_dir / "DDSUpdater.exe"
    shutil.copy2(source, runner)

    ack = paths.workspace / f"startup-{prepared.version}.ok"
    ack.unlink(missing_ok=True)
    launch_args_file = paths.workspace / "relaunch_args.json"
    temp_args = launch_args_file.with_name(launch_args_file.name + ".tmp")
    temp_args.write_text(
        json.dumps({"args": list(launch_args)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temp_args, launch_args_file)
    command = [
        str(runner),
        "--application-dir", str(root),
        "--staged-dir", str(prepared.staged_path),
        "--target-version", prepared.version,
        "--parent-pid", str(parent_pid),
        "--ack-path", str(ack),
        "--launch-args-file", str(launch_args_file),
        "--lock-path", str(paths.lock),
        "--log-path", str(paths.log),
        "--journal-path", str(paths.journal),
    ]
    if resume_state_path is not None:
        command += ["--resume-state", str(Path(resume_state_path).resolve())]

    return subprocess.Popen(
        command,
        cwd=str(runner_dir),
        close_fds=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
