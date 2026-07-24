"""
Regression tests against REAL provider OCR outputs (tests/fixtures/).

Source document: page 2 of Virginia OCS Administrative Memo #21-07 (2020), a
public government memo. The same page was run through Google Cloud Vision, AWS
Textract, and Azure AI Document Intelligence; each native response is stored
under tests/fixtures/ as <engine>_0212236_p01_raw.json, alongside the source
image 0212236_p01.jpg.

Unlike the hand-built fixtures in the other test modules, these exercise the
parsers against real-world quirks (punctuation-as-words, sparse pages, a
hyperlink, per-symbol Vision breaks, Textract's normalized geometry, Azure's
flat span model).

Checked per source:
  * parses without error, with the expected word count
  * all word geometry normalizes into [0, 1]
  * same-format round-trip preserves the word-text sequence
  * conversion to every other format preserves the character content
    (whitespace-insensitive: line-oriented targets re-join word tokens, so
    token counts differ, but no characters are added or lost)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ocronverter

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ALL_FORMATS = ["google_vision", "textract", "tesseract", "azure", "hocr", "easyocr"]

# fmt -> (fixture file, expected word count, expected (w, h) or None if normalized)
CASES = {
    "google_vision": ("google_0212236_p01_raw.json", 69, (1275, 1650)),
    "textract": ("textract_0212236_p01_raw.json", 60, None),
    "azure": ("azure_0212236_p01_raw.json", 60, (1275, 1650)),
}


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _nospace(words):
    return "".join(w.text for w in words).replace(" ", "")


def test_real_parse_geometry_and_roundtrip():
    for fmt, (fname, n_words, dims) in CASES.items():
        data = _load(fname)
        doc = ocronverter.parse(data, fmt)
        words = list(doc.iter_words())

        assert len(words) == n_words, f"{fmt}: {len(words)} words, expected {n_words}"

        # geometry normalized into [0, 1] (small epsilon for rounding)
        for w in words:
            if w.geometry is None:
                continue
            b = w.geometry.bbox
            assert -0.01 <= b.left <= 1.01 and -0.01 <= b.top <= 1.01, f"{fmt}: {b}"
            assert b.right <= 1.01 and b.bottom <= 1.01, f"{fmt}: {b}"

        if dims is not None:
            assert (doc.pages[0].width, doc.pages[0].height) == dims, fmt

        # same-format round-trip keeps the word sequence intact
        out = ocronverter.emit(doc, fmt)
        doc2 = ocronverter.parse(out, fmt)
        assert [w.text for w in doc2.iter_words()] == [w.text for w in words], fmt

    print("OK: real fixtures parse + geometry + round-trip")


def test_real_cross_format_preserves_content():
    for fmt, (fname, _n, _d) in CASES.items():
        data = _load(fname)
        src_chars = _nospace(ocronverter.parse(data, fmt).iter_words())

        for tgt in ALL_FORMATS:
            if tgt == fmt:
                continue
            out = ocronverter.convert(data, fmt, tgt)
            got_chars = _nospace(ocronverter.parse(out, tgt).iter_words())
            assert got_chars == src_chars, (
                f"{fmt} -> {tgt}: character content changed "
                f"({len(src_chars)} -> {len(got_chars)})")

    print("OK: real fixtures cross-format content preservation")


if __name__ == "__main__":
    test_real_parse_geometry_and_roundtrip()
    test_real_cross_format_preserves_content()
