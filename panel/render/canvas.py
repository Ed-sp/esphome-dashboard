"""Drawing surface for a 1-bit e-paper panel.

The image is mode "1" throughout, which makes PIL select FreeType's monochrome
rasteriser for text: hinted, hard-edged, no antialiasing. That is what we want --
there is no grey on the panel to antialias into, so thresholding an antialiased
render would only smear the stems.

Two consequences worth remembering when editing the layout:

*   There is no opacity. A "light" hairline is a line drawn on alternate pixels,
    not a faint one. `rule(..., tone="light")` does that.
*   Shading is ordered dithering. `dither_fill` tiles a 4x4 pattern at one of four
    densities (6 / 12 / 25 / 50%), optionally clipped to an arbitrary polygon.

Coordinates match the approved SVG mockup one-to-one, and text y-positions are
*baselines*, so the numbers in `geometry.py` can be read straight off the design.
"""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageChops, ImageDraw, ImageFont

from . import fonts

BLACK = 0
WHITE = 255

# Ordered dither tiles, 4x4, in increasing density. Index 0 is "no ink".
_TILES: list[list[tuple[int, int]]] = [
    [],
    [(0, 0)],
    [(0, 0), (2, 2)],
    [(0, 0), (2, 2), (2, 0), (0, 2)],
    [(0, 0), (2, 2), (2, 0), (0, 2), (1, 1), (3, 3), (3, 1), (1, 3)],
]

# Rain probability (%) -> dither level. Below 10% nothing is drawn at all, so a
# dry day leaves the graph band clean rather than faintly speckled.
_RAIN_BREAKS = [(10, 0), (30, 1), (50, 2), (70, 3)]


def rain_level(probability: float | None) -> int:
    if probability is None:
        return 0
    for threshold, level in _RAIN_BREAKS:
        if probability < threshold:
            return level
    return 4


@dataclass(frozen=True)
class Text:
    """A resolved text style. Sizes are pixels; tracking is extra px per gap."""

    role: str = "sans"
    size: int = 12
    tracking: float = 0.0

    @property
    def font(self) -> ImageFont.FreeTypeFont:
        return fonts.font(self.role, self.size)


class Canvas:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.image = Image.new("1", (width, height), WHITE)
        self.draw = ImageDraw.Draw(self.image)
        self._tile_cache: dict[int, Image.Image] = {}

    # ------------------------------------------------------------------ text

    # Mode "1" images make PIL select FreeType's monochrome rasteriser, which
    # rounds every glyph advance up to a whole pixel. Measuring with the default
    # (antialiased) metrics under-reports by a fraction per character -- about
    # 50px across a line of body text -- so every measurement has to ask for the
    # same mode the text will actually be drawn in.
    _FONT_MODE = "1"

    def measure(self, text: str, style: Text) -> float:
        width = style.font.getlength(text, mode=self._FONT_MODE)
        if style.tracking and len(text) > 1:
            width += style.tracking * (len(text) - 1)
        return width

    def text(
        self,
        x: float,
        y: float,
        text: str,
        style: Text,
        *,
        anchor: str = "left",
        fill: int = BLACK,
    ) -> float:
        """Draw `text` with its baseline at `y`. Returns the x where it ended.

        `anchor` is one of "left", "center", "right" and refers to `x`.
        """
        if not text:
            return x
        width = self.measure(text, style)
        if anchor == "center":
            x -= width / 2
        elif anchor == "right":
            x -= width

        if not style.tracking:
            self.draw.text((x, y), text, font=style.font, fill=fill, anchor="ls")
            return x + width

        # Tracked text has to be stepped character by character; PIL has no
        # letter-spacing. Used for the small-caps eyebrows, where the spacing is
        # doing real work in the design.
        cursor = x
        for char in text:
            self.draw.text((cursor, y), char, font=style.font, fill=fill, anchor="ls")
            cursor += style.font.getlength(char, mode=self._FONT_MODE) + style.tracking
        return cursor - style.tracking

    def wrap(self, text: str, style: Text, max_width: float, max_lines: int) -> list[str]:
        """Greedy word wrap. Overflow is truncated with an ellipsis on the last line."""
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and self.measure(candidate, style) > max_width:
                lines.append(current)
                current = word
                if len(lines) == max_lines:
                    break
            else:
                current = candidate
        if current and len(lines) < max_lines:
            lines.append(current)

        if len(lines) == max_lines and (len(lines) < len(words)):
            remaining = " ".join(words[sum(len(l.split()) for l in lines):])
            if remaining:
                lines[-1] = self.ellipsize(lines[-1] + " " + remaining, style, max_width)
        return lines

    def ellipsize(self, text: str, style: Text, max_width: float) -> str:
        if self.measure(text, style) <= max_width:
            return text
        ellipsis = "…"
        trimmed = text
        while trimmed and self.measure(trimmed + ellipsis, style) > max_width:
            trimmed = trimmed[:-1]
        return trimmed.rstrip() + ellipsis

    # ----------------------------------------------------------------- lines

    def rule(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        *,
        weight: int = 1,
        tone: str = "solid",
    ) -> None:
        """A horizontal or vertical rule.

        `tone="light"` draws on alternate pixels, standing in for the 22%-opacity
        hairlines in the design. `tone="dashed"` is 1 on, 3 off, used for the
        sunrise and sunset markers.
        """
        if tone == "solid":
            self.draw.line([(x0, y0), (x1, y1)], fill=BLACK, width=weight)
            return

        step, run = (2, 1) if tone == "light" else (4, 1)
        if y0 == y1:
            for x in range(int(x0), int(x1), step):
                self.draw.rectangle(
                    [x, int(y0), x + run - 1, int(y0) + weight - 1], fill=BLACK
                )
        else:
            for y in range(int(y0), int(y1), step):
                self.draw.rectangle(
                    [int(x0), y, int(x0) + weight - 1, y + run - 1], fill=BLACK
                )

    # ---------------------------------------------------------------- shapes

    def box(self, x0: float, y0: float, x1: float, y1: float, *, weight: int = 1) -> None:
        self.draw.rectangle([x0, y0, x1, y1], outline=BLACK, width=weight)

    def filled(self, x0: float, y0: float, x1: float, y1: float, fill: int = BLACK) -> None:
        self.draw.rectangle([x0, y0, x1, y1], fill=fill)

    def polyline(self, points: list[tuple[float, float]], *, weight: int = 2) -> None:
        self.draw.line(points, fill=BLACK, width=weight, joint="curve")
        # `joint="curve"` rounds the interior joints but leaves the two ends square;
        # cap them so the temperature trace does not look clipped at the edges.
        radius = weight / 2
        for x, y in (points[0], points[-1]):
            self.draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=BLACK)

    # --------------------------------------------------------------- shading

    def _tile(self, level: int) -> Image.Image:
        """A full-canvas image of the dither pattern at `level`, cached."""
        if level not in self._tile_cache:
            tile = Image.new("1", (4, 4), 0)
            for dx, dy in _TILES[level]:
                tile.putpixel((dx, dy), 1)
            full = Image.new("1", (self.width, self.height), 0)
            for y in range(0, self.height, 4):
                for x in range(0, self.width, 4):
                    full.paste(tile, (x, y))
            self._tile_cache[level] = full
        return self._tile_cache[level]

    def dither_fill(
        self,
        level: int,
        *,
        clip: list[tuple[float, float]] | None = None,
        rect: tuple[float, float, float, float] | None = None,
    ) -> None:
        """Lay down dither at `level`, limited to `clip` polygon and/or `rect`."""
        if level <= 0:
            return
        mask = self._tile(level)

        if clip is not None:
            shape = Image.new("1", (self.width, self.height), 0)
            ImageDraw.Draw(shape).polygon([(round(x), round(y)) for x, y in clip], fill=1)
            mask = ImageChops.logical_and(mask, shape)

        if rect is not None:
            window = Image.new("1", (self.width, self.height), 0)
            x0, y0, x1, y1 = rect
            ImageDraw.Draw(window).rectangle([round(x0), round(y0), round(x1), round(y1)], fill=1)
            mask = ImageChops.logical_and(mask, window)

        self.image.paste(BLACK, (0, 0), mask)

    # ---------------------------------------------------------------- output

    def to_png_bytes(self) -> bytes:
        from io import BytesIO

        buffer = BytesIO()
        # optimize=True costs a few ms and shaves a useful chunk off the transfer,
        # which matters because the dither patterns compress poorly.
        self.image.save(buffer, format="PNG", optimize=True, bits=1)
        return buffer.getvalue()
