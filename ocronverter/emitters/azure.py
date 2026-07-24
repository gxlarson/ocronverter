"""
Emit neutral Document -> Azure AI Document Intelligence (analyzeResult) shape.

Inverse of parsers.azure. The hard part is reconstructing the flat model: we
walk the hierarchy once, building the `content` string while recording each
word's / line's / paragraph's character span (offset+length) into it. Then
words and lines are emitted as FLAT per-page lists (Azure's shape), and blocks
become document-level `paragraphs[]` with boundingRegions.

Geometry is denormalized to page units. When page dims are unknown (e.g. a
Textract-origin doc), DEFAULT_PAGE is used so polygons are still populated.
"""

from __future__ import annotations

from ..model import Document, Geometry, Page

SOURCE_FORMAT = "azure"

DEFAULT_PAGE = (8.5, 11.0, "inch")  # US Letter; used when dims are unknown


def _dims(page: Page):
    if page.width and page.height:
        return page.width, page.height, page.unit or "pixel"
    return DEFAULT_PAGE


def _poly(geom: Geometry, w, h) -> list:
    """Flat [x1,y1,...,x4,y4] in page units from a normalized Geometry."""
    if geom is None:
        return []
    out = []
    for p in geom.polygon:
        out.extend([round(p.x * w, 4), round(p.y * h, 4)])
    return out


def emit(doc: Document) -> dict:
    content_parts = []
    offset = [0]

    def add(text: str):
        start = offset[0]
        content_parts.append(text)
        offset[0] += len(text)
        return {"offset": start, "length": len(text)}

    pages_out = []
    paragraphs_out = []

    for page in doc.pages:
        w, h, unit = _dims(page)
        words_out, lines_out = [], []

        for block in page.blocks:
            block_start = offset[0]
            for line in block.lines:
                line_start = offset[0]
                for wi, word in enumerate(line.words):
                    wspan = add(word.text)
                    words_out.append({
                        "content": word.text,
                        "polygon": _poly(word.geometry, w, h),
                        "confidence": round(word.confidence, 4)
                        if word.confidence is not None else 1.0,
                        "span": wspan,
                    })
                    if wi < len(line.words) - 1:
                        add(" ")  # inter-word space is part of content
                line_len = offset[0] - line_start
                lines_out.append({
                    "content": line.text or _line_text(line),
                    "polygon": _poly(line.geometry, w, h),
                    "spans": [{"offset": line_start, "length": line_len}],
                })
                add("\n")  # line separator

            # Non-synthetic blocks surface as Azure paragraphs.
            if not block.provider_meta.get("synthetic"):
                block_len = offset[0] - block_start
                para = {
                    "spans": [{"offset": block_start, "length": block_len}],
                    "boundingRegions": [{
                        "pageNumber": len(pages_out) + 1,
                        "polygon": _poly(block.geometry, w, h),
                    }],
                    "content": block.text or "",
                }
                role = block.provider_meta.get("role")
                if role:
                    para["role"] = role
                paragraphs_out.append(para)

        pages_out.append({
            "pageNumber": len(pages_out) + 1,
            "angle": page.rotation,
            "width": w,
            "height": h,
            "unit": unit,
            "words": words_out,
            "lines": lines_out,
            "spans": _page_span(words_out, lines_out),
        })

    content = "".join(content_parts)
    if content.endswith("\n"):  # drop the trailing line separator we appended
        content = content[:-1]

    result = {
        "apiVersion": "2023-07-31",
        "modelId": "prebuilt-layout",
        "content": content,
        "pages": pages_out,
        "paragraphs": paragraphs_out,
    }
    return {"status": "succeeded", "analyzeResult": result}


def _line_text(line) -> str:
    return " ".join(w.text for w in line.words if w.text)


def _page_span(words_out, lines_out) -> list:
    spans = [w["span"] for w in words_out] + \
            [s for ln in lines_out for s in ln["spans"]]
    if not spans:
        return []
    start = min(s["offset"] for s in spans)
    end = max(s["offset"] + s["length"] for s in spans)
    return [{"offset": start, "length": end - start}]
