from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from dds_companion.core.settings import CompanionSettings

from .cancel import UpdateCancelled, raise_if_cancelled
from .check_state import CheckStateStore
from .client import UpdateCheckResult, UpdateClient
from .downloader import PackageDownloader
from .event_log import UpdateLog
from .journal import JournalEntry, JournalStore
from .lock import UpdateFileLock
from .models import UpdateState
from .paths import UpdaterPaths
from .space import require_free_space
from .staging import PackageStager

StatusSink = Callable[[dict], None]
SettingsGetter = Callable[[], CompanionSettings]


@dataclass(frozen=True)
class PreparedUpdate:
    version: str
    package_path: Path
    staged_path: Path


class UpdateController:
    """Optional update orchestration isolated from archive/runtime services."""

    def __init__(
        self,
        *,
        paths: UpdaterPaths,
        current_version: str,
        settings_getter: SettingsGetter,
        status_sink: StatusSink,
        client: UpdateClient | None = None,
        downloader: PackageDownloader | None = None,
        stager: PackageStager | None = None,
    ):
        self.paths = paths
        self.current_version = current_version
        self.settings_getter = settings_getter
        self.status_sink = status_sink
        self.client = client or UpdateClient()
        self.downloader = downloader or PackageDownloader()
        self.stager = stager or PackageStager(paths)
        self.check_state = CheckStateStore(paths.check_state)
        self.log = UpdateLog(paths.log)
        self.journal = JournalStore(paths.journal)
        self._operation_lock = threading.Lock()
        self._cancel_event = threading.Event()
        self.available_result: UpdateCheckResult | None = None
        self.prepared: PreparedUpdate | None = None

    def maybe_check_in_background(self) -> bool:
        settings = self.settings_getter()
        if not settings.update_background_check_enabled:
            return False
        if not self.check_state.due(interval_hours=24):
            return False
        return self.check_async(manual=False)

    def check_async(self, *, manual: bool) -> bool:
        if not self._operation_lock.acquire(blocking=False):
            self._emit("BUSY", "Проверка или загрузка обновления уже выполняется.")
            return False
        self._cancel_event.clear()
        thread = threading.Thread(
            target=self._check_worker,
            args=(manual,),
            name="dds-updater-check",
            daemon=True,
        )
        thread.start()
        return True

    def download_async(self) -> bool:
        if self.available_result is None:
            self._emit("ERROR", "Сначала проверьте наличие обновлений.")
            return False
        if not self._operation_lock.acquire(blocking=False):
            self._emit("BUSY", "Проверка или загрузка обновления уже выполняется.")
            return False
        self._cancel_event.clear()
        thread = threading.Thread(
            target=self._download_worker,
            name="dds-updater-download",
            daemon=True,
        )
        thread.start()
        return True

    def cancel_current(self) -> bool:
        if not self._operation_lock.locked():
            return False
        self._cancel_event.set()
        self._emit("CANCELLING", "Отменяю операцию обновления…")
        return True

    def _cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def _mark_cancelled(self, target_version: str | None = None) -> None:
        self._write_journal(
            UpdateState.CANCELLED,
            target_version,
            "operation cancelled by user",
        )
        self._emit("CANCELLED", "Операция обновления отменена.", version=target_version)

    def _claim_process_lock(self) -> UpdateFileLock | None:
        lock = UpdateFileLock(self.paths.lock)
        if lock.acquire():
            return lock
        self._emit("BUSY", "Другой процесс DDS уже выполняет операцию обновления.")
        return None

    def _download_worker(self) -> None:
        process_lock = None
        try:
            process_lock = self._claim_process_lock()
            if process_lock is None:
                return
            result = self.available_result
            if result is None:
                raise RuntimeError("update is no longer available")
            self._download_and_stage(result)
        except UpdateCancelled:
            version = self.available_result.manifest.version if self.available_result and self.available_result.manifest else None
            self._mark_cancelled(version)
        except Exception as exc:
            self._emit("ERROR", f"Загрузка обновления не удалась: {type(exc).__name__}: {exc}")
        finally:
            if process_lock is not None:
                process_lock.release()
            self._operation_lock.release()

    def _check_worker(self, manual: bool) -> None:
        process_lock = None
        check_succeeded = False
        try:
            process_lock = self._claim_process_lock()
            if process_lock is None:
                return
            self._emit("CHECKING", "Проверяю обновления…", manual=manual)
            raise_if_cancelled(self._cancelled)
            # Throttle attempts, not only successful GitHub responses. Otherwise
            # an outage would cause a background request on every DDS launch.
            self.check_state.mark_attempt()
            result = self.client.check(self.current_version, channel="preview")
            raise_if_cancelled(self._cancelled)

            if not result.update_available:
                self.check_state.mark_success()
                check_succeeded = True
                self.available_result = None
                self._emit("CURRENT", "Установлена актуальная версия.", manual=manual)
                return

            self.available_result = result
            descriptor = result.descriptor
            manifest = result.manifest
            if descriptor is None or manifest is None:
                detail = "GitHub сообщил об обновлении без manifest."
                self.check_state.mark_failure(detail)
                self._emit("ERROR", detail)
                return

            self.check_state.mark_success()
            check_succeeded = True
            self._emit(
                "AVAILABLE",
                f"Доступна версия {manifest.version}.",
                version=manifest.version,
                current_version=self.current_version,
                size_bytes=manifest.size_bytes,
                notes=descriptor.notes,
                release_url=descriptor.release_url,
            )
            settings = self.settings_getter()
            if settings.update_auto_download_enabled:
                self._download_and_stage(result)
        except UpdateCancelled:
            self._mark_cancelled()
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            if not check_succeeded:
                try:
                    self.check_state.mark_failure(detail)
                except Exception:
                    # Status persistence must never hide the original update error.
                    pass
            self._emit("ERROR", f"Проверка обновлений не удалась: {detail}")
        finally:
            if process_lock is not None:
                process_lock.release()
            self._operation_lock.release()

    def _download_and_stage(self, result: UpdateCheckResult) -> PreparedUpdate:
        descriptor = result.descriptor
        manifest = result.manifest
        if descriptor is None or manifest is None:
            raise RuntimeError("update result is incomplete")
        asset_url = descriptor.asset_urls.get(manifest.asset)
        if not asset_url:
            raise RuntimeError(f"release asset is missing: {manifest.asset}")

        raise_if_cancelled(self._cancelled)
        self._write_journal(
            UpdateState.DOWNLOADING,
            manifest.version,
            f"downloading {manifest.asset}",
        )
        try:
            # First gate: enough room for the compressed package plus the global
            # updater safety margin. Extraction performs a second, exact check using
            # the ZIP inventory before writing the staged payload.
            require_free_space(self.paths.downloads, manifest.size_bytes)
            self._emit(
                "DOWNLOADING",
                f"Загружаю {manifest.asset}…",
                version=manifest.version,
                current_version=self.current_version,
                size_bytes=manifest.size_bytes,
                notes=descriptor.notes,
            )
            package_path = self.paths.downloads / manifest.asset
            downloaded = self.downloader.download(
                asset_url,
                package_path,
                manifest,
                cancel_check=self._cancelled,
            )
            raise_if_cancelled(self._cancelled)
            self._write_journal(UpdateState.VERIFYING, manifest.version, "verifying staged package")
            self._emit(
                "VERIFYING",
                "Проверяю и подготавливаю пакет…",
                version=manifest.version,
                current_version=self.current_version,
                size_bytes=manifest.size_bytes,
                notes=descriptor.notes,
            )
            staged_path, _inventory = self.stager.stage(
                downloaded,
                manifest,
                cancel_check=self._cancelled,
            )
            prepared = PreparedUpdate(manifest.version, downloaded, staged_path)
            self.prepared = prepared
            self._write_journal(UpdateState.STAGED, manifest.version, "candidate is staged and verified")
            self._emit(
                "STAGED",
                f"Версия {manifest.version} загружена и проверена.",
                version=manifest.version,
                current_version=self.current_version,
                size_bytes=manifest.size_bytes,
                notes=descriptor.notes,
                auto_install=self.settings_getter().update_auto_install_enabled,
            )
            return prepared
        except UpdateCancelled:
            self._write_journal(
                UpdateState.CANCELLED,
                manifest.version,
                "operation cancelled by user",
            )
            raise
        except Exception as exc:
            self._write_journal(
                UpdateState.FAILED,
                manifest.version,
                f"{type(exc).__name__}: {exc}",
            )
            raise

    def _write_journal(self, state: UpdateState, target_version: str | None, detail: str) -> None:
        try:
            self.journal.write(JournalEntry(
                state=state,
                current_version=self.current_version,
                target_version=target_version,
                detail=detail,
            ))
        except Exception:
            # Journal is observability/recovery metadata, never an archive dependency.
            pass

    def _emit(self, state: str, message: str, **extra) -> None:
        # Updater observability is intentionally best-effort: a log failure must
        # never make the archive/runtime layer fail.
        try:
            self.log.write(state, message)
        except Exception:
            pass
        self.status_sink({"state": state, "message": message, **extra})
