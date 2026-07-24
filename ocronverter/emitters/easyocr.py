"""
Emit neutral Document -> EasyOCR `readtext` output. Inverse of parsers.easyocr.

EasyOCR is a flat list of [polygon, text, confidence] detections at text-box
granularity, so we emit one entry per Line: its 4-point polygon (denormalized to
pixels) as [[x,y],...], its text, and its confidence. Line confidence is used
when present, else the mean of its word confidences, else omitted.

When a Line only has an axis-aligned bbox (no explicit polygon), a 4-corner
polygon is derived from it. Page dims come from the Page; DEFAULT_PAGE fills in
when unknown (e.g. a Textract-origin doc) so coordinates stay in pixels.

Returns a list (EasyOCR's native shape). It is valid JSON as-is.
"""

from __future__ import annotations

from ..geometry import polygon_from_bbox
from ..model import Document, Geometry, Page

SOURCE_FORMAT = "easyocr"

DEFAULT_PAGE = (1000, 1000)


def _dims(page: Page):
    return (page.width or DEFAULT_PAGE[0], page.height or DEFAULT_PAGE[1])


def _polygon(geom: Geometry | None, w, h):
    if geom is None:
        return []
    pts = geom.polygon or polygon_from_bbox(geom.bbox)
    return [[int(round(p.x * w)), int(round(p.y * h))] for p in pts]


def _confidence(line):
    if line.confidence is not None:
        return round(line.confidence, 4)
    confs = [w.confidence for w in line.words if w.confidence is not None]
    if confs:
        return round(sum(confs) / len(confs), 4)
    return None


def emit(doc: Document) -> list:
    results = []
    for page in doc.pages:
        w, h = _dims(page)
        for block in page.blocks:
            for line in block.lines:
                text = line.text or " ".join(
                    wd.text for wd in line.words if wd.text)
                entry = [_polygon(line.geometry, w, h), text]
                conf = _confidence(line)
                if conf is not None:
                    entry.append(conf)
                results.append(entry)
    return results
