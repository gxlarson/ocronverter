"""
Neutral intermediate model for OCR output.

Hierarchy (every level optional):

    Document
     └─ Page[]       size in pixels + rotation; the coordinate anchor
         └─ Block[]  ~ Textract paragraph / Vision BLOCK / Tesseract block
             └─ Line[]   Textract LINE / Tesseract line (Vision has none)
                 └─ Word[]
                     └─ Symbol[]   Vision symbol / Tesseract char (optional)

Conventions decided during design:
    * Geometry stores BOTH a normalized axis-aligned bbox AND a polygon
      (Q1: both, no info loss, cheap conversion either way).
    * Confidence is ALWAYS stored 0.0-1.0 internally; parsers rescale.
    * Levels are optional. The library never invents levels on parse;
      synthesis of missing levels is an explicit, opt-in step (see synth.py).
    * `provider_meta` on every node carries source-specific fields verbatim so
      a same-format round-trip can be (best-effort) lossless.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Break(str, Enum):
    """Whitespace/break that follows a node, used to reassemble plain text."""

    NONE = "none"
    SPACE = "space"
    SURE_SPACE = "sure_space"  # Vision's wide space
    EOL = "eol"                # end of line
    HYPHEN = "hyphen"          # line-break hyphen (word continues next line)
    LINE_BREAK = "line_break"  # paragraph/line separation


@dataclass
class Point:
    """A single vertex, normalized to 0.0-1.0 of the page."""

    x: float
    y: float


@dataclass
class BBox:
    """Axis-aligned bounding box, normalized to 0.0-1.0 of the page."""

    left: float
    top: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height


@dataclass
class Geometry:
    """Both representations kept in sync (Q1). Normalized to the page, 0.0-1.0.

    Use geometry.py helpers to build one from the other or to project into
    pixel space using a Page's dimensions.
    """

    bbox: BBox
    polygon: list[Point] = field(default_factory=list)


# ---- content nodes -------------------------------------------------------

@dataclass
class Symbol:
    text: str = ""
    confidence: float | None = None            # 0.0-1.0
    geometry: Geometry | None = None
    break_after: Break = Break.NONE
    id: str | None = None
    provider_meta: dict = field(default_factory=dict)


@dataclass
class Word:
    text: str = ""
    confidence: float | None = None
    geometry: Geometry | None = None
    break_after: Break = Break.NONE
    symbols: list[Symbol] = field(default_factory=list)
    id: str | None = None
    provider_meta: dict = field(default_factory=dict)


@dataclass
class Line:
    text: str = ""
    confidence: float | None = None
    geometry: Geometry | None = None
    break_after: Break = Break.EOL
    words: list[Word] = field(default_factory=list)
    id: str | None = None
    provider_meta: dict = field(default_factory=dict)


@dataclass
class Block:
    text: str = ""
    confidence: float | None = None
    geometry: Geometry | None = None
    break_after: Break = Break.LINE_BREAK
    lines: list[Line] = field(default_factory=list)
    id: str | None = None
    provider_meta: dict = field(default_factory=dict)


@dataclass
class Page:
    """A page. width/height are in `unit` and anchor all normalized geometry.

    Usually pixels (Vision, Tesseract, Textract=normalized so 0). Azure may use
    "inch" with fractional dims (e.g. 8.5 x 11), hence float.
    """

    width: float = 0
    height: float = 0
    unit: str = "pixel"
    rotation: float = 0.0
    blocks: list[Block] = field(default_factory=list)
    confidence: float | None = None
    id: str | None = None
    provider_meta: dict = field(default_factory=dict)


@dataclass
class Document:
    """Top-level container. `source_format` records who parsed it."""

    pages: list[Page] = field(default_factory=list)
    source_format: str | None = None
    language: str | None = None
    provider_meta: dict = field(default_factory=dict)

    def iter_words(self):
        for page in self.pages:
            for block in page.blocks:
                for line in block.lines:
                    yield from line.words
