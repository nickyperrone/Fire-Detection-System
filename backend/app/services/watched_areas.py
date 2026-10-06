"""Where the satellites are read: the region plus a box around every field outside it
(docs/02-architecture.md)."""

from sqlalchemy import text
from sqlalchemy.orm import Session

Box = tuple[float, float, float, float]  # west, south, east, north

FIELD_BOXES_SQL = text("""
    SELECT ST_XMin(geom) AS west, ST_YMin(geom) AS south,
           ST_XMax(geom) AS east, ST_YMax(geom) AS north
    FROM territory
    WHERE parent_id IS NULL
""")


def _touch(a: Box, b: Box) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def merge_boxes(boxes: list[Box]) -> list[Box]:
    """Boxes that touch become the one box around both, until none touch."""
    merged: list[Box] = []
    for box in boxes:
        while True:
            touching = [m for m in merged if _touch(m, box)]
            if not touching:
                break
            for m in touching:
                merged.remove(m)
            box = (
                min(box[0], *(m[0] for m in touching)),
                min(box[1], *(m[1] for m in touching)),
                max(box[2], *(m[2] for m in touching)),
                max(box[3], *(m[3] for m in touching)),
            )
        merged.append(box)
    return sorted(merged)


def watched_areas(session: Session, thresholds: dict) -> list[Box]:
    margin = thresholds["region"]["field_margin_degrees"]
    fields = [
        (r.west - margin, r.south - margin, r.east + margin, r.north + margin)
        for r in session.execute(FIELD_BOXES_SQL)
    ]
    return merge_boxes([tuple(thresholds["region"]["bbox"]), *fields])
