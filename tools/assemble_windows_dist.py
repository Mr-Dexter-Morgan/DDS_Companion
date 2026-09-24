from __future__ import annotations

import json
import shutil
import sys
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


def zip_tree(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted((item for item in source.rglob("*") if item.is_file()), key=lambda p: str(p).casefold()):
            archive.write(path, path.relative_to(source).as_posix())


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

    shutil.rmtree(FINAL, ignore_errors=True)
    shutil.rmtree(RELEASE, ignore_errors=True)
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
