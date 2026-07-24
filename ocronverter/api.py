"""
Top-level convenience API.

    import ocronverter

    doc  = ocronverter.parse(data, "google_vision")     # -> neutral Document
    out  = ocronverter.emit(doc, "textract")            # -> provider dict
    out  = ocronverter.convert(data, "google_vision", "textract")   # parse+emit

`data` may be a dict or a JSON string. Format names are case-insensitive and
accept common aliases (see FORMAT_ALIASES). `convert` returns a dict by default;
pass as_json=True for a JSON string.

Line synthesis (Q2, opt-in): converting a paragraph-oriented source (Google
Vision) into a line-oriented target (Textract) reads best with one line per
visual line. `convert(..., split_lines=True)` runs synth.split_lines_on_breaks
first. It defaults to "auto": on by default only for that lossy direction, so
same-format and Textract->Vision trips are left untouched.
"""

from __future__ import annotations

import json

from . import synth
from .emitters import azure as _az_emit
from .emitters import easyocr as _eo_emit
from .emitters import google_vision as _gv_emit
from .emitters import hocr as _hocr_emit
from .emitters import tesseract as _ts_emit
from .emitters import textract as _tx_emit
from .model import Document
from .parsers import azure as _az_parse
from .parsers import easyocr as _eo_parse
from .parsers import google_vision as _gv_parse
from .parsers import hocr as _hocr_parse
from .parsers import tesseract as _ts_parse
from .parsers import textract as _tx_parse

# dict / JSON string for JSON formats; list for EasyOCR's native detections;
# markup string for hOCR.
JsonLike = dict | list | str

# canonical name -> (parser, emitter). emitter is a callable(doc, **opts)->dict.
_REGISTRY = {
    "google_vision": (_gv_parse.parse, _gv_emit.emit),
    "textract": (_tx_parse.parse, _tx_emit.emit),
    "tesseract": (_ts_parse.parse, _ts_emit.emit),
    "azure": (_az_parse.parse, _az_emit.emit),
    "hocr": (_hocr_parse.parse, _hocr_emit.emit),
    "easyocr": (_eo_parse.parse, _eo_emit.emit),
}

# formats whose data is a text/markup string, not JSON: parse() must pass the
# raw string straight to the parser rather than json.loads-ing it.
_TEXT_INPUT_FORMATS = {"hocr"}

# lowercased alias -> canonical name
FORMAT_ALIASES = {
    "google": "google_vision",
    "google_vision": "google_vision",
    "googlevision": "google_vision",
    "vision": "google_vision",
    "gcv": "google_vision",
    "aws": "textract",
    "textract": "textract",
    "aws_textract": "textract",
    "tesseract": "tesseract",
    "tess": "tesseract",
    "tsv": "tesseract",
    "azure": "azure",
    "azure_di": "azure",
    "document_intelligence": "azure",
    "form_recognizer": "azure",
    "di": "azure",
    "hocr": "hocr",
    "ocr_html": "hocr",
    "easyocr": "easyocr",
    "easy_ocr": "easyocr",
    "easy": "easyocr",
}

# formats whose native grouping is paragraph-ish (no real line level)
_PARAGRAPH_SOURCES = {"google_vision"}
# formats that read best as one entry per visual line
_LINE_TARGETS = {"textract", "tesseract", "azure", "hocr", "easyocr"}


def list_formats() -> list[str]:
    """Canonical format names currently supported (parse + emit)."""
    return sorted(_REGISTRY)


def canonical_format(name: str) -> str:
    key = (name or "").strip().lower().replace("-", "_")
    if key in FORMAT_ALIASES:
        return FORMAT_ALIASES[key]
    raise ValueError(
        f"Unknown OCR format {name!r}. Known: {', '.join(list_formats())} "
        f"(aliases: {', '.join(sorted(FORMAT_ALIASES))})."
    )


def _as_dict(data: JsonLike):
    if isinstance(data, str):
        return json.loads(data)
    if isinstance(data, (dict, list)):  # list: EasyOCR's native detections shape
        return data
    raise TypeError(
        f"Expected dict, list, or JSON str, got {type(data).__name__}.")


def parse(data: JsonLike, source_format: str) -> Document:
    """Provider data (JSON dict/str/list, or an hOCR string) -> neutral Document."""
    fmt = canonical_format(source_format)
    parser, _ = _REGISTRY[fmt]
    if fmt in _TEXT_INPUT_FORMATS:
        return parser(data)  # hOCR: raw markup string/bytes, not JSON
    return parser(_as_dict(data))


def emit(doc: Document, target_format: str, **opts):
    """Neutral Document -> provider output. Extra opts pass through to the emitter.

    Return type follows the target's native shape: a dict for JSON formats, a
    list for EasyOCR, an hOCR/XHTML string for hocr.
    """
    fmt = canonical_format(target_format)
    _, emitter = _REGISTRY[fmt]
    return emitter(doc, **opts)


def convert(
    data: JsonLike,
    source_format: str,
    target_format: str,
    *,
    split_lines: bool | str = "auto",
    as_json: bool = False,
    indent: int = None,
    **emit_opts,
):
    """Parse `data` from source_format and emit as target_format.

    split_lines : True / False / "auto" (default). "auto" splits paragraph
                  sources into visual lines only when the target is line-oriented.
    as_json     : return a JSON string instead of the native object. Intended
                  for JSON targets; hOCR already emits a string, and applying it
                  to hOCR/EasyOCR just JSON-encodes their native output.
    indent      : JSON indent when as_json=True.
    """
    src = canonical_format(source_format)
    dst = canonical_format(target_format)

    doc = parse(data, src)

    if split_lines is True or (
        split_lines == "auto" and src in _PARAGRAPH_SOURCES and dst in _LINE_TARGETS
    ):
        synth.split_lines_on_breaks(doc)

    out = emit(doc, dst, **emit_opts)
    if as_json:
        return json.dumps(out, indent=indent, ensure_ascii=False)
    return out
