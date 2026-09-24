from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator


def iter_regular_files(root: str | Path) -> Iterator[Path]:
    """Yield regular files while tolerating concurrent filesystem pruning.

    Media maintenance may delete empty shard directories while statistics or a
    second maintenance pass is enumerating them. Every filesystem probe is a
    race boundary: an OSError means the entry changed and should be skipped,
    never that the archive runtime should stop.
    """
    stack = [Path(root)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                snapshot = list(entries)
        except OSError:
            continue

        for entry in snapshot:
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    yield Path(entry.path)
            except OSError:
                continue


def iter_directories(root: str | Path) -> Iterator[Path]:
    """Yield directories without failing when another thread removes one."""
    stack = [Path(root)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                snapshot = list(entries)
        except OSError:
            continue

        for entry in snapshot:
            try:
                if entry.is_dir(follow_symlinks=False):
                    child = Path(entry.path)
                    yield child
                    stack.append(child)
            except OSError:
                continue
