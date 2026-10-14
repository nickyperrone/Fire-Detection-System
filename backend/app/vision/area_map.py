"""The affected-area photo sent with an alert (docs/13-notifications.md#the-affected-area-image):
the field, the fires and lightning, the distance to the closest fire, the wind, a scale and north,
over satellite tiles."""

import io
import math
from dataclasses import dataclass, field

import httpx
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry.base import BaseGeometry

TILE = 256
FIELD_GREEN = (74, 222, 128, 255)
FIRE_RED = (239, 68, 68, 255)
LIGHTNING_YELLOW = (250, 204, 21, 255)
WHITE = (255, 255, 255, 255)
SHADOW = (11, 14, 19, 255)
PLATE = (11, 14, 19, 190)


@dataclass
class AreaMap:
    """What to draw: lon/lat points and shapes, and the label of the closest fire's distance."""

    field: BaseGeometry
    lots: list[BaseGeometry] = field(default_factory=list)
    fires: list[tuple[float, float]] = field(default_factory=list)
    lightning: list[tuple[float, float]] = field(default_factory=list)
    # The closest fire and the point of the field nearest to it, with "3,7 km".
    distance: tuple[tuple[float, float], tuple[float, float], str] | None = None
    # Where the wind blows from, in degrees, with its label ("viento 18 km/h").
    wind: tuple[float, str] | None = None


def _world_px(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    size = TILE * 2**zoom
    x = (lon + 180) / 360 * size
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * size
    return x, y


def _zoom_for(box: tuple[float, float, float, float], width: int, height: int, top: int) -> int:
    west, south, east, north = box
    for zoom in range(top, 0, -1):
        x0, y0 = _world_px(west, north, zoom)
        x1, y1 = _world_px(east, south, zoom)
        if x1 - x0 <= width and y1 - y0 <= height:
            return zoom
    return 1


def _meters_per_px(lat: float, zoom: int) -> float:
    return 40_075_016.686 * math.cos(math.radians(lat)) / (TILE * 2**zoom)


def _dashed(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]], fill, width: int):
    dash, gap = 10, 7
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        length = math.hypot(x1 - x0, y1 - y0)
        steps = int(length // (dash + gap)) + 1
        for i in range(steps):
            a = i * (dash + gap) / max(length, 1)
            b = min((i * (dash + gap) + dash) / max(length, 1), 1)
            draw.line(
                [
                    (x0 + (x1 - x0) * a, y0 + (y1 - y0) * a),
                    (x0 + (x1 - x0) * b, y0 + (y1 - y0) * b),
                ],
                fill=fill,
                width=width,
            )


def _label(
    draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, font, anchor: str = "mm"
) -> None:
    left, top, right, bottom = draw.textbbox(xy, text, font=font, anchor=anchor)
    draw.rounded_rectangle((left - 8, top - 5, right + 8, bottom + 5), 6, fill=PLATE)
    draw.text(xy, text, font=font, fill=WHITE, anchor=anchor)


def render(
    area: AreaMap, client: httpx.Client, config: dict, scale_label: str, north_label: str = "N"
) -> bytes:
    """A PNG of the area; tiles that fail to load are left dark rather than failing the alert."""
    width, height = config["width_px"], config["height_px"]
    shapes = [area.field, *area.lots]
    points = [*area.fires, *area.lightning]
    west, south, east, north = area.field.bounds
    for lon, lat in points:
        west, south, east, north = min(west, lon), min(south, lat), max(east, lon), max(north, lat)
    margin_x, margin_y = (east - west) * config["margin"], (north - south) * config["margin"]
    box = (west - margin_x, south - margin_y, east + margin_x, north + margin_y)
    zoom = _zoom_for(box, width, height, config["max_zoom"])

    center = _world_px((box[0] + box[2]) / 2, (box[1] + box[3]) / 2, zoom)
    origin = (center[0] - width / 2, center[1] - height / 2)
    image = Image.new("RGBA", (width, height), (20, 24, 30, 255))
    for tx in range(int(origin[0] // TILE), int((origin[0] + width) // TILE) + 1):
        for ty in range(int(origin[1] // TILE), int((origin[1] + height) // TILE) + 1):
            try:
                response = client.get(config["tiles"].format(z=zoom, x=tx, y=ty), timeout=15)
                response.raise_for_status()
                tile = Image.open(io.BytesIO(response.content)).convert("RGBA")
            except (httpx.HTTPError, OSError):
                continue
            image.paste(tile, (int(tx * TILE - origin[0]), int(ty * TILE - origin[1])))

    def px(lon: float, lat: float) -> tuple[float, float]:
        x, y = _world_px(lon, lat, zoom)
        return x - origin[0], y - origin[1]

    overlay = Image.new("RGBA", image.size)
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.load_default(size=18)
    small = ImageFont.load_default(size=15)

    for i, shape in enumerate(shapes):
        for polygon in getattr(shape, "geoms", [shape]):
            ring = [px(*xy) for xy in polygon.exterior.coords]
            if i == 0:
                draw.polygon(ring, fill=(74, 222, 128, 50))
                draw.line(ring, fill=SHADOW, width=7, joint="curve")
                draw.line(ring, fill=FIELD_GREEN, width=4, joint="curve")
            else:
                _dashed(draw, ring, (255, 255, 255, 170), 2)

    if area.distance:
        fire, nearest, text = area.distance
        start, end = px(*nearest), px(*fire)
        _dashed(draw, [start, end], WHITE, 3)
        _label(draw, ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2), text, font)
    for lon, lat in area.lightning:
        x, y = px(lon, lat)
        bolt = [(-6, -18), (9, -3), (0, 0), (6, 18), (-9, 3), (0, 0)]
        draw.polygon([(x + dx, y + dy) for dx, dy in bolt], fill=LIGHTNING_YELLOW, outline=SHADOW)
    for lon, lat in area.fires:
        x, y = px(lon, lat)
        draw.ellipse((x - 20, y - 20, x + 20, y + 20), fill=(239, 68, 68, 70))
        draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=FIRE_RED, outline=WHITE, width=3)

    # North, top right; the wind arrow under it points where the wind goes.
    draw.text(
        (width - 26, 22),
        north_label,
        font=font,
        fill=WHITE,
        anchor="mm",
        stroke_width=3,
        stroke_fill=SHADOW,
    )
    if area.wind:
        degrees, text = area.wind
        cx, cy = width - 46, 82
        draw.ellipse((cx - 28, cy - 28, cx + 28, cy + 28), fill=PLATE)
        heading = math.radians(degrees + 180)
        dx, dy = math.sin(heading) * 18, -math.cos(heading) * 18
        draw.line([(cx - dx, cy - dy), (cx + dx, cy + dy)], fill=WHITE, width=4)
        left = heading + math.radians(150)
        right = heading - math.radians(150)
        draw.polygon(
            [
                (cx + dx, cy + dy),
                (cx + dx + math.sin(left) * 10, cy + dy - math.cos(left) * 10),
                (cx + dx + math.sin(right) * 10, cy + dy - math.cos(right) * 10),
            ],
            fill=WHITE,
        )
        _label(draw, (width - 22, cy + 46), text, small, anchor="rm")

    # Scale, bottom left: 1 km, or 5 km when 1 km would be too short to read.
    meters = _meters_per_px((box[1] + box[3]) / 2, zoom)
    km = 1 if 1000 / meters >= 60 else 5
    bar = 1000 * km / meters
    label = scale_label.format(km=km)
    plate_right = 48 + bar + draw.textlength(label, font=small)
    draw.rounded_rectangle((14, height - 46, plate_right, height - 14), 6, fill=PLATE)
    draw.line([(26, height - 30), (26 + bar, height - 30)], fill=WHITE, width=4)
    draw.text((36 + bar, height - 30), label, font=small, fill=WHITE, anchor="lm")

    output = io.BytesIO()
    Image.alpha_composite(image, overlay).convert("RGB").save(output, "PNG", optimize=True)
    return output.getvalue()
