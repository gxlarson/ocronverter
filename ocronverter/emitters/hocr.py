"""
Emit neutral Document -> hOCR (XHTML string). Inverse of parsers.hocr.

Rebuilds the class-tagged tree  page -> carea -> par -> line -> word, packing
geometry and confidence back into each element's `title`. The neutral model has
no paragraph level, so lines are regrouped into `ocr_par` runs by their
provider_meta["par_id"] (from an hOCR/Tesseract parse); lines lacking it fall
into one paragraph per block. Geometry is denormalized to pixels via the Page
dimensions; DEFAULT_PAGE fills in when they're unknown (e.g. a Textract-origin
doc, all-normalized) so bboxes stay populated.

Returns an hOCR document as a string.
"""

from __future__ import annotations

from html import escape

from ..model import Document, Geometry, Page

SOURCE_FORMAT = "hocr"

DEFAULT_PAGE = (1000, 1000)


def _dims(page: Page):
    return (page.width or DEFAULT_PAGE[0], page.height or DEFAULT_PAGE[1])


def _bbox(geom: Geometry | None, w, h):
    if geom is None:
        return (0, 0, int(round(w)), int(round(h)))
    b = geom.bbox
    return (int(round(b.left * w)), int(round(b.top * h)),
            int(round(b.right * w)), int(round(b.bottom * h)))


def _bbox_str(geom, w, h):
    x0, y0, x1, y1 = _bbox(geom, w, h)
    return f"bbox {x0} {y0} {x1} {y1}"


def _paragraph_groups(lines):
    """Group consecutive lines sharing par_id, preserving order."""
    groups: list = []
    cur: list = []
    cur_key: object = object()
    for line in lines:
        key = line.provider_meta.get("par_id")
        if cur and key != cur_key:
            groups.append(cur)
            cur = []
        cur.append(line)
        cur_key = key
    if cur:
        groups.append(cur)
    return groups


def emit(doc: Document) -> str:
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"'
        ' "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">',
        '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">',
        "<head>",
        '<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />',
        '<meta name="ocr-system" content="ocronverter" />',
        '<meta name="ocr-capabilities" content="ocr_page ocr_carea ocr_par'
        ' ocr_line ocrx_word" />',
        "</head>",
        "<body>",
    ]

    for pi, page in enumerate(doc.pages, start=1):
        w, h = _dims(page)
        pid = page.id or f"page_{pi}"
        ppageno = page.provider_meta.get("ppageno", pi - 1)
        out.append(
            f"<div class='ocr_page' id='{escape(str(pid), quote=True)}'"
            f" title='bbox 0 0 {int(round(w))} {int(round(h))}; ppageno {ppageno}'>")

        for bi, block in enumerate(page.blocks, start=1):
            bid = block.provider_meta.get("hocr_id") or f"block_{pi}_{bi}"
            out.append(f"  <div class='ocr_carea' id='{escape(str(bid), quote=True)}'"
                       f" title='{_bbox_str(block.geometry, w, h)}'>")

            for par_i, plines in enumerate(_paragraph_groups(block.lines), start=1):
                pbox = _union_bbox([ln.geometry for ln in plines], w, h)
                out.append(f"   <p class='ocr_par' id='par_{pi}_{bi}_{par_i}'"
                           f" title='bbox {pbox[0]} {pbox[1]} {pbox[2]} {pbox[3]}'>")

                for li, line in enumerate(plines, start=1):
                    lid = (line.provider_meta.get("hocr_id")
                           or f"line_{pi}_{bi}_{par_i}_{li}")
                    out.append(
                        f"    <span class='ocr_line'"
                        f" id='{escape(str(lid), quote=True)}'"
                        f" title='{_bbox_str(line.geometry, w, h)}'>")
                    for wi, word in enumerate(line.words, start=1):
                        wid = word.provider_meta.get("hocr_id") or \
                            f"word_{pi}_{bi}_{par_i}_{li}_{wi}"
                        title = _bbox_str(word.geometry, w, h)
                        if word.confidence is not None:
                            title += f"; x_wconf {int(round(word.confidence * 100))}"
                        out.append(
                            f"     <span class='ocrx_word'"
                            f" id='{escape(str(wid), quote=True)}'"
                            f" title='{title}'>{escape(word.text)}</span>")
                    out.append("    </span>")
                out.append("   </p>")
            out.append("  </div>")
        out.append("</div>")

    out.append("</body>")
    out.append("</html>")
    return "\n".join(out)


def _union_bbox(geoms, w, h):
    boxes = [_bbox(g, w, h) for g in geoms if g is not None]
    if not boxes:
        return (0, 0, int(round(w)), int(round(h)))
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))
