"""
Parse AWS Textract (`DetectDocumentText` / `AnalyzeDocument`) -> neutral Document.

Textract is a FLAT list of Blocks joined by a relationship graph:

    PAGE --CHILD--> LINE --CHILD--> WORD

There is no Block or Symbol level, and no pixel page size (all geometry is
normalized 0-1). Confidence is 0-100. We map:

    Textract PAGE -> Page
    (no block level) -> one synthetic Block per page (synth.wrap_lines_in_block)
    Textract LINE -> Line
    Textract WORD -> Word   (no symbols)

Word breaks are inferred: words within a line are space-separated, the last
word of a line ends the line (EOL), so cross-format text reassembly works.
"""

from __future__ import annotations

from ..model import BBox, Break, Document, Geometry, Line, Page, Point, Word
from ..synth import wrap_lines_in_block

SOURCE_FORMAT = "textract"


def _geom(geometry: dict) -> Geometry | None:
    if not geometry:
        return None
    bb = geometry.get("BoundingBox") or {}
    bbox = BBox(
        left=bb.get("Left", 0.0), top=bb.get("Top", 0.0),
        width=bb.get("Width", 0.0), height=bb.get("Height", 0.0),
    )
    poly = [Point(p.get("X", 0.0), p.get("Y", 0.0))
            for p in geometry.get("Polygon", [])]
    if not poly:  # Textract almost always supplies Polygon, but be safe
        poly = [Point(bbox.left, bbox.top), Point(bbox.right, bbox.top),
                Point(bbox.right, bbox.bottom), Point(bbox.left, bbox.bottom)]
    return Geometry(bbox=bbox, polygon=poly)


def _conf(block: dict) -> float | None:
    c = block.get("Confidence")
    return None if c is None else c / 100.0


def _children(block: dict, by_id: dict) -> list[dict]:
    out = []
    for rel in block.get("Relationships", []) or []:
        if rel.get("Type") == "CHILD":
            out.extend(by_id[i] for i in rel.get("Ids", []) if i in by_id)
    return out


def parse(response: dict) -> Document:
    """Parse a Textract response dict (must contain a "Blocks" list)."""
    doc = Document(source_format=SOURCE_FORMAT)
    blocks = (response or {}).get("Blocks", [])
    by_id = {b["Id"]: b for b in blocks if "Id" in b}

    for pblock in blocks:
        if pblock.get("BlockType") != "PAGE":
            continue
        page = Page(width=0, height=0, unit="normalized", id=pblock.get("Id"))

        lines = []
        for lblock in _children(pblock, by_id):
            if lblock.get("BlockType") != "LINE":
                continue
            words = []
            word_blocks = [w for w in _children(lblock, by_id)
                           if w.get("BlockType") == "WORD"]
            for wi, wblock in enumerate(word_blocks):
                is_last = wi == len(word_blocks) - 1
                words.append(Word(
                    text=wblock.get("Text", ""),
                    confidence=_conf(wblock),
                    geometry=_geom(wblock.get("Geometry")),
                    break_after=Break.EOL if is_last else Break.SPACE,
                    id=wblock.get("Id"),
                ))
            line = Line(
                text=lblock.get("Text", ""),
                confidence=_conf(lblock),
                geometry=_geom(lblock.get("Geometry")),
                break_after=Break.LINE_BREAK,
                words=words,
                id=lblock.get("Id"),
            )
            lines.append(line)

        page.blocks = [wrap_lines_in_block(lines)] if lines else []
        doc.pages.append(page)
    return doc
