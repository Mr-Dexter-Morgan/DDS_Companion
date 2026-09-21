from __future__ import annotations


def human_size(value: int | float | None) -> str:
    if value is None:
        return "—"
    number = float(value)
    sign = "-" if number < 0 else ""
    number = abs(number)
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if number < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{sign}{int(number)} B"
            return f"{sign}{number:.2f} {unit}"
        number /= 1024
    return f"{sign}{number:.2f} TB"


def human_storage_delta(value: int | float | None, *, sentence_case: bool = True) -> str:
    """Describe session storage movement without a misleading raw +/- sign."""
    if value is None:
        return "Изменение за сессию: —" if sentence_case else "изменение за сессию —"
    number = int(value)
    # Avoid noisy metadata jitter being presented as a meaningful user event.
    if abs(number) < 1024:
        return "Без изменений за сессию" if sentence_case else "без изменений за сессию"
    amount = human_size(abs(number))
    if number < 0:
        return ("Освобождено" if sentence_case else "освобождено") + f" за сессию: {amount}"
    return ("Добавлено" if sentence_case else "добавлено") + f" за сессию: {amount}"
