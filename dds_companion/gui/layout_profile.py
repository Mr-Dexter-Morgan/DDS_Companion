from __future__ import annotations


def choose_layout_profile(
    *,
    available_width: int,
    available_height: int,
    logical_dpi: float = 96.0,
    device_pixel_ratio: float = 1.0,
    window_width: int | None = None,
) -> str:
    """Return compact/standard/large from usable screen and density metrics.

    The profile changes layout density and card flow; it deliberately does not
    uniformly scale the whole UI.  Qt reports available geometry in logical
    pixels, so devicePixelRatio is also considered for dense 2K/4K displays.
    """

    aw = max(1, int(available_width))
    ah = max(1, int(available_height))
    ww = max(1, int(window_width or aw))
    dpi = max(72.0, float(logical_dpi or 96.0))
    dpr = max(1.0, float(device_pixel_ratio or 1.0))

    # Small-height Windows laptops are the most constrained case.  Width can
    # also force compact mode after the sidebar has taken its share.
    if ah <= 820 or ww < 1220:
        return "compact"

    physical_w = aw * dpr
    physical_h = ah * dpr
    if (
        aw >= 2300
        or (physical_w >= 2500 and physical_h >= 1350 and (dpr >= 1.25 or dpi >= 120.0))
    ):
        return "large"

    return "standard"
