"""Geometry helpers: build/convert bboxes and polygons, normalize <-> pixels."""

from __future__ import annotations

from .model import BBox, Geometry, Point


def bbox_from_points(points: list[Point]) -> BBox:
    """Axis-aligned bbox enclosing a set of normalized points."""
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    left, top = min(xs), min(ys)
    return BBox(left=left, top=top, width=max(xs) - left, height=max(ys) - top)


def polygon_from_bbox(bbox: BBox) -> list[Point]:
    """Clockwise 4-point polygon from an axis-aligned bbox (TL, TR, BR, BL)."""
    return [
        Point(bbox.left, bbox.top),
        Point(bbox.right, bbox.top),
        Point(bbox.right, bbox.bottom),
        Point(bbox.left, bbox.bottom),
    ]


def geometry_from_points(points: list[Point]) -> Geometry:
    """Build a Geometry (both reps) from normalized polygon points."""
    return Geometry(bbox=bbox_from_points(points), polygon=list(points))


def geometry_from_bbox(bbox: BBox) -> Geometry:
    """Build a Geometry (both reps) from a normalized bbox."""
    return Geometry(bbox=bbox, polygon=polygon_from_bbox(bbox))


def union_geometry(geoms: list[Geometry]) -> Geometry | None:
    """Enclosing Geometry over children. Used when synthesizing/merging levels."""
    boxes = [g.bbox for g in geoms if g is not None]
    if not boxes:
        return None
    left = min(b.left for b in boxes)
    top = min(b.top for b in boxes)
    right = max(b.right for b in boxes)
    bottom = max(b.bottom for b in boxes)
    return geometry_from_bbox(
        BBox(left=left, top=top, width=right - left, height=bottom - top))


def normalize_point(x: float, y: float, width: int, height: int) -> Point:
    """Pixel (x, y) -> normalized Point. Guards against zero-size pages."""
    nx = x / width if width else 0.0
    ny = y / height if height else 0.0
    return Point(nx, ny)


def denormalize_point(p: Point, width: int, height: int) -> tuple[float, float]:
    """Normalized Point -> pixel (x, y)."""
    return (p.x * width, p.y * height)
