"""
Emit neutral Document -> Google Cloud Vision `fullTextAnnotation` shape.

Inverse of parsers.google_vision. Our Line maps back to a Vision paragraph,
Block to a Vision block. Geometry is written as `normalizedVertices` (0-1);
`vertices` (pixels) are added too when the page has known dimensions, so a
same-format round-trip preserves both vertex forms.
"""

from __future__ import annotations

from typing import Any

from ..model import Break, Document, Geometry, Page

# neutral Break -> Vision BreakType
_BREAK_MAP = {
    Break.SPACE: "SPACE",
    Break.SURE_SPACE: "SURE_SPACE",
    Break.EOL: "EOL_SURE_SPACE",
    Break.HYPHEN: "HYPHEN",
    Break.LINE_BREAK: "LINE_BREAK",
}


def emit(doc: Document, wrap_response: bool = True) -> dict:
    """Return a Vision-shaped dict.

    wrap_response=True  -> {"responses": [{"fullTextAnnotation": {...}}]}
    wrap_response=False -> the fullTextAnnotation dict itself
    """
    fta = {"text": _document_text(doc), "pages": [_page(p) for p in doc.pages]}
    if not wrap_response:
        return fta
    return {"responses": [{"fullTextAnnotation": fta}]}


def _page(page: Page) -> dict:
    out: dict[str, Any] = {"width": page.width, "height": page.height,
                           "blocks": []}
    if page.confidence is not None:
        out["confidence"] = page.confidence
    if page.provider_meta.get("property"):
        out["property"] = page.provider_meta["property"]

    for block in page.blocks:
        vblock: dict[str, Any] = {
            "blockType": block.provider_meta.get("blockType", "TEXT"),
            "paragraphs": [],
        }
        _put_box(vblock, block.geometry, page)
        if block.confidence is not None:
            vblock["confidence"] = block.confidence

        for line in block.lines:
            vpar: dict[str, Any] = {"words": []}
            _put_box(vpar, line.geometry, page)
            if line.confidence is not None:
                vpar["confidence"] = line.confidence

            for word in line.words:
                vword: dict[str, Any] = {"symbols": []}
                _put_box(vword, word.geometry, page)
                if word.confidence is not None:
                    vword["confidence"] = word.confidence

                for sym in word.symbols:
                    vsym: dict[str, Any] = {"text": sym.text}
                    _put_box(vsym, sym.geometry, page)
                    if sym.confidence is not None:
                        vsym["confidence"] = sym.confidence
                    _put_break(vsym, sym)
                    vword["symbols"].append(vsym)
                _vblock_word_fixup(vword, word)
                vpar["words"].append(vword)
            vblock["paragraphs"].append(vpar)
        out["blocks"].append(vblock)
    return out


def _vblock_word_fixup(vword: dict, word) -> None:
    """If a word had no symbols (e.g. parsed from a symbol-less format),
    still emit one synthetic symbol carrying the word text so Vision text
    reconstruction works."""
    if vword["symbols"] or not word.text:
        return
    vsym = {"text": word.text}
    if word.break_after in _BREAK_MAP:
        vsym["property"] = {"detectedBreak": {"type": _BREAK_MAP[word.break_after]}}
    vword["symbols"].append(vsym)


def _put_break(vsym: dict, sym) -> None:
    prefix_val = sym.provider_meta.get("break_is_prefix")
    if prefix_val:
        vsym["property"] = {"detectedBreak": {
            "type": _BREAK_MAP.get(Break(prefix_val), "SPACE"), "isPrefix": True}}
        return
    if sym.break_after in _BREAK_MAP:
        vsym["property"] = {"detectedBreak": {"type": _BREAK_MAP[sym.break_after]}}


def _put_box(target: dict, geom: Geometry | None, page: Page) -> None:
    if geom is None:
        return
    box: dict[str, Any] = {
        "normalizedVertices": [{"x": p.x, "y": p.y} for p in geom.polygon]}
    if page.width and page.height:
        box["vertices"] = [
            {"x": round(p.x * page.width), "y": round(p.y * page.height)}
            for p in geom.polygon
        ]
    target["boundingBox"] = box


def _document_text(doc: Document) -> str:
    """Reassemble the full-document text from words + break markers."""
    out = []
    for page in doc.pages:
        for block in page.blocks:
            for line in block.lines:
                for word in line.words:
                    out.append(word.text)
                    out.append(_break_text(word.break_after))
    return "".join(out)


def _break_text(brk: Break) -> str:
    if brk in (Break.SPACE, Break.SURE_SPACE):
        return " "
    if brk in (Break.EOL, Break.LINE_BREAK):
        return "\n"
    return ""
