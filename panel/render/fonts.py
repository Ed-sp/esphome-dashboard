"""Font resolution with per-platform fallback.

The panel is drawn in 1-bit mode, so fonts are rendered by FreeType's monochrome
rasteriser -- hinted, no antialiasing. That makes the choice of face matter more
than usual: humanist sans faces with open counters survive the threshold, geometric
ones close up and turn to mush at 9-10px.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

# Candidate files per role, in preference order. First one that exists wins.
# Windows entries come first for local development; the rest cover a Debian-based
# Home Assistant add-on container.
_CANDIDATES: dict[str, list[str]] = {
    "sans": [
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",  # Alpine, and so the add-on
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Debian
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",  # Arch
    ],
    "sans_bold": [
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ],
    "serif": [
        "C:/Windows/Fonts/georgia.ttf",
        "/usr/share/fonts/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSerif.ttf",
    ],
    "serif_italic": [
        "C:/Windows/Fonts/georgiai.ttf",
        "/usr/share/fonts/dejavu/DejaVuSerif-Italic.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
    ],
}

# The panel is drawn on Windows during development and on Alpine in the add-on,
# so the same layout is set in Arial/Georgia in one place and DejaVu in the
# other. DejaVu is a little wider, which the collect's auto-fit ladder absorbs
# by dropping a size -- but it is worth knowing that the two do not render
# identically, and the add-on is the one that counts.


class FontsMissing(RuntimeError):
    pass


@lru_cache(maxsize=None)
def _resolve(role: str) -> str:
    for candidate in _CANDIDATES[role]:
        if Path(candidate).is_file():
            return candidate
    raise FontsMissing(
        f"No font found for role {role!r} on {sys.platform}. "
        f"Tried: {', '.join(_CANDIDATES[role])}. "
        f"Install a base font package (fonts-dejavu-core on Debian) or add a path "
        f"to _CANDIDATES in panel/render/fonts.py."
    )


@lru_cache(maxsize=None)
def font(role: str, size: int) -> ImageFont.FreeTypeFont:
    """A cached font for `role` at `size` pixels."""
    return ImageFont.truetype(_resolve(role), size)


def available() -> dict[str, str | None]:
    """Which face each role resolved to -- for the preview page's diagnostics."""
    out: dict[str, str | None] = {}
    for role in _CANDIDATES:
        try:
            out[role] = _resolve(role)
        except FontsMissing:
            out[role] = None
    return out
