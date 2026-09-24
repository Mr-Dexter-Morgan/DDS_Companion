from __future__ import annotations

import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TARGETS = (
    ROOT / "build" / "pyinstaller-app",
    ROOT / "build" / "pyinstaller-launcher",
    ROOT / "build" / "pyinstaller-updater",
    ROOT / "build" / "artifacts",
    ROOT / "dist" / "DDS",
    ROOT / "dist" / "release",
)


def remove_tree(path: Path, *, attempts: int = 60, delay_seconds: float = 0.25) -> None:
    last_error: OSError | None = None
    for attempt in range(1, attempts + 1):
        if not path.exists():
            return
        try:
            shutil.rmtree(path)
        except OSError as exc:
            last_error = exc
        if not path.exists():
            return
        if attempt < attempts:
            time.sleep(delay_seconds)
    detail = f": {last_error}" if last_error is not None else ""
    raise RuntimeError(
        f"could not clean build target after {attempts} attempts: {path}{detail}"
    )


def main() -> int:
    for target in TARGETS:
        remove_tree(target)
        print(f"CLEAN={target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
