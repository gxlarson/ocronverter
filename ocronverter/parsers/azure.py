"""
Parse Azure AI Document Intelligence (prebuilt-read / -layout) -> Document.

Azure's shape is unlike the others:

  * Geometry is a FLAT polygon [x1,y1,x2,y2,x3,y3,x4,y4] in page `unit`
    (inch or pixel), NOT normalized.
  * Within a page, `words[]` and `lines[]` are FLAT lists. Their nesting is
    implied by character `span` offsets into `analyzeResult.content`: a word
    belongs to the line whose span range contains the word's offset.
  * `paragraphs[]` live at analyzeResult level (not per page) and reference a
    page via boundingRegions[].pageNumber; lines map to a paragraph the same
    span-containment way.

We map:

    Azure page      -> Page   (width/height/unit preserved for denormalization)
    Azure paragraph -> Block
    Azure line      -> Line
    Azure word      -> Word

Word/line association is offset-range containment (the Azure-specific bit).
"""

from __future__ import annotations

from ..geometry import geometry_from_points, union_geometry
from ..model import Block, Break, Document, Line, Page, Point, Word
from ..synth import wrap_lines_in_block

SOURCE_FORMAT = "azure"


def _polygon(obj):
    """Azure v3 uses `polygon`; older previews used `boundingBox`. Flat 8 nums."""
    return obj.get("polygon") or obj.get("boundingBox") or []


def _geom(obj, w, h):
    flat = _polygon(obj)
    if not flat or not w or not h:
        return None
    pts = [Point(flat[i] / w, flat[i + 1] / h) for i in range(0, len(flat) - 1, 2)]
    return geometry_from_points(pts) if pts else None


def _spans(obj):
    if obj.get("spans"):
        return obj["spans"]
    if obj.get("span"):
        return [obj["span"]]
    return []


def _span_range(obj):
    """(start, end) covering an element's spans, or (0, 0)."""
    spans = _spans(obj)
    if not spans:
        return (0, 0)
    start = min(s.get("offset", 0) for s in spans)
    end = max(s.get("offset", 0) + s.get("length", 0) for s in spans)
    return (start, end)


def _extract_result(obj: dict) -> dict:
    if not isinstance(obj, dict):
        return {}
    if "analyzeResult" in obj:
        return obj["analyzeResult"] or {}
    return obj  # already an analyzeResult


def parse(response: dict) -> Document:
    result = _extract_result(response)
    doc = Document(source_format=SOURCE_FORMAT)
    doc.language = _first_language(result)

    paragraphs = result.get("paragraphs", []) or []

    for pi, apage in enumerate(result.get("pages", []), start=1):
        page_num = apage.get("pageNumber", pi)
        w = apage.get("width", 0) or 0
        h = apage.get("height", 0) or 0
        page = Page(width=w, height=h, unit=apage.get("unit", "pixel"),
                    rotation=apage.get("angle", 0.0) or 0.0,
                    id=f"page-{page_num}")

        # 1) Build lines with their span ranges.
        line_metas = []  # (Line, start, end)
        for lz in apage.get("lines", []):
            start, end = _span_range(lz)
            line = Line(text=lz.get("content", ""), geometry=_geom(lz, w, h),
                        break_after=Break.LINE_BREAK,
                        provider_meta={"spans": _spans(lz)})
            line_metas.append((line, start, end))

        # 2) Assign each word to the line whose span range contains it.
        leftover_words = []
        for wz in apage.get("words", []):
            w_off, _ = _span_range(wz)
            word = Word(text=wz.get("content", ""),
                        confidence=wz.get("confidence"),
                        geometry=_geom(wz, w, h), break_after=Break.SPACE)
            target = _find_containing(line_metas, w_off)
            (target.words if target else leftover_words).append(word)
        if leftover_words:
            line_metas.append((Line(words=leftover_words,
                                    break_after=Break.LINE_BREAK), 0, 0))

        # 3) Group lines into Blocks via paragraphs (span containment).
        used = set()
        for para in paragraphs:
            if not _para_on_page(para, page_num):
                continue
            pranges = [(_s(s), _e(s)) for s in _spans(para)]
            block_lines = []
            for idx, (line, start, _end) in enumerate(line_metas):
                if idx in used:
                    continue
                if any(a <= start < b for a, b in pranges) or (
                        not pranges and False):
                    block_lines.append(line)
                    used.add(idx)
            if block_lines:
                block = Block(
                    lines=block_lines,
                    geometry=union_geometry(
                        [ln.geometry for ln in block_lines if ln.geometry]),
                    provider_meta={"azure_paragraph": True,
                                   "role": para.get("role")},
                )
                page.blocks.append(block)

        # 4) Any lines not claimed by a paragraph -> one synthetic block.
        leftover = [lm[0] for idx, lm in enumerate(line_metas) if idx not in used]
        if leftover:
            page.blocks.append(wrap_lines_in_block(leftover))

        for blk in page.blocks:
            for ln in blk.lines:
                _finish_line(ln)
            _finish_block(blk)
        doc.pages.append(page)
    return doc


def _s(span):
    return span.get("offset", 0)


def _e(span):
    return span.get("offset", 0) + span.get("length", 0)


def _find_containing(line_metas, offset):
    for line, start, end in line_metas:
        if start <= offset < end:
            return line
    return None


def _para_on_page(para, page_num) -> bool:
    for br in para.get("boundingRegions", []) or []:
        if br.get("pageNumber") == page_num:
            return True
    # paragraphs without boundingRegions: treat as belonging everywhere
    return not para.get("boundingRegions")


def _first_language(result: dict):
    for lang in result.get("languages", []) or []:
        code = lang.get("locale") or lang.get("languageCode")
        if code:
            return code
    return None


def _finish_line(line: Line) -> None:
    if line.words:
        line.words[-1].break_after = Break.EOL
    if not line.text:
        line.text = " ".join(w.text for w in line.words if w.text)


def _finish_block(block: Block) -> None:
    if not block.text:
        block.text = "\n".join(ln.text for ln in block.lines)
