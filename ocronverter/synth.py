"""
Opt-in synthesis of levels the neutral model doesn't carry from a given source
(Q2: the model never invents levels on parse; callers ask for synthesis when a
target format needs a level the source lacked).

Two operations so far:

    split_lines_on_breaks(doc)   split a Line into visual lines at internal
                                 EOL / LINE_BREAK word breaks. Needed when a
                                 source groups by paragraph (Google Vision) but
                                 the target is line-oriented (Textract, hOCR).

    wrap_lines_in_block(lines)   bundle loose lines under one synthetic Block,
                                 for sources with no block level (Textract).

All operations mutate/return neutral objects only; they are pure geometry+break
reasoning with no provider knowledge.
"""

from __future__ import annotations

from .geometry import union_geometry
from .model import Block, Break, Document, Line

_LINE_BREAKS = (Break.EOL, Break.LINE_BREAK)


def split_lines_on_breaks(doc: Document) -> Document:
    """In place: split each Line wherever an interior word ends a visual line."""
    for page in doc.pages:
        for block in page.blocks:
            block.lines = _split_block_lines(block.lines)
    return doc


def _split_block_lines(lines: list[Line]) -> list[Line]:
    out: list[Line] = []
    for line in lines:
        out.extend(_split_one_line(line))
    return out


def _split_one_line(line: Line) -> list[Line]:
    if len(line.words) <= 1:
        return [line]

    groups: list[list] = [[]]
    for i, word in enumerate(line.words):
        groups[-1].append(word)
        is_last = i == len(line.words) - 1
        if word.break_after in _LINE_BREAKS and not is_last:
            groups.append([])

    if len(groups) == 1:
        return [line]  # no interior break; leave untouched

    new_lines = []
    for gi, words in enumerate(groups):
        is_last_group = gi == len(groups) - 1
        nl = Line(
            words=words,
            confidence=line.confidence,
            geometry=union_geometry([w.geometry for w in words if w.geometry]),
            break_after=line.break_after if is_last_group else Break.EOL,
            provider_meta=dict(line.provider_meta),
        )
        _rebuild_line_text(nl)
        new_lines.append(nl)
    return new_lines


def _rebuild_line_text(line: Line) -> None:
    parts = []
    for w in line.words:
        parts.append(w.text)
        if w.break_after in (Break.SPACE, Break.SURE_SPACE):
            parts.append(" ")
    line.text = "".join(parts).rstrip()


def wrap_lines_in_block(lines: list[Line]) -> Block:
    """Bundle lines under one synthetic Block (for block-less sources)."""
    block = Block(
        lines=list(lines),
        geometry=union_geometry([ln.geometry for ln in lines if ln.geometry]),
        provider_meta={"synthetic": True},
    )
    block.text = "\n".join(ln.text for ln in lines)
    return block
