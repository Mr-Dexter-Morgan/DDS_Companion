from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from .cancel import CancelCheck, UpdateCancelled, raise_if_cancelled
from .integrity import PackageInventory, PackageValidationError, validate_update_zip, verify_sha256
from .models import ReleaseManifest
from .payload import INSTALL_MANIFEST_NAME, InstallManifest
from .paths import UpdaterPaths, ensure_updater_dirs
from .space import require_free_space

SUPPORTED_UPDATER_PROTOCOL = 1
SUPPORTED_PACKAGE_FORMAT = 1


class StageError(RuntimeError):
    pass


class PackageStager:
    def __init__(self, paths: UpdaterPaths):
        self.paths = paths

    def stage(
        self,
        package_path: str | Path,
        manifest: ReleaseManifest,
        *,
        cancel_check: CancelCheck | None = None,
    ) -> tuple[Path, PackageInventory]:
        raise_if_cancelled(cancel_check)
        manifest.validate()
        if manifest.updater_protocol != SUPPORTED_UPDATER_PROTOCOL:
            raise StageError("unsupported updater protocol")
        if manifest.package_format != SUPPORTED_PACKAGE_FORMAT:
            raise StageError("unsupported package format")

        source = Path(package_path)
        if not source.is_file():
            raise StageError("update package does not exist")
        if source.stat().st_size != manifest.size_bytes:
            raise StageError("update package size does not match manifest")
        if not verify_sha256(source, manifest.sha256):
            raise StageError("update package SHA-256 does not match manifest")

        try:
            inventory = validate_update_zip(
                source,
                required_files=("DDSApp.exe", INSTALL_MANIFEST_NAME),
            )
        except PackageValidationError as exc:
            raise StageError(str(exc)) from exc

        raise_if_cancelled(cancel_check)
        ensure_updater_dirs(self.paths)
        require_free_space(self.paths.staging, inventory.uncompressed_bytes)

        target = self.paths.staging / manifest.version
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=False)

        try:
            with zipfile.ZipFile(source, "r") as archive:
                for info in archive.infolist():
                    raise_if_cancelled(cancel_check)
                    rel = Path(info.filename.replace("\\", "/"))
                    destination = target.joinpath(*rel.parts)
                    if info.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info, "r") as source_handle, destination.open("wb") as output:
                        while True:
                            raise_if_cancelled(cancel_check)
                            chunk = source_handle.read(1024 * 1024)
                            if not chunk:
                                break
                            output.write(chunk)

            raise_if_cancelled(cancel_check)
            install_manifest = InstallManifest.load(target / INSTALL_MANIFEST_NAME)
            if install_manifest.version != manifest.version:
                raise StageError("install manifest version does not match release manifest")
            install_manifest.verify(target)
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise

        return target, inventory
