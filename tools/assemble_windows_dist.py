from __future__ import annotations

import json
import shutil
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dds_companion import __version__
from dds_companion.updater.integrity import sha256_file
from dds_companion.updater.models import ReleaseManifest
from dds_companion.updater.payload import create_install_manifest, write_install_manifest
from dds_companion.updater.pointer import CURRENT_POINTER, VersionPointer, write_pointer

ARTIFACTS = ROOT / "build" / "artifacts"
FINAL = ROOT / "dist" / "DDS"
RELEASE = ROOT / "dist" / "release"


def remove_tree_with_retries(path: Path, *, attempts: int = 20, delay_seconds: float = 0.1) -> None:
    """Remove build output robustly across transient Windows file locks."""
    for attempt in range(1, max(1, attempts) + 1):
        if not path.exists():
            return
        try:
            shutil.rmtree(path)
            return
        except OSError as exc:
            if attempt >= attempts:
                raise RuntimeError(
                    f"could not clean build output after {attempts} attempts: {path}: {exc}"
                ) from exc
            time.sleep(max(0.0, delay_seconds))


def zip_tree(
    source: Path,
    destination: Path,
    *,
    attempts: int = 8,
    delay_seconds: float = 0.05,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(
        (item for item in source.rglob("*") if item.is_file()),
        key=lambda p: str(p).casefold(),
    )
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            arcname = path.relative_to(source).as_posix()
            for attempt in range(1, max(1, attempts) + 1):
                try:
                    archive.write(path, arcname)
                    break
                except (FileNotFoundError, PermissionError) as exc:
                    if attempt >= attempts:
                        raise RuntimeError(
                            f"could not read build payload after {attempts} attempts: {path}: {exc}"
                        ) from exc
                    time.sleep(max(0.0, delay_seconds))

    with zipfile.ZipFile(destination, "r") as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise RuntimeError(f"ZIP integrity check failed at member: {bad_member}")


def write_sha_file(path: Path) -> Path:
    target = path.with_name(path.name + ".sha256")
    target.write_text(f"{sha256_file(path)}  {path.name}\n", encoding="ascii", newline="\n")
    return target


def main() -> int:
    app_source = ARTIFACTS / "app" / "DDSApp"
    launcher = ARTIFACTS / "bootstrap" / "DDS.exe"
    updater = ARTIFACTS / "bootstrap" / "DDSUpdater.exe"
    for required in (app_source / "DDSApp.exe", launcher, updater):
        if not required.exists():
            raise FileNotFoundError(required)

    remove_tree_with_retries(FINAL)
    remove_tree_with_retries(RELEASE)
    version_dir = FINAL / "versions" / __version__
    version_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(app_source, version_dir)
    write_install_manifest(version_dir, create_install_manifest(version_dir, __version__))

    shutil.copy2(launcher, FINAL / "DDS.exe")
    shutil.copy2(updater, FINAL / "DDSUpdater.exe")
    write_pointer(
        FINAL / CURRENT_POINTER,
        VersionPointer(__version__, f"versions/{__version__}"),
    )

    RELEASE.mkdir(parents=True, exist_ok=True)
    artifact_version = __version__.replace(".dev", "-dev")
    full_zip = RELEASE / f"DDS-{artifact_version}-windows-x64.zip"
    update_zip = RELEASE / f"DDS-{artifact_version}-update.zip"
    zip_tree(FINAL, full_zip)
    zip_tree(version_dir, update_zip)
    write_sha_file(full_zip)
    write_sha_file(update_zip)

    manifest = ReleaseManifest(
        version=__version__,
        channel="preview",
        asset=update_zip.name,
        sha256=sha256_file(update_zip),
        size_bytes=update_zip.stat().st_size,
        updater_protocol=1,
        package_format=1,
    )
    manifest_name = RELEASE / f"DDS-{__version__}-update.json"
    manifest_name.write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print(f"DDS_VERSION={__version__}")
    print(f"DDS_ROOT={FINAL}")
    print(f"FULL_ZIP={full_zip}")
    print(f"UPDATE_ZIP={update_zip}")
    print(f"UPDATE_MANIFEST={manifest_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
