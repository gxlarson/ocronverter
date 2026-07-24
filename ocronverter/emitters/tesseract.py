"""
Emit neutral Document -> Tesseract `image_to_data` output.

Inverse of parsers.tesseract. Rebuilds the level-tagged table:

    page(1) -> block(2) -> paragraph(3) -> line(4) -> word(5)

The neutral model has no paragraph level, so lines are regrouped into
paragraphs by their provider_meta["par_num"] (from a Tesseract parse); lines
lacking it fall into a single paragraph per block. Geometry is denormalized to
pixels using the Page dimensions. When those are unknown (e.g. a Textract-origin
doc, all-normalized), DEFAULT_PAGE is used so pixel columns are still populated.

Returns the Output.DICT shape (dict of parallel lists). Use to_tsv() for the
tab-separated string form.
"""

from __future__ import annotations

from ..model import Document, Geometry, Page

SOURCE_FORMAT = "tesseract"

_COLUMNS = ["level", "page_num", "block_num", "par_num", "line_num",
            "word_num", "left", "top", "width", "height", "conf", "text"]

DEFAULT_PAGE = (1000, 1000)


def _dims(page: Page):
    w = page.width or DEFAULT_PAGE[0]
    h = page.height or DEFAULT_PAGE[1]
    return w, h


def _px(geom: Geometry, w, h):
    """(left, top, width, height) in pixels from a normalized Geometry."""
    if geom is None:
        return 0, 0, w, h
    b = geom.bbox
    return (round(b.left * w), round(b.top * h),
            round(b.width * w), round(b.height * h))


def _paragraph_groups(lines):
    """Group consecutive lines by par_num, preserving order."""
    groups, cur, cur_key = [], [], object()
    for line in lines:
        key = line.provider_meta.get("par_num", 1)
        if not cur or key == cur_key:
            cur.append(line)
            cur_key = key
        else:
            groups.append((cur_key, cur))
            cur, cur_key = [line], key
    if cur:
        groups.append((cur_key, cur))
    return groups


def emit(doc: Document) -> dict:
    cols = {c: [] for c in _COLUMNS}

    def row(level, page_num, block_num, par_num, line_num, word_num,
            box, conf, text):
        vals = [level, page_num, block_num, par_num, line_num, word_num,
                box[0], box[1], box[2], box[3], conf, text]
        for c, v in zip(_COLUMNS, vals, strict=True):
            cols[c].append(v)

    for pi, page in enumerate(doc.pages, start=1):
        w, h = _dims(page)
        row(1, pi, 0, 0, 0, 0, (0, 0, w, h), -1, "")

        for bi, block in enumerate(page.blocks, start=1):
            block_num = block.provider_meta.get("block_num", bi)
            row(2, pi, block_num, 0, 0, 0, _px(block.geometry, w, h), -1, "")

            for par_i, (par_key, plines) in enumerate(
                    _paragraph_groups(block.lines), start=1):
                par_num = par_key if isinstance(par_key, int) else par_i
                # paragraph box = union of its line boxes (in pixels)
                pbox = _union_px([ln.geometry for ln in plines], w, h)
                row(3, pi, block_num, par_num, 0, 0, pbox, -1, "")

                for li, line in enumerate(plines, start=1):
                    line_num = line.provider_meta.get("line_num", li)
                    row(4, pi, block_num, par_num, line_num, 0,
                        _px(line.geometry, w, h), -1, "")
                    for wi, word in enumerate(line.words, start=1):
                        word_num = word.provider_meta.get("word_num", wi)
                        conf = round(word.confidence * 100, 2) \
                            if word.confidence is not None else -1
                        row(5, pi, block_num, par_num, line_num, word_num,
                            _px(word.geometry, w, h), conf, word.text)
    return cols


def _union_px(geoms, w, h):
    boxes = [_px(g, w, h) for g in geoms if g is not None]
    if not boxes:
        return 0, 0, w, h
    left = min(b[0] for b in boxes)
    top = min(b[1] for b in boxes)
    right = max(b[0] + b[2] for b in boxes)
    bottom = max(b[1] + b[3] for b in boxes)
    return left, top, right - left, bottom - top


def to_tsv(cols: dict) -> str:
    """Render an emitted column-dict as Tesseract's TSV string."""
    out = ["\t".join(_COLUMNS)]
    n = len(cols["level"])
    for i in range(n):
        out.append("\t".join(str(cols[c][i]) for c in _COLUMNS))
    return "\n".join(out)
