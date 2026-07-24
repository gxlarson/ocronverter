"""
Round-trip check: Vision JSON -> neutral Document -> Vision JSON.

Verifies the design goal (semantic round-trip) on a hand-built fixture that
exercises: two words on a line, a line break, symbol-level breaks, and both
vertex forms. Run:  python -m pytest tests/  (or just: python tests/test_google_roundtrip.py)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ocronverter.emitters import google_vision as gv_emit
from ocronverter.parsers import google_vision as gv_parse


def _sym(text, break_type=None, x0=0, y0=0, x1=10, y1=10):
    s = {
        "text": text,
        "confidence": 0.99,
        "boundingBox": {"vertices": [
            {"x": x0, "y": y0}, {"x": x1, "y": y0},
            {"x": x1, "y": y1}, {"x": x0, "y": y1}]},
    }
    if break_type:
        s["property"] = {"detectedBreak": {"type": break_type}}
    return s


FIXTURE = {
    "responses": [{
        "fullTextAnnotation": {
            "text": "Hello world\nBye\n",
            "pages": [{
                "width": 100,
                "height": 50,
                "property": {"detectedLanguages": [{"languageCode": "en"}]},
                "blocks": [{
                    "blockType": "TEXT",
                    "confidence": 0.98,
                    "boundingBox": {"vertices": [
                        {"x": 0, "y": 0}, {"x": 100, "y": 0},
                        {"x": 100, "y": 50}, {"x": 0, "y": 50}]},
                    "paragraphs": [{
                        "words": [
                            {"symbols": [
                                _sym("H"), _sym("e"), _sym("l"), _sym("l"),
                                _sym("o", "SPACE")]},
                            {"symbols": [
                                _sym("w"), _sym("o"), _sym("r"), _sym("l"),
                                _sym("d", "EOL_SURE_SPACE")]},
                            {"symbols": [
                                _sym("B"), _sym("y"),
                                _sym("e", "LINE_BREAK")]},
                        ],
                    }],
                }],
            }],
        }
    }]
}


def test_semantic_roundtrip():
    doc = gv_parse.parse(FIXTURE)

    # structure
    assert len(doc.pages) == 1
    page = doc.pages[0]
    assert (page.width, page.height) == (100, 50)
    assert doc.language == "en"
    words = list(doc.iter_words())
    assert [w.text for w in words] == ["Hello", "world", "Bye"]

    # geometry normalized correctly (symbol H: x 0..10 of width 100)
    h = words[0].symbols[0]
    assert abs(h.geometry.bbox.left - 0.0) < 1e-9
    assert abs(h.geometry.bbox.width - 0.10) < 1e-9
    # both reps present
    assert len(h.geometry.polygon) == 4

    # emit back
    out = gv_emit.emit(doc)
    fta = out["responses"][0]["fullTextAnnotation"]
    assert fta["text"] == "Hello world\nBye\n"  # matches original, incl. trailing break

    # re-parse the emitted output: text + words stable (semantic round-trip)
    doc2 = gv_parse.parse(out)
    assert [w.text for w in doc2.iter_words()] == ["Hello", "world", "Bye"]
    assert doc2.pages[0].width == 100

    # geometry survived the round-trip
    h2 = list(doc2.iter_words())[0].symbols[0]
    assert abs(h2.geometry.bbox.width - 0.10) < 1e-9

    print("OK: semantic round-trip verified")


if __name__ == "__main__":
    test_semantic_roundtrip()
