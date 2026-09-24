from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from dds_companion.updater.event_log import UpdateLog
from dds_companion.updater.journal import JournalEntry, JournalStore
from dds_companion.updater.models import UpdateState
from dds_companion.updater.pointer import (
    CURRENT_POINTER,
    PENDING_UPDATE,
    PREVIOUS_POINTER,
    PendingUpdate,
    VersionPointer,
    read_json,
    read_pointer,
    write_pointer,
)


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _executable(root: Path, pointer: VersionPointer) -> Path:
    pointer.validate()
    path = root.joinpath(*Path(pointer.relative_path).parts) / "DDSApp.exe"
    resolved = path.resolve()
    if root.resolve() not in resolved.parents:
        raise ValueError("version executable escaped application root")
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved


def _spawn(root: Path, pointer: VersionPointer, args: list[str]) -> subprocess.Popen:
    exe = _executable(root, pointer)
    env = os.environ.copy()
    env["DDS_APPLICATION_DIR"] = str(root)
    return subprocess.Popen(
        [str(exe), *args],
        cwd=str(exe.parent),
        env=env,
        close_fds=True,
    )


def _cleanup_versions(root: Path, keep: set[str]) -> None:
    versions = root / "versions"
    if not versions.is_dir():
        return
    for child in versions.iterdir():
        if not child.is_dir() or child.name in keep or child.name.startswith("."):
            continue
        shutil.rmtree(child, ignore_errors=True)


def _recover_orphan_versions(root: Path) -> None:
    """Best-effort cleanup after a crash before/around transactional promotion.

    Only pointer/pending-referenced versions are authoritative. Hidden .incoming
    directories are never authoritative and can be removed after a dead updater.
    Recovery is deliberately non-fatal: cleanup must never prevent DDS startup.
    """
    versions = root / "versions"
    if not versions.is_dir():
        return

    keep: set[str] = set()
    for pointer_name in (CURRENT_POINTER, PREVIOUS_POINTER):
        pointer_path = root / pointer_name
        if not pointer_path.is_file():
            continue
        try:
            keep.add(read_pointer(pointer_path).version)
        except Exception:
            pass

    pending_path = root / PENDING_UPDATE
    if pending_path.is_file():
        try:
            pending = PendingUpdate.from_dict(read_json(pending_path))
            keep.add(pending.previous.version)
            keep.add(pending.candidate.version)
        except Exception:
            # Broken pending is handled by main(); do not trust it for retention.
            pass

    # If no valid authority exists, preserve everything for the normal fallback
    # path rather than guessing which directory is safe.
    if not keep:
        return

    for child in versions.iterdir():
        if not child.is_dir():
            continue
        if child.name.startswith("."):
            _remove_tree_with_retries(child)
            continue
        if child.name not in keep:
            _remove_tree_with_retries(child)


def _pending_log(pending: PendingUpdate, event: str, detail: str = "") -> None:
    if not pending.log_path:
        return
    try:
        UpdateLog(pending.log_path).write(event, detail)
    except Exception:
        pass


def _pending_journal(
    pending: PendingUpdate,
    state: UpdateState,
    *,
    current_version: str,
    detail: str,
) -> None:
    if not pending.journal_path:
        return
    try:
        JournalStore(pending.journal_path).write(JournalEntry(
            state=state,
            current_version=current_version,
            target_version=pending.candidate.version,
            detail=detail,
        ))
    except Exception:
        pass


def _terminate_process_tree(process: subprocess.Popen) -> None:
    """Terminate a candidate and its descendants without touching unrelated DDS."""
    pid = getattr(process, "pid", None)
    if sys.platform == "win32" and isinstance(pid, int) and pid > 0:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass

    if process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        except Exception:
            pass


def _remove_tree_with_retries(path: Path, *, attempts: int = 20, delay_seconds: float = 0.1) -> bool:
    for _attempt in range(max(1, attempts)):
        if not path.exists():
            return True
        try:
            shutil.rmtree(path)
            return True
        except (OSError, PermissionError):
            time.sleep(max(0.0, delay_seconds))
    return not path.exists()


def _rollback_pending(root: Path, pending: PendingUpdate, detail: str) -> int:
    _pending_log(pending, "ROLLBACK_START", detail)
    _pending_journal(
        pending,
        UpdateState.ROLLING_BACK,
        current_version=pending.candidate.version,
        detail=detail,
    )
    write_pointer(root / CURRENT_POINTER, pending.previous)
    Path(root / PENDING_UPDATE).unlink(missing_ok=True)
    candidate_dir = root.joinpath(*Path(pending.candidate.relative_path).parts)
    candidate_removed = _remove_tree_with_retries(candidate_dir)

    keep_versions = {pending.previous.version}
    committed_previous_path = root / PREVIOUS_POINTER
    if committed_previous_path.is_file():
        try:
            committed_previous = read_pointer(committed_previous_path)
            keep_versions.add(committed_previous.version)
        except Exception:
            # A malformed backup pointer is non-authoritative; rollback still
            # restores the known-good version captured in pending.previous.
            pass
    _cleanup_versions(root, keep_versions)
    if not candidate_removed:
        _pending_log(
            pending,
            "CLEANUP_DEFERRED",
            f"failed candidate directory is still locked: {candidate_dir}",
        )

    try:
        _spawn(root, pending.previous, list(pending.launch_args))
    except Exception as exc:
        failure = (
            f"rollback pointer restored to {pending.previous.version}, "
            f"but relaunch failed: {type(exc).__name__}: {exc}"
        )
        _pending_journal(
            pending,
            UpdateState.FAILED,
            current_version=pending.previous.version,
            detail=failure,
        )
        _pending_log(pending, "ROLLBACK_RELAUNCH_FAILED", failure)
        return 11

    _pending_journal(
        pending,
        UpdateState.FAILED,
        current_version=pending.previous.version,
        detail=f"rolled back to {pending.previous.version}: {detail}",
    )
    _pending_log(
        pending,
        "ROLLBACK_COMPLETE",
        f"{pending.candidate.version}->{pending.previous.version}: {detail}",
    )
    return 10


def _launch_pending(root: Path, pending: PendingUpdate, passthrough: list[str]) -> int:
    ack = Path(pending.ack_path)
    ack.unlink(missing_ok=True)
    args = list(pending.launch_args)
    args += ["--update-ack", str(ack)]
    if pending.resume_state_path:
        args += ["--update-resume-state", pending.resume_state_path]

    try:
        candidate = _spawn(root, pending.candidate, args)
    except Exception as exc:
        return _rollback_pending(
            root,
            pending,
            f"candidate could not start: {type(exc).__name__}: {exc}",
        )

    deadline = time.monotonic() + pending.timeout_seconds
    while time.monotonic() < deadline:
        if ack.is_file():
            # Commit is idempotent. Rewriting current.json here also repairs the
            # power-loss window where pending_update.json reached disk but the
            # external updater crashed before current.json was switched.
            write_pointer(root / CURRENT_POINTER, pending.candidate)
            # previous.json must describe the immediate previous *successful*
            # version, never a candidate that has not passed startup health.
            write_pointer(root / PREVIOUS_POINTER, pending.previous)
            Path(root / PENDING_UPDATE).unlink(missing_ok=True)
            _cleanup_versions(root, {pending.candidate.version, pending.previous.version})
            _pending_journal(
                pending,
                UpdateState.COMPLETE,
                current_version=pending.candidate.version,
                detail="candidate startup acknowledged",
            )
            _pending_log(
                pending,
                "STARTUP_CONFIRMED",
                f"current={pending.candidate.version}",
            )
            return 0
        if candidate.poll() is not None:
            break
        time.sleep(0.2)

    _terminate_process_tree(candidate)

    return _rollback_pending(
        root,
        pending,
        "candidate exited or did not acknowledge startup before timeout",
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    root = application_root()
    pending_path = root / PENDING_UPDATE

    # Crash recovery is maintenance only. It cannot become a prerequisite for
    # launching the known-good application.
    try:
        _recover_orphan_versions(root)
    except Exception:
        pass

    if pending_path.is_file():
        try:
            pending = PendingUpdate.from_dict(read_json(pending_path))
            return _launch_pending(root, pending, args)
        except Exception:
            # A broken pending marker must not strand an otherwise runnable current version.
            pending_path.unlink(missing_ok=True)

    try:
        current = read_pointer(root / CURRENT_POINTER)
        _spawn(root, current, args)
        return 0
    except Exception:
        previous_path = root / PREVIOUS_POINTER
        if previous_path.is_file():
            previous = read_pointer(previous_path)
            write_pointer(root / CURRENT_POINTER, previous)
            _spawn(root, previous, args)
            return 0
        raise


if __name__ == "__main__":
    raise SystemExit(main())
