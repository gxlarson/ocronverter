"""
Parse Tesseract `image_to_data` output -> neutral Document.

Tesseract's structured output is a table with a `level` column:

    1 = page   2 = block   3 = paragraph   4 = line   5 = word

so its hierarchy is  page -> block -> paragraph -> line -> word, with pixel
coordinates and word-level confidence (0-100; -1 on non-word rows). It has a
PARAGRAPH level our model lacks (between block and line) and no symbol level.
We map:

    Tesseract page      -> Page   (dims come from the level-1 row's w/h)
    Tesseract block     -> Block
    Tesseract paragraph -> preserved as Line.provider_meta["par_num"]
    Tesseract line      -> Line
    Tesseract word      -> Word

Accepts either the Output.DICT shape (dict of parallel lists, what
pytesseract.image_to_data(output_type=DICT) returns) or the raw TSV string.
"""

from __future__ import annotations

from ..geometry import geometry_from_bbox
from ..model import BBox, Block, Break, Document, Line, Page, Word

SOURCE_FORMAT = "tesseract"

_COLUMNS = ["level", "page_num", "block_num", "par_num", "line_num",
            "word_num", "left", "top", "width", "height", "conf", "text"]

LEVEL_PAGE, LEVEL_BLOCK, LEVEL_PARA, LEVEL_LINE, LEVEL_WORD = 1, 2, 3, 4, 5


def _rows_from_dict(d: dict) -> list[dict]:
    n = len(d.get("level", []))
    return [{c: d[c][i] for c in _COLUMNS if c in d} for i in range(n)]


def _rows_from_tsv(text: str) -> list[dict]:
    lines = text.splitlines()
    if not lines:
        return []
    header = lines[0].split("\t")
    rows = []
    for ln in lines[1:]:
        if not ln.strip():
            continue
        cells = ln.split("\t")
        # text (last col) may itself be empty; pad short rows
        cells += [""] * (len(header) - len(cells))
        rows.append(dict(zip(header, cells, strict=False)))
    return rows


def _to_rows(data) -> list[dict]:
    if isinstance(data, str):
        return _rows_from_tsv(data)
    if isinstance(data, dict):
        return _rows_from_dict(data)
    raise TypeError("tesseract parse expects an Output.DICT dict or a TSV string")


def _i(row, key, default=0):
    try:
        return int(float(row.get(key, default)))
    except (TypeError, ValueError):
        return default


def _conf(row):
    try:
        c = float(row.get("conf", -1))
    except (TypeError, ValueError):
        return None
    return None if c < 0 else c / 100.0


def _geom(row, pw, ph):
    if not pw or not ph:
        return None
    left = _i(row, "left") / pw
    top = _i(row, "top") / ph
    width = _i(row, "width") / pw
    height = _i(row, "height") / ph
    return geometry_from_bbox(BBox(left=left, top=top, width=width, height=height))


def parse(data) -> Document:
    rows = _to_rows(data)
    doc = Document(source_format=SOURCE_FORMAT)

    # Page dimensions from the level-1 row (there may be several pages).
    doc_pages: list[Page] = []
    cur: Page | None = None
    page_dims = (0, 0)
    block: Block | None = None
    line: Line | None = None

    for row in rows:
        level = _i(row, "level")

        if level == LEVEL_PAGE:
            page_dims = (_i(row, "width"), _i(row, "height"))
            cur = Page(width=page_dims[0], height=page_dims[1],
                       id=f"page-{_i(row, 'page_num')}")
            doc_pages.append(cur)
            block = line = None
            continue

        if cur is None:
            continue  # rows before the first page row (malformed) — skip

        if level == LEVEL_BLOCK:
            block = Block(
                geometry=_geom(row, *page_dims),
                provider_meta={"block_num": _i(row, "block_num")},
            )
            cur.blocks.append(block)
            line = None

        elif level == LEVEL_PARA:
            # No neutral paragraph level; par_num is carried on each LINE below.
            pass

        elif level == LEVEL_LINE:
            line = Line(
                geometry=_geom(row, *page_dims),
                break_after=Break.LINE_BREAK,
                provider_meta={
                    "block_num": _i(row, "block_num"),
                    "par_num": _i(row, "par_num"),
                    "line_num": _i(row, "line_num"),
                },
            )
            (block or _ensure_block(cur)).lines.append(line)

        elif level == LEVEL_WORD:
            text = row.get("text", "") or ""
            if line is None:
                line = Line(break_after=Break.LINE_BREAK)
                _ensure_block(cur).lines.append(line)
            word = Word(
                text=text,
                confidence=_conf(row),
                geometry=_geom(row, *page_dims),
                break_after=Break.SPACE,
                provider_meta={"word_num": _i(row, "word_num")},
            )
            line.words.append(word)

    for page in doc_pages:
        for blk in page.blocks:
            for ln in blk.lines:
                _finish_line(ln)
            _finish_block(blk)
    doc.pages = doc_pages
    return doc


def _ensure_block(page: Page) -> Block:
    if not page.blocks:
        page.blocks.append(Block(provider_meta={"synthetic": True}))
    return page.blocks[-1]


def _finish_line(line: Line) -> None:
    if line.words:
        line.words[-1].break_after = Break.EOL
    line.text = " ".join(w.text for w in line.words if w.text)


def _finish_block(block: Block) -> None:
    block.text = "\n".join(ln.text for ln in block.lines)
