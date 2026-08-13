"""Vector icons drawn with Pillow primitives.

Deliberately not a font. An icon font would mean shipping and version-pinning a
TTF, and would still have to be declared glyph-by-glyph if the layout ever moved
back to ESPHome lambdas. These are a few dozen lines of arithmetic instead, and
they scale to any size the layout asks for.

Each icon is authored in a 24x24 coordinate space, rendered 4x oversampled into
an 8-bit tile, then downsampled and thresholded. Oversampling is what keeps the
curves from going to staircases at the 14px sizes used in the forecast list.

Outlined shapes that are unions of circles and rectangles -- clouds, mainly --
are drawn by filling the union black and then filling an inset copy white. That
gives a clean silhouette outline with no internal seams, and it makes occlusion
free: a sun drawn before a cloud is correctly hidden behind it.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

SS = 4  # oversampling factor
_UNIT = 24.0
_STROKE = 1.9  # in 24-space units, matching the design


class _Pen:
    def __init__(self, draw: ImageDraw.ImageDraw, k: float):
        self.d = draw
        self.k = k
        self.sw = _STROKE * k
        self.w = _STROKE  # stroke width expressed back in 24-space

    def _p(self, x: float, y: float) -> tuple[float, float]:
        return (x * self.k, y * self.k)

    def line(self, x1: float, y1: float, x2: float, y2: float, ink: int = 0) -> None:
        self.d.line([self._p(x1, y1), self._p(x2, y2)], fill=ink, width=round(self.sw))
        r = self.sw / 2
        for x, y in ((x1, y1), (x2, y2)):
            px, py = self._p(x, y)
            self.d.ellipse([px - r, py - r, px + r, py + r], fill=ink)

    def ring(self, cx: float, cy: float, r: float, ink: int = 0) -> None:
        px, py = self._p(cx, cy)
        rr = r * self.k
        self.d.ellipse([px - rr, py - rr, px + rr, py + rr], outline=ink, width=round(self.sw))

    def disc(self, cx: float, cy: float, r: float, ink: int = 0) -> None:
        px, py = self._p(cx, cy)
        rr = r * self.k
        self.d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=ink)

    def rect(self, x0: float, y0: float, x1: float, y1: float, ink: int = 0) -> None:
        self.d.rectangle([self._p(x0, y0), self._p(x1, y1)], fill=ink)

    def box(self, x0: float, y0: float, x1: float, y1: float, radius: float = 0.0) -> None:
        if radius:
            self.d.rounded_rectangle(
                [self._p(x0, y0), self._p(x1, y1)],
                radius=radius * self.k,
                outline=0,
                width=round(self.sw),
            )
        else:
            self.d.rectangle([self._p(x0, y0), self._p(x1, y1)], outline=0, width=round(self.sw))

    def poly(self, points: list[tuple[float, float]], ink: int = 0) -> None:
        self.d.polygon([self._p(x, y) for x, y in points], fill=ink)

    def poly_outline(self, points: list[tuple[float, float]]) -> None:
        closed = points + [points[0]]
        for (x1, y1), (x2, y2) in zip(closed, closed[1:]):
            self.line(x1, y1, x2, y2)

    def arc(self, cx: float, cy: float, r: float, start: float, end: float) -> None:
        px, py = self._p(cx, cy)
        rr = r * self.k
        self.d.arc([px - rr, py - rr, px + rr, py + rr], start, end, fill=0, width=round(self.sw))


# --------------------------------------------------------------------- parts


def _cloud(p: _Pen, dx: float = 0.0, dy: float = 0.0, scale: float = 1.0) -> None:
    """Outlined cloud: union of two discs and a base slab, minus an inset copy."""
    w = p.w

    def at(x: float, y: float) -> tuple[float, float]:
        return (12 + (x - 12) * scale + dx, 12 + (y - 12) * scale + dy)

    small = (*at(8.6, 13.2), 4.7 * scale)
    big = (*at(14.2, 11.7), 5.9 * scale)
    left, top = at(8.6, 13.0)
    right, bottom = at(20.1, 18.2)

    for cx, cy, r in (small, big):
        p.disc(cx, cy, r)
    p.rect(left, top, right, bottom)

    for cx, cy, r in (small, big):
        p.disc(cx, cy, r - w, ink=255)
    p.rect(left, top, right - w, bottom - w, ink=255)


def _sun_rays(p: _Pen, cx: float, cy: float, r: float, count: int = 8) -> None:
    import math

    inner, outer = r + 1.3, r + 2.9
    for i in range(count):
        a = math.radians(i * (360 / count))
        p.line(
            cx + inner * math.cos(a),
            cy + inner * math.sin(a),
            cx + outer * math.cos(a),
            cy + outer * math.sin(a),
        )


def _drops(p: _Pen, length: float = 3.1, y: float = 18.4) -> None:
    for x in (8.8, 13.8, 18.8):
        p.line(x, y, x - 1.1, y + length)


# -------------------------------------------------------------------- icons


def _sun(p: _Pen) -> None:
    p.ring(12, 12, 4.4)
    _sun_rays(p, 12, 12, 4.4)


def _moon(p: _Pen) -> None:
    # A crescent outline is just two arcs of equal-radius circles meeting at their
    # intersection points. Both centres and the angles below are precomputed for
    # R=8.4 with the bite offset 3.6 up and left; changing either means redoing them.
    p.arc(12.4, 12.4, 8.4, 297.4, 152.6)
    p.arc(8.8, 8.8, 8.4, 332.6, 117.4)


def _cloudy(p: _Pen) -> None:
    _cloud(p, dy=-0.5)


def _partly(p: _Pen) -> None:
    p.ring(8.5, 7.3, 3.1)
    _sun_rays(p, 8.5, 7.3, 3.1, count=8)
    _cloud(p, dy=1.4, scale=0.94)


def _partly_night(p: _Pen) -> None:
    p.disc(8.6, 7.2, 3.6)
    p.disc(8.6 - 1.5, 7.2 - 1.5, 3.6, ink=255)
    _cloud(p, dy=1.4, scale=0.94)


def _rainy(p: _Pen) -> None:
    _cloud(p, dy=-2.4, scale=0.9)
    _drops(p, length=3.0, y=17.6)


def _pouring(p: _Pen) -> None:
    _cloud(p, dy=-3.0, scale=0.9)
    for x in (8.4, 12.0, 15.6, 19.2):
        p.line(x, 16.6, x - 1.4, 21.2)


def _stormy(p: _Pen) -> None:
    _cloud(p, dy=-3.0, scale=0.9)
    p.poly([(13.8, 14.6), (9.6, 20.2), (12.4, 20.2), (10.9, 23.4), (15.6, 17.4), (12.8, 17.4)])


def _snowy(p: _Pen) -> None:
    _cloud(p, dy=-2.4, scale=0.9)
    for x in (9.0, 14.0, 19.0):
        p.disc(x, 19.6, 1.15)


def _foggy(p: _Pen) -> None:
    _cloud(p, dy=-3.2, scale=0.88)
    p.line(5.0, 18.6, 19.0, 18.6)
    p.line(7.4, 21.6, 16.6, 21.6)


def _windy(p: _Pen) -> None:
    p.line(3.0, 9.0, 14.0, 9.0)
    p.line(14.0, 9.0, 16.6, 6.6)
    p.line(3.0, 14.0, 17.5, 14.0)
    p.line(17.5, 14.0, 20.0, 16.4)
    p.line(6.0, 19.0, 13.0, 19.0)


def _bike(p: _Pen) -> None:
    p.ring(5.6, 16.8, 3.9)
    p.ring(18.4, 16.8, 3.9)
    p.line(5.6, 16.8, 9.3, 8.4)
    p.line(9.3, 8.4, 14.4, 8.4)
    p.line(14.4, 8.4, 18.4, 16.8)
    p.line(9.3, 8.4, 7.1, 8.4)
    p.line(12.4, 8.4, 15.3, 16.8)


def _car(p: _Pen) -> None:
    p.poly_outline([(6.6, 12.0), (8.8, 7.4), (15.2, 7.4), (17.4, 12.0)])
    p.box(3.4, 11.6, 20.6, 16.6, radius=1.4)
    for cx in (7.9, 16.1):
        p.disc(cx, 17.4, 2.4)
        p.disc(cx, 17.4, 2.4 - p.w, ink=255)


def _bin(p: _Pen, recycle: bool = False) -> None:
    p.line(3.6, 6.6, 20.4, 6.6)
    p.line(9.4, 6.6, 9.4, 4.2)
    p.line(9.4, 4.2, 14.6, 4.2)
    p.line(14.6, 4.2, 14.6, 6.6)
    p.line(5.8, 6.6, 7.0, 20.2)
    p.line(7.0, 20.2, 17.0, 20.2)
    p.line(17.0, 20.2, 18.2, 6.6)
    if recycle:
        p.poly_outline([(12.0, 10.0), (15.2, 15.8), (8.8, 15.8)])
    else:
        p.line(10.2, 10.4, 10.2, 16.6)
        p.line(13.8, 10.4, 13.8, 16.6)


def _recycle(p: _Pen) -> None:
    _bin(p, recycle=True)


def _leaf(p: _Pen) -> None:
    import math

    tip, stem = (19.8, 4.2), (4.2, 19.8)

    def lens(bulge: float, shrink: float = 0.0) -> list[tuple[float, float]]:
        (ax, ay), (bx, by) = stem, tip
        length = math.hypot(bx - ax, by - ay)
        ux, uy = (bx - ax) / length, (by - ay) / length
        nx, ny = -uy, ux
        ax, ay = ax + ux * shrink, ay + uy * shrink
        bx, by = bx - ux * shrink, by - uy * shrink
        points: list[tuple[float, float]] = []
        for side in (1, -1):
            steps = range(0, 25) if side == 1 else range(24, -1, -1)
            for i in steps:
                t = i / 24
                swell = bulge * math.sin(math.pi * t)
                points.append(
                    (ax + (bx - ax) * t + nx * side * swell, ay + (by - ay) * t + ny * side * swell)
                )
        return points

    p.poly(lens(3.7))
    p.poly(lens(3.7 - p.w, shrink=p.w), ink=255)
    p.line(*stem, *tip)


def _battery(p: _Pen) -> None:
    p.box(2.4, 7.6, 19.0, 16.4, radius=2.0)
    p.line(21.0, 10.9, 21.0, 13.1)
    p.rect(5.0, 10.0, 7.8, 14.0)


def _spark(p: _Pen) -> None:
    p.poly_outline(
        [(12, 2.8), (14.1, 9.7), (21.0, 11.8), (14.1, 13.9), (12, 20.8), (9.9, 13.9), (3.0, 11.8), (9.9, 9.7)]
    )


def _drop(p: _Pen) -> None:
    p.disc(12, 15, 6.4)
    p.poly([(12, 3.2), (18.0, 15.4), (6.0, 15.4)])


def _clock(p: _Pen) -> None:
    p.ring(12, 12, 8.6)
    p.line(12, 6.6, 12, 12)
    p.line(12, 12, 16.0, 13.8)


_ICONS = {
    "sun": _sun,
    "moon": _moon,
    "cloud": _cloudy,
    "partly": _partly,
    "partly-night": _partly_night,
    "rain": _rainy,
    "pour": _pouring,
    "storm": _stormy,
    "snow": _snowy,
    "fog": _foggy,
    "wind": _windy,
    "bike": _bike,
    "car": _car,
    "bin": lambda p: _bin(p, recycle=False),
    "recycle": _recycle,
    "leaf": _leaf,
    "battery": _battery,
    "spark": _spark,
    "drop": _drop,
    "clock": _clock,
}

# Home Assistant weather states -> icon name. Night variants are chosen by the
# caller, which knows whether the sun is up at that point in the forecast.
_CONDITIONS = {
    "clear-night": "moon",
    "cloudy": "cloud",
    "exceptional": "spark",
    "fog": "fog",
    "hail": "snow",
    "lightning": "storm",
    "lightning-rainy": "storm",
    "partlycloudy": "partly",
    "pouring": "pour",
    "rainy": "rain",
    "snowy": "snow",
    "snowy-rainy": "snow",
    "sunny": "sun",
    "windy": "wind",
    "windy-variant": "wind",
}


def for_condition(condition: str | None, *, night: bool = False) -> str:
    name = _CONDITIONS.get(condition or "", "cloud")
    if night:
        if name == "sun":
            return "moon"
        if name == "partly":
            return "partly-night"
    return name


def names() -> list[str]:
    return sorted(_ICONS)


def render(name: str, size: int) -> Image.Image:
    """A 1-bit mask for `name` at `size` px. Set pixels are where ink goes."""
    if name not in _ICONS:
        raise KeyError(f"Unknown icon {name!r}. Available: {', '.join(names())}")

    big = size * SS
    tile = Image.new("L", (big, big), 255)
    pen = _Pen(ImageDraw.Draw(tile), big / _UNIT)
    _ICONS[name](pen)

    small = tile.resize((size, size), Image.LANCZOS)
    threshold = 128
    mask = small.point(lambda v: 255 if v < threshold else 0, mode="L").convert("1")
    return mask


def paste(target: Image.Image, name: str, x: float, y: float, size: int, *, invert: bool = False) -> None:
    """Stamp an icon onto `target` at top-left (x, y)."""
    mask = render(name, size)
    target.paste(255 if invert else 0, (round(x), round(y)), mask)
