"""
Parse EasyOCR `readtext` output -> neutral Document.

EasyOCR returns a FLAT list of detections, one per detected text box:

    [ [ [[x0,y0],[x1,y1],[x2,y2],[x3,y3]], "Hello world", 0.83 ], ... ]

i.e. [polygon(4 pts, pixels), text, confidence(0-1)]. With paragraph=True the
confidence is dropped, giving 2-element entries. There is NO page, block, or
line hierarchy and NO per-word geometry — a detection is a whole text box, so:

    EasyOCR detection -> Line holding a single Word (text = the box's text)

carrying the box geometry on both. All detections land in one synthetic Block.

The format also has no page dimensions, which we need to normalize. We infer a
page size from the maximum extent of every polygon point; the same extent is
recovered on any emit->parse round-trip, so normalization is stable.

Accepts the bare list, a JSON string of it, or a dict wrapper
{"width": W, "height": H, "results": [...]} when true page dims are known.
"""

from __future__ import annotations

import json

from ..geometry import geometry_from_points
from ..model import Break, Document, Line, Page, Point, Word
from ..synth import wrap_lines_in_block

SOURCE_FORMAT = "easyocr"


def _unwrap(data):
    """Return (detections, width, height). width/height may be 0 (infer)."""
    if isinstance(data, str):
        data = json.loads(data)
    if isinstance(data, dict):
        results = data.get("results") or data.get("detections") or []
        return results, data.get("width", 0) or 0, data.get("height", 0) or 0
    if isinstance(data, list):
        return data, 0, 0
    raise TypeError("easyocr parse expects a detections list, JSON string, or "
                    "{'results': [...]} dict")


def _points(box):
    """[[x,y],...] -> list of raw (x, y) float pairs."""
    pts = []
    for xy in box or []:
        if len(xy) >= 2:
            pts.append((float(xy[0]), float(xy[1])))
    return pts


def _detection(entry):
    """(box_points, text, confidence) from a 2- or 3-element detection."""
    box = entry[0] if len(entry) > 0 else []
    text = entry[1] if len(entry) > 1 else ""
    conf = entry[2] if len(entry) > 2 else None
    return _points(box), (text or ""), conf


def parse(data) -> Document:
    detections, w, h = _unwrap(data)

    parsed = [_detection(e) for e in detections]

    # Fall back to inferred dims per-axis, so a wrapper supplying only one of
    # width/height keeps the value it gave.
    if not w or not h:
        iw, ih = _infer_dims(parsed)
        w = w or iw
        h = h or ih

    doc = Document(source_format=SOURCE_FORMAT)
    page = Page(width=w, height=h, id="page-1")

    lines = []
    for pts, text, conf in parsed:
        geom = geometry_from_points(
            [Point(x / w, y / h) for (x, y) in pts]) if (pts and w and h) else None
        word = Word(text=text, confidence=conf, geometry=geom,
                    break_after=Break.EOL)
        line = Line(text=text, confidence=conf, geometry=geom,
                    words=[word], break_after=Break.LINE_BREAK,
                    provider_meta={"easyocr_detection": True})
        lines.append(line)

    block = wrap_lines_in_block(lines)
    page.blocks.append(block)
    doc.pages.append(page)
    return doc


def _infer_dims(parsed):
    """Page size = max extent over all polygon points (fallback 1, 1)."""
    max_x = max_y = 0.0
    for pts, _text, _conf in parsed:
        for (x, y) in pts:
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    return (max_x or 1.0, max_y or 1.0)
