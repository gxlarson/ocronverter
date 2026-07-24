"""
Parse Google Cloud Vision `fullTextAnnotation` -> neutral Document.

Vision hierarchy is  page -> block -> paragraph -> word -> symbol, with no
"line" concept; breaks live on symbols (`property.detectedBreak`). We map:

    Vision block     -> Block
    Vision paragraph -> Line     (tagged provider_meta["vision_role"]="paragraph")
    Vision word      -> Word
    Vision symbol    -> Symbol

so the emitter can reproduce Vision exactly. Text at every level is rebuilt
bottom-up from symbols using the break markers.
"""

from __future__ import annotations

from ..geometry import geometry_from_points, normalize_point
from ..model import Block, Break, Document, Line, Page, Point, Symbol, Word

SOURCE_FORMAT = "google_vision"

# Vision BreakType -> neutral Break
_BREAK_MAP = {
    "SPACE": Break.SPACE,
    "SURE_SPACE": Break.SURE_SPACE,
    "EOL_SURE_SPACE": Break.EOL,
    "HYPHEN": Break.HYPHEN,
    "LINE_BREAK": Break.LINE_BREAK,
    "UNKNOWN": Break.NONE,
}


def _points(bounding_box, width, height):
    """Return normalized Points from a Vision boundingBox (either vertex form)."""
    if not bounding_box:
        return []
    if bounding_box.get("normalizedVertices"):
        return [Point(v.get("x", 0.0), v.get("y", 0.0))
                for v in bounding_box["normalizedVertices"]]
    return [normalize_point(v.get("x", 0), v.get("y", 0), width, height)
            for v in bounding_box.get("vertices", [])]


def _geom(bounding_box, width, height):
    pts = _points(bounding_box, width, height)
    return geometry_from_points(pts) if pts else None


def _break_of(symbol):
    """(neutral Break, is_prefix) from a symbol's detectedBreak."""
    db = (symbol.get("property") or {}).get("detectedBreak")
    if not db:
        return Break.NONE, False
    brk = _BREAK_MAP.get(db.get("type", "UNKNOWN"), Break.NONE)
    return brk, bool(db.get("isPrefix"))


def _break_text(brk: Break) -> str:
    if brk in (Break.SPACE, Break.SURE_SPACE):
        return " "
    if brk in (Break.EOL, Break.LINE_BREAK):
        return "\n"
    return ""  # HYPHEN / NONE add nothing to the joined text


def parse(annotation: dict) -> Document:
    """Parse a Vision response.

    Accepts either the full response dict ({"responses":[...]} or a single
    response) or the `fullTextAnnotation` object directly.
    """
    fta = _extract_fta(annotation)
    doc = Document(source_format=SOURCE_FORMAT)
    if not fta:
        return doc

    langs = _languages(fta)
    if langs:
        doc.language = langs[0]

    for vpage in fta.get("pages", []):
        w = int(vpage.get("width", 0))
        h = int(vpage.get("height", 0))
        page = Page(width=w, height=h, confidence=vpage.get("confidence"))
        page.provider_meta = _page_meta(vpage)

        for vblock in vpage.get("blocks", []):
            block = Block(
                confidence=vblock.get("confidence"),
                geometry=_geom(vblock.get("boundingBox"), w, h),
                provider_meta={"blockType": vblock.get("blockType", "TEXT")},
            )
            for vpar in vblock.get("paragraphs", []):
                line = Line(
                    confidence=vpar.get("confidence"),
                    geometry=_geom(vpar.get("boundingBox"), w, h),
                    provider_meta={"vision_role": "paragraph"},
                )
                for vword in vpar.get("words", []):
                    word = Word(
                        confidence=vword.get("confidence"),
                        geometry=_geom(vword.get("boundingBox"), w, h),
                    )
                    for vsym in vword.get("symbols", []):
                        brk, is_prefix = _break_of(vsym)
                        sym = Symbol(
                            text=vsym.get("text", ""),
                            confidence=vsym.get("confidence"),
                            geometry=_geom(vsym.get("boundingBox"), w, h),
                            break_after=Break.NONE if is_prefix else brk,
                        )
                        if is_prefix:
                            sym.provider_meta["break_is_prefix"] = brk.value
                        word.symbols.append(sym)
                    _finish_word(word)
                    line.words.append(word)
                _finish_line(line)
                block.lines.append(line)
            _finish_block(block)
            page.blocks.append(block)
        doc.pages.append(page)
    return doc


# ---- text/break roll-up --------------------------------------------------

def _finish_word(word: Word) -> None:
    word.text = "".join(s.text for s in word.symbols)
    word.break_after = word.symbols[-1].break_after if word.symbols else Break.NONE
    if word.confidence is None:
        confs = [s.confidence for s in word.symbols if s.confidence is not None]
        if confs:
            word.confidence = sum(confs) / len(confs)


def _finish_line(line: Line) -> None:
    parts = []
    for w in line.words:
        parts.append(w.text)
        parts.append(_break_text(w.break_after))
    line.text = "".join(parts).rstrip("\n")
    line.break_after = line.words[-1].break_after if line.words else Break.LINE_BREAK


def _finish_block(block: Block) -> None:
    block.text = "\n".join(ln.text for ln in block.lines)


# ---- input shape helpers -------------------------------------------------

def _extract_fta(obj: dict) -> dict:
    if not isinstance(obj, dict):
        return {}
    if "responses" in obj:
        responses = obj.get("responses") or [{}]
        return responses[0].get("fullTextAnnotation") or {}
    if "fullTextAnnotation" in obj:
        return obj.get("fullTextAnnotation") or {}
    if "pages" in obj or "text" in obj:
        return obj  # already an fta
    return {}


def _languages(fta: dict) -> list[str]:
    for page in fta.get("pages", []):
        for lang in (page.get("property") or {}).get("detectedLanguages", []):
            if lang.get("languageCode"):
                return [lang["languageCode"]]
    return []


def _page_meta(vpage: dict) -> dict:
    meta = {}
    prop = vpage.get("property")
    if prop:
        meta["property"] = prop
    return meta
