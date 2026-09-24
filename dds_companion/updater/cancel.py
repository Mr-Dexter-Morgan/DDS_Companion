from __future__ import annotations

from typing import Callable

CancelCheck = Callable[[], bool]


class UpdateCancelled(RuntimeError):
    """Raised when the user cancels a bounded updater operation."""


def raise_if_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and bool(cancel_check()):
        raise UpdateCancelled("update operation cancelled by user")
