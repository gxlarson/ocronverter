"""
ocronverter — convert between OCR output formats via a neutral intermediate model.

Design:
    <provider JSON> --parse--> Document (neutral) --emit--> <provider JSON>

The neutral model (see model.py) is the superset of the levels every supported
OCR service exposes. Any level may be absent; parsers fill what the source
provides, emitters synthesize or collapse what a target needs.

Guarantees:
    * Semantic round-trip: text + geometry + confidence survive any A -> B -> A.
    * Best-effort lossless round-trip when B == A, via per-node provider_meta.
"""

from .api import canonical_format, convert, emit, list_formats, parse
from .model import (
    BBox,
    Block,
    Break,
    Document,
    Geometry,
    Line,
    Page,
    Point,
    Symbol,
    Word,
)

__all__ = [
    # model
    "Document",
    "Page",
    "Block",
    "Line",
    "Word",
    "Symbol",
    "Geometry",
    "BBox",
    "Point",
    "Break",
    # api
    "parse",
    "emit",
    "convert",
    "list_formats",
    "canonical_format",
]
