"""
Parse hOCR (the open HTML/XHTML OCR interchange format) -> neutral Document.

hOCR encodes structure in element `class` names and packs geometry/metadata into
a `title` attribute:

    <div  class='ocr_page'  title='image "x.png"; bbox 0 0 W H; ppageno 0'>
     <div  class='ocr_carea' title='bbox ...'>
      <p   class='ocr_par'   title='bbox ...'>
       <span class='ocr_line' title='bbox ...; baseline 0 -4'>
        <span class='ocrx_word' title='bbox x0 y0 x1 y1; x_wconf 95'>Hello</span>

so its hierarchy is  page -> carea -> par -> line -> word, with absolute pixel
coordinates and 0-100 word confidence. Like Tesseract it has a PARAGRAPH level
our model lacks; we carry `ocr_par` identity on each Line's provider_meta. We map:

    ocr_page  -> Page   (dims from the page bbox: right/bottom)
    ocr_carea -> Block  (also ocr_column)
    ocr_par   -> preserved as Line.provider_meta["par_id"]
    ocr_line  -> Line   (also ocr_header / ocr_caption / ocr_textfloat)
    ocrx_word -> Word

Parsing tolerates real-world hOCR by only tracking div/p/span on the element
stack, so void tags in <head> (<meta>, <link>) can't unbalance nesting.
"""

from __future__ import annotations

from html.parser import HTMLParser

from ..geometry import geometry_from_bbox
from ..model import BBox, Block, Break, Document, Line, Page, Word

SOURCE_FORMAT = "hocr"

# Only these tags carry hOCR structure; everything else (meta, img, br, strong,
# em, ...) is ignored for nesting so void/inline tags never desync the stack.
_CONTAINER_TAGS = {"div", "p", "span"}

_BLOCK_CLASSES = {"ocr_carea", "ocr_column"}
_LINE_CLASSES = {"ocr_line", "ocr_header", "ocr_caption",
                 "ocr_textfloat", "ocrx_line"}
_PAR_CLASSES = {"ocr_par"}
_WORD_CLASSES = {"ocrx_word", "ocr_word"}


def _parse_title(title: str) -> dict:
    """hOCR title -> {prop: [tokens]}, e.g. 'bbox 1 2 3 4; x_wconf 90'."""
    props = {}
    for part in (title or "").split(";"):
        toks = part.split()
        if toks:
            props[toks[0]] = toks[1:]
    return props


class _HOCRTree(HTMLParser):
    """Build a nested dict tree of the div/p/span elements only."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = {"class": "", "id": None, "props": {},
                     "children": [], "text": ""}
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        if tag not in _CONTAINER_TAGS:
            return
        a = dict(attrs)
        node = {
            "class": a.get("class", "") or "",
            "id": a.get("id"),
            "props": _parse_title(a.get("title", "")),
            "children": [],
            "text": "",
        }
        self.stack[-1]["children"].append(node)
        self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        # e.g. <span .../>: has no content, don't leave it on the stack.
        if tag in _CONTAINER_TAGS:
            self.handle_starttag(tag, attrs)
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in _CONTAINER_TAGS and len(self.stack) > 1:
            self.stack.pop()

    def handle_data(self, data):
        self.stack[-1]["text"] += data


def _classes(node) -> set:
    return set(node["class"].split())


def _gather_text(node) -> str:
    """Concatenated text of a node and all descendants (handles inner spans)."""
    parts = [node["text"]]
    for child in node["children"]:
        parts.append(_gather_text(child))
    return "".join(parts)


def _geom(props, w, h):
    bb = props.get("bbox")
    if not bb or len(bb) < 4 or not w or not h:
        return None
    try:
        x0, y0, x1, y1 = (float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3]))
    except ValueError:
        return None
    return geometry_from_bbox(
        BBox(left=x0 / w, top=y0 / h, width=(x1 - x0) / w, height=(y1 - y0) / h))


def _wconf(props):
    vals = props.get("x_wconf")
    if not vals:
        return None
    try:
        return float(vals[0]) / 100.0
    except ValueError:
        return None


def _iter(node, cls_set):
    """Depth-first find of nodes whose classes intersect cls_set."""
    if _classes(node) & cls_set:
        yield node
    for child in node["children"]:
        yield from _iter(child, cls_set)


def parse(data) -> Document:
    if isinstance(data, bytes):
        data = data.decode("utf-8", "replace")
    if not isinstance(data, str):
        raise TypeError("hocr parse expects an hOCR/XHTML string or bytes")

    tree = _HOCRTree()
    tree.feed(data)

    doc = Document(source_format=SOURCE_FORMAT)
    for pi, pnode in enumerate(_iter(tree.root, {"ocr_page"}), start=1):
        bb = pnode["props"].get("bbox")
        w = float(bb[2]) if bb and len(bb) >= 4 else 0
        h = float(bb[3]) if bb and len(bb) >= 4 else 0
        ppageno = pnode["props"].get("ppageno")
        page = Page(width=w, height=h, id=pnode["id"] or f"page-{pi}")
        if ppageno:
            page.provider_meta["ppageno"] = ppageno[0]

        state = {"block": None, "line": None, "par": None, "par_seq": 0}
        for child in pnode["children"]:
            _walk(child, page, w, h, state)

        for blk in page.blocks:
            for ln in blk.lines:
                _finish_line(ln)
            _finish_block(blk)
        doc.pages.append(page)
    return doc


def _walk(node, page, w, h, state) -> None:
    cls = _classes(node)

    if cls & _BLOCK_CLASSES:
        block = Block(geometry=_geom(node["props"], w, h),
                      provider_meta={"hocr_id": node["id"], "class": node["class"]})
        page.blocks.append(block)
        state["block"] = block
        state["line"] = None

    elif cls & _PAR_CLASSES:
        state["par_seq"] += 1
        state["par"] = node["id"] or f"par_{state['par_seq']}"

    elif cls & _LINE_CLASSES:
        block = state["block"] or _ensure_block(page, state)
        line = Line(
            geometry=_geom(node["props"], w, h),
            break_after=Break.LINE_BREAK,
            provider_meta={"hocr_id": node["id"], "class": node["class"],
                           "par_id": state["par"]},
        )
        block.lines.append(line)
        state["line"] = line

    elif cls & _WORD_CLASSES:
        line = state["line"]
        if line is None:
            block = state["block"] or _ensure_block(page, state)
            line = Line(break_after=Break.LINE_BREAK)
            block.lines.append(line)
            state["line"] = line
        line.words.append(Word(
            text=_gather_text(node).strip(),
            confidence=_wconf(node["props"]),
            geometry=_geom(node["props"], w, h),
            break_after=Break.SPACE,
            provider_meta={"hocr_id": node["id"]},
        ))
        return  # don't descend into a word (skip any ocr_glyph children)

    for child in node["children"]:
        _walk(child, page, w, h, state)


def _ensure_block(page: Page, state) -> Block:
    block = Block(provider_meta={"synthetic": True})
    page.blocks.append(block)
    state["block"] = block
    return block


def _finish_line(line: Line) -> None:
    if line.words:
        line.words[-1].break_after = Break.EOL
    if not line.text:
        line.text = " ".join(w.text for w in line.words if w.text)


def _finish_block(block: Block) -> None:
    if not block.text:
        block.text = "\n".join(ln.text for ln in block.lines)
