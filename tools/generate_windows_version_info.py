from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dds_companion import __version__
from dds_companion.core.identity import PRODUCT_NAME

BUILD = ROOT / "build"
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


def numeric_version(version: str) -> tuple[int, int, int, int]:
    match = VERSION_RE.match(version)
    if match is None:
        raise ValueError(f"unsupported DDS version for Windows metadata: {version!r}")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch, 0


def u(value: str) -> str:
    return "u" + ascii(str(value))
def render_version_info(*, description: str, internal_name: str, filename: str) -> str:
    numeric = numeric_version(__version__)
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numeric!r},
    prodvers={numeric!r},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'DDS Project'),
         StringStruct(u'FileDescription', {u(description)}),
         StringStruct(u'FileVersion', {u(__version__)}),
         StringStruct(u'InternalName', {u(internal_name)}),
         StringStruct(u'OriginalFilename', {u(filename)}),
         StringStruct(u'ProductName', {u(PRODUCT_NAME)}),
         StringStruct(u'ProductVersion', {u(__version__)})]
      )
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""


def main() -> int:
    BUILD.mkdir(parents=True, exist_ok=True)
    targets = (
        ("windows_app_version_info.txt", "DDS Application Runtime", "DDSApp", "DDSApp.exe"),
        ("windows_launcher_version_info.txt", PRODUCT_NAME, "DDS", "DDS.exe"),
        ("windows_updater_version_info.txt", "DDS Safe Updater", "DDSUpdater", "DDSUpdater.exe"),
    )
    for name, description, internal_name, filename in targets:
        target = BUILD / name
        target.write_text(
            render_version_info(
                description=description,
                internal_name=internal_name,
                filename=filename,
            ),
            encoding="utf-8",
            newline="\n",
        )
        print(f"{target}: {__version__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
