from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from contextlib import nullcontext
from pathlib import Path

from .event_log import UpdateLog
from .journal import JournalEntry, JournalStore
from .lock import UpdateFileLock
from .models import UpdateState
from .payload import INSTALL_MANIFEST_NAME, InstallManifest
from .pointer import (
    CURRENT_POINTER,
    PENDING_UPDATE,
    PREVIOUS_POINTER,
    PendingUpdate,
    VersionPointer,
    read_pointer,
    write_pending,
    write_pointer,
)
from .space import directory_bytes, require_free_space


def wait_for_pid(pid: int, timeout_seconds: int = 60) -> bool:
    if pid <= 0:
        return True
    if sys.platform == "win32":
        SYNCHRONIZE = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if not handle:
            return True
        try:
            result = ctypes.windll.kernel32.WaitForSingleObject(handle, timeout_seconds * 1000)
            return result == 0
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return True
        time.sleep(0.2)
    return False


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DDS external updater")
    parser.add_argument("--application-dir", required=True)
    parser.add_argument("--staged-dir", required=True)
    parser.add_argument("--target-version", required=True)
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--ack-path", required=True)
    parser.add_argument("--resume-state")
    parser.add_argument("--launch-args-file")
    parser.add_argument("--lock-path")
    parser.add_argument("--log-path")
    parser.add_argument("--journal-path")
    return parser


def _write_log(log: UpdateLog | None, event: str, detail: str = "") -> None:
    if log is None:
        return
    try:
        log.write(event, detail)
    except Exception:
        # A broken log target must not strand an otherwise recoverable update.
        pass


def _write_journal(
    journal_path: Path | None,
    state: UpdateState,
    *,
    current_version: str,
    target_version: str,
    detail: str,
) -> None:
    if journal_path is None:
        return
    try:
        JournalStore(journal_path).write(JournalEntry(
            state=state,
            current_version=current_version,
            target_version=target_version,
            detail=detail,
        ))
    except Exception:
        # Recovery metadata must never become the reason an update cannot recover.
        pass


def install_candidate(
    *,
    application_dir: Path,
    staged_dir: Path,
    target_version: str,
    parent_pid: int,
    ack_path: Path,
    resume_state: str | None,
    launch_args: tuple[str, ...] = (),
    lock_path: Path | None = None,
    log_path: Path | None = None,
    journal_path: Path | None = None,
) -> None:
    root = application_dir.resolve()
    staged = staged_dir.resolve()
    log = UpdateLog(log_path) if log_path is not None else None
    lock_context = UpdateFileLock(lock_path) if lock_path is not None else nullcontext()

    current = None
    try:
        with lock_context:
            _write_log(log, "INSTALL_START", f"target={target_version}")
            manifest = InstallManifest.load(staged / INSTALL_MANIFEST_NAME)
            if manifest.version != target_version:
                raise ValueError("staged payload version does not match target version")
            manifest.verify(staged)
            _write_log(log, "PAYLOAD_VERIFIED", f"target={target_version}")

            current = read_pointer(root / CURRENT_POINTER)
            if current.version == target_version:
                raise ValueError("target version is already current")

            _write_journal(
                journal_path,
                UpdateState.WAITING_FOR_EXIT,
                current_version=current.version,
                target_version=target_version,
                detail=f"waiting for DDS pid {parent_pid}",
            )
            # Do not mutate application files while the running DDS process still
            # owns the current version. The staged payload lives outside app root.
            _write_log(log, "WAITING_FOR_EXIT", f"pid={parent_pid}")
            if not wait_for_pid(parent_pid):
                raise TimeoutError("DDS did not exit before update commit")

            _write_journal(
                journal_path,
                UpdateState.BACKING_UP,
                current_version=current.version,
                target_version=target_version,
                detail="preserving current version for transactional rollback",
            )

            versions = root / "versions"
            versions.mkdir(parents=True, exist_ok=True)
            payload_bytes = directory_bytes(staged)
            require_free_space(versions, payload_bytes)
            _write_log(log, "SPACE_OK", f"payload_bytes={payload_bytes}")

            incoming = versions / f".{target_version}.incoming-{uuid.uuid4().hex}"
            target = versions / target_version
            try:
                shutil.copytree(staged, incoming)
                InstallManifest.load(incoming / INSTALL_MANIFEST_NAME).verify(incoming)
                _write_log(log, "CANDIDATE_COPIED", f"target={target_version}")

                # A stale copy of the same candidate is disposable. The current
                # pointer is guaranteed to reference a different version above.
                if target.exists():
                    shutil.rmtree(target)
                os.replace(incoming, target)
            except Exception:
                shutil.rmtree(incoming, ignore_errors=True)
                raise

            _write_journal(
                journal_path,
                UpdateState.PROMOTING,
                current_version=current.version,
                target_version=target_version,
                detail="promoting verified candidate pointer",
            )
            candidate = VersionPointer(target_version, f"versions/{target_version}")
            pending = PendingUpdate(
                previous=current,
                candidate=candidate,
                ack_path=str(ack_path),
                resume_state_path=resume_state,
                launch_args=launch_args,
                timeout_seconds=30,
                journal_path=str(journal_path) if journal_path is not None else None,
                log_path=str(log_path) if log_path is not None else None,
            )
            write_pending(root / PENDING_UPDATE, pending)
            write_pointer(root / CURRENT_POINTER, candidate)
            _write_log(log, "PROMOTED", f"{current.version}->{target_version}")

            launcher = root / "DDS.exe"
            if not launcher.is_file():
                raise FileNotFoundError("DDS launcher is missing")
            subprocess.Popen([str(launcher)], cwd=str(root), close_fds=True)
            _write_log(log, "LAUNCHED_CANDIDATE", f"target={target_version}")
            _write_journal(
                journal_path,
                UpdateState.VERIFYING_STARTUP,
                current_version=target_version,
                target_version=target_version,
                detail="candidate launched; waiting for startup acknowledgement",
            )
    except Exception as exc:
        source_version = current.version if current is not None else "unknown"
        _write_journal(
            journal_path,
            UpdateState.FAILED,
            current_version=source_version,
            target_version=target_version,
            detail=f"{type(exc).__name__}: {exc}",
        )
        _write_log(log, "INSTALL_FAILED", f"{type(exc).__name__}: {exc}")
        raise


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    log_path = Path(args.log_path) if args.log_path else None
    try:
        launch_args: tuple[str, ...] = ()
        if args.launch_args_file:
            payload = json.loads(Path(args.launch_args_file).read_text(encoding="utf-8-sig"))
            if not isinstance(payload, dict) or not isinstance(payload.get("args"), list):
                raise ValueError("launch args file is invalid")
            launch_args = tuple(str(item) for item in payload["args"])
        install_candidate(
            application_dir=Path(args.application_dir),
            staged_dir=Path(args.staged_dir),
            target_version=args.target_version,
            parent_pid=args.parent_pid,
            ack_path=Path(args.ack_path),
            resume_state=args.resume_state,
            launch_args=launch_args,
            lock_path=Path(args.lock_path) if args.lock_path else None,
            log_path=log_path,
            journal_path=Path(args.journal_path) if args.journal_path else None,
        )
        return 0
    except Exception as exc:
        if log_path is not None:
            _write_log(
                UpdateLog(log_path),
                "UPDATER_FAILED",
                f"{type(exc).__name__}: {exc}",
            )
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
