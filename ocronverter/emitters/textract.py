"""
Emit neutral Document -> AWS Textract response shape.

Inverse of parsers.textract. The neutral Block level is COLLAPSED (Textract has
no blocks): every Line under every Block is flattened into the page's LINE list.
Symbols are dropped (Textract stops at WORD). Output is a flat "Blocks" list
with a regenerated CHILD relationship graph.

If the source grouped multiple visual lines into one Line (e.g. a Google Vision
paragraph), call synth.split_lines_on_breaks(doc) BEFORE emitting to get one
Textract LINE per visual line.

IDs: a node's original id (from a Textract parse) is reused when present, so a
same-format round-trip keeps ids stable; otherwise a deterministic id is minted.
"""

from __future__ import annotations

from ..model import Break, Document, Geometry

SOURCE_FORMAT = "textract"


class _IdGen:
    """Deterministic ids (no randomness) so output is reproducible/testable."""

    def __init__(self):
        self._n = 0

    def get(self, existing):
        if existing:
            return existing
        self._n += 1
        return f"blk-{self._n:08d}"


def _geom_dict(geom: Geometry) -> dict:
    return {
        "BoundingBox": {
            "Width": geom.bbox.width, "Height": geom.bbox.height,
            "Left": geom.bbox.left, "Top": geom.bbox.top,
        },
        "Polygon": [{"X": p.x, "Y": p.y} for p in geom.polygon],
    }


def _conf(value) -> float:
    return round(value * 100.0, 4) if value is not None else 0.0


def _line_text(line) -> str:
    if line.text:
        return line.text
    parts = []
    for w in line.words:
        parts.append(w.text)
        if w.break_after in (Break.SPACE, Break.SURE_SPACE):
            parts.append(" ")
    return "".join(parts).rstrip()


def emit(doc: Document) -> dict:
    ids = _IdGen()
    page_blocks = []  # PAGE blocks, in document order
    body = []         # LINE/WORD blocks

    for page in doc.pages:
        page_block = {
            "BlockType": "PAGE",
            "Id": ids.get(page.id),
            "Geometry": _full_page_geom(),  # neutral Page has no geometry; full page
            "Relationships": [],
        }
        line_ids = []

        for nblock in page.blocks:
            for line in nblock.lines:
                word_ids = []
                for word in line.words:
                    wid = ids.get(word.id)
                    word_ids.append(wid)
                    wblock = {
                        "BlockType": "WORD",
                        "Id": wid,
                        "Text": word.text,
                        "Confidence": _conf(word.confidence),
                    }
                    if word.geometry:
                        wblock["Geometry"] = _geom_dict(word.geometry)
                    body.append(wblock)

                lid = ids.get(line.id)
                line_ids.append(lid)
                lblock = {
                    "BlockType": "LINE",
                    "Id": lid,
                    "Text": _line_text(line),
                    "Confidence": _conf(line.confidence),
                }
                if line.geometry:
                    lblock["Geometry"] = _geom_dict(line.geometry)
                if word_ids:
                    lblock["Relationships"] = [{"Type": "CHILD", "Ids": word_ids}]
                # Textract lists PAGE, then LINEs, then WORDs, but consumers
                # resolve by Id so order within a page is free.
                body.append(lblock)

        if line_ids:
            page_block["Relationships"] = [{"Type": "CHILD", "Ids": line_ids}]
        page_blocks.append(page_block)

    # PAGE blocks first (in document order), then the LINE/WORD bodies.
    return {
        "DocumentMetadata": {"Pages": len(doc.pages)},
        "Blocks": page_blocks + body,
        "DetectDocumentTextModelVersion": "1.0",
    }


def _full_page_geom() -> dict:
    return {
        "BoundingBox": {"Width": 1.0, "Height": 1.0, "Left": 0.0, "Top": 0.0},
        "Polygon": [{"X": 0.0, "Y": 0.0}, {"X": 1.0, "Y": 0.0},
                    {"X": 1.0, "Y": 1.0}, {"X": 0.0, "Y": 1.0}],
    }
