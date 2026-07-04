from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT / "assets"
PNG_PATH = ASSETS_DIR / "app_icon.png"
ICO_PATH = ASSETS_DIR / "app_icon.ico"


def rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    value = hex_color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha


def blend(dst: tuple[int, int, int, int], src: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    sr, sg, sb, sa = src
    dr, dg, db, da = dst
    a = sa / 255
    inv = 1 - a
    out_a = int(sa + da * inv)
    if out_a <= 0:
        return 0, 0, 0, 0
    return (
        int(sr * a + dr * inv),
        int(sg * a + dg * inv),
        int(sb * a + db * inv),
        out_a,
    )


def lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def rounded_rect_contains(x: float, y: float, left: float, top: float, right: float, bottom: float, radius: float) -> bool:
    if left + radius <= x <= right - radius and top <= y <= bottom:
        return True
    if left <= x <= right and top + radius <= y <= bottom - radius:
        return True
    for cx, cy in (
        (left + radius, top + radius),
        (right - radius, top + radius),
        (left + radius, bottom - radius),
        (right - radius, bottom - radius),
    ):
        if (x - cx) ** 2 + (y - cy) ** 2 <= radius**2:
            return True
    return False


def point_in_poly(x: float, y: float, points: list[tuple[float, float]]) -> bool:
    inside = False
    j = len(points) - 1
    for i, (xi, yi) in enumerate(points):
        xj, yj = points[j]
        if (yi > y) != (yj > y):
            x_intersect = (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
            if x < x_intersect:
                inside = not inside
        j = i
    return inside


def segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    closest_x = ax + t * dx
    closest_y = ay + t * dy
    return math.hypot(px - closest_x, py - closest_y)


class Canvas:
    def __init__(self, size: int) -> None:
        self.size = size
        self.pixels = [(0, 0, 0, 0)] * (size * size)

    def set_pixel(self, x: int, y: int, color: tuple[int, int, int, int]) -> None:
        if 0 <= x < self.size and 0 <= y < self.size:
            idx = y * self.size + x
            self.pixels[idx] = blend(self.pixels[idx], color)

    def fill_rounded_rect(
        self,
        left: float,
        top: float,
        right: float,
        bottom: float,
        radius: float,
        top_color: tuple[int, int, int, int],
        bottom_color: tuple[int, int, int, int] | None = None,
    ) -> None:
        bottom_color = bottom_color or top_color
        x0, y0, x1, y1 = map(int, (left, top, right, bottom))
        for y in range(y0, y1 + 1):
            t = 0 if bottom == top else (y - top) / (bottom - top)
            color = (
                lerp(top_color[0], bottom_color[0], t),
                lerp(top_color[1], bottom_color[1], t),
                lerp(top_color[2], bottom_color[2], t),
                lerp(top_color[3], bottom_color[3], t),
            )
            for x in range(x0, x1 + 1):
                if rounded_rect_contains(x + 0.5, y + 0.5, left, top, right, bottom, radius):
                    self.set_pixel(x, y, color)

    def fill_polygon(self, points: list[tuple[float, float]], color: tuple[int, int, int, int]) -> None:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        for y in range(int(min(ys)), int(max(ys)) + 1):
            for x in range(int(min(xs)), int(max(xs)) + 1):
                if point_in_poly(x + 0.5, y + 0.5, points):
                    self.set_pixel(x, y, color)

    def stroke_line(self, start: tuple[float, float], end: tuple[float, float], width: float, color: tuple[int, int, int, int]) -> None:
        ax, ay = start
        bx, by = end
        pad = int(width + 2)
        for y in range(int(min(ay, by)) - pad, int(max(ay, by)) + pad + 1):
            for x in range(int(min(ax, bx)) - pad, int(max(ax, bx)) + pad + 1):
                if segment_distance(x + 0.5, y + 0.5, ax, ay, bx, by) <= width / 2:
                    self.set_pixel(x, y, color)


def render(size: int, scale: int = 4) -> list[tuple[int, int, int, int]]:
    s = size * scale
    c = Canvas(s)
    m = s / 256

    c.fill_rounded_rect(12 * m, 12 * m, 244 * m, 244 * m, 48 * m, rgba("#12233a"), rgba("#155e75"))
    c.fill_rounded_rect(42 * m, 34 * m, 210 * m, 222 * m, 19 * m, rgba("#000000", 58))
    c.fill_rounded_rect(36 * m, 28 * m, 204 * m, 216 * m, 18 * m, rgba("#f8fbff"), rgba("#edf5fb"))

    c.fill_polygon([(164 * m, 28 * m), (204 * m, 68 * m), (164 * m, 68 * m)], rgba("#d8e7f0"))
    c.fill_polygon([(164 * m, 28 * m), (204 * m, 68 * m), (204 * m, 58 * m), (174 * m, 28 * m)], rgba("#ffffff", 150))

    accent = rgba("#14b8a6")
    dark = rgba("#133247")
    c.fill_rounded_rect(58 * m, 68 * m, 182 * m, 82 * m, 7 * m, rgba("#c9dce8"))
    c.fill_rounded_rect(58 * m, 96 * m, 148 * m, 108 * m, 6 * m, rgba("#d6e4ec"))

    width = 17 * m
    c.stroke_line((61 * m, 172 * m), (61 * m, 119 * m), width, dark)
    c.stroke_line((61 * m, 119 * m), (88 * m, 153 * m), width, dark)
    c.stroke_line((88 * m, 153 * m), (115 * m, 119 * m), width, dark)
    c.stroke_line((115 * m, 119 * m), (115 * m, 172 * m), width, dark)

    c.stroke_line((154 * m, 118 * m), (154 * m, 169 * m), 16 * m, accent)
    c.fill_polygon([(132 * m, 154 * m), (176 * m, 154 * m), (154 * m, 184 * m)], accent)

    c.fill_rounded_rect(44 * m, 198 * m, 196 * m, 207 * m, 4 * m, rgba("#14b8a6", 210))

    out: list[tuple[int, int, int, int]] = []
    for y in range(size):
        for x in range(size):
            total = [0, 0, 0, 0]
            for yy in range(scale):
                for xx in range(scale):
                    r, g, b, a = c.pixels[(y * scale + yy) * s + (x * scale + xx)]
                    total[0] += r
                    total[1] += g
                    total[2] += b
                    total[3] += a
            count = scale * scale
            out.append(tuple(v // count for v in total))  # type: ignore[arg-type]
    return out


def png_bytes(size: int, pixels: list[tuple[int, int, int, int]]) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for r, g, b, a in pixels[y * size : (y + 1) * size]:
            raw.extend((r, g, b, a))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def ico_bytes(entries: list[tuple[int, bytes]]) -> bytes:
    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    directory = bytearray()
    images = bytearray()
    for size, data in entries:
        width_byte = 0 if size >= 256 else size
        directory.extend(struct.pack("<BBBBHHII", width_byte, width_byte, 0, 0, 1, 32, len(data), offset))
        images.extend(data)
        offset += len(data)
    return header + bytes(directory) + bytes(images)


def main() -> None:
    ASSETS_DIR.mkdir(exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [(size, png_bytes(size, render(size))) for size in sizes]
    PNG_PATH.write_bytes(images[-1][1])
    ICO_PATH.write_bytes(ico_bytes(images))
    print(f"Created {PNG_PATH}")
    print(f"Created {ICO_PATH}")


if __name__ == "__main__":
    main()
