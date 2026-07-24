"""
Textract round-trip + the first CROSS-format trip.

  test_textract_roundtrip : Textract JSON -> Document -> Textract JSON
  test_cross_vision_to_textract : Vision -> Document -> (split lines) -> Textract,
        proving the neutral model bridges the two opposite hierarchy styles and
        that synth.split_lines_on_breaks turns a Vision paragraph into real
        Textract LINEs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ocronverter import synth
from ocronverter.emitters import textract as tx_emit
from ocronverter.parsers import google_vision as gv_parse
from ocronverter.parsers import textract as tx_parse


def _bb(left, t, w, h):
    return {
        "BoundingBox": {"Left": left, "Top": t, "Width": w, "Height": h},
        "Polygon": [{"X": left, "Y": t}, {"X": left + w, "Y": t},
                    {"X": left + w, "Y": t + h}, {"X": left, "Y": t + h}],
    }


TEXTRACT = {
    "DocumentMetadata": {"Pages": 1},
    "Blocks": [
        {"BlockType": "PAGE", "Id": "page-1", "Geometry": _bb(0, 0, 1, 1),
         "Relationships": [{"Type": "CHILD", "Ids": ["line-1", "line-2"]}]},
        {"BlockType": "LINE", "Id": "line-1", "Text": "Hello world",
         "Confidence": 99.0, "Geometry": _bb(0.1, 0.1, 0.5, 0.05),
         "Relationships": [{"Type": "CHILD", "Ids": ["w-1", "w-2"]}]},
        {"BlockType": "LINE", "Id": "line-2", "Text": "Bye",
         "Confidence": 98.0, "Geometry": _bb(0.1, 0.2, 0.2, 0.05),
         "Relationships": [{"Type": "CHILD", "Ids": ["w-3"]}]},
        {"BlockType": "WORD", "Id": "w-1", "Text": "Hello",
         "Confidence": 99.5, "Geometry": _bb(0.1, 0.1, 0.24, 0.05)},
        {"BlockType": "WORD", "Id": "w-2", "Text": "world",
         "Confidence": 99.0, "Geometry": _bb(0.36, 0.1, 0.24, 0.05)},
        {"BlockType": "WORD", "Id": "w-3", "Text": "Bye",
         "Confidence": 98.0, "Geometry": _bb(0.1, 0.2, 0.2, 0.05)},
    ],
}


def test_textract_roundtrip():
    doc = tx_parse.parse(TEXTRACT)

    assert len(doc.pages) == 1
    # one synthetic block wrapping both lines
    page = doc.pages[0]
    assert len(page.blocks) == 1 and page.blocks[0].provider_meta.get("synthetic")
    assert [w.text for w in doc.iter_words()] == ["Hello", "world", "Bye"]
    # confidence normalized to 0-1
    assert abs(list(doc.iter_words())[0].confidence - 0.995) < 1e-9

    out = tx_emit.emit(doc)
    by_type = {}
    for b in out["Blocks"]:
        by_type.setdefault(b["BlockType"], []).append(b)
    assert len(by_type["PAGE"]) == 1
    assert len(by_type["LINE"]) == 2
    assert len(by_type["WORD"]) == 3

    # ids preserved (same-format round-trip), confidence back to 0-100
    words = {b["Id"]: b for b in by_type["WORD"]}
    assert words["w-1"]["Text"] == "Hello"
    assert abs(words["w-1"]["Confidence"] - 99.5) < 1e-6

    # relationship graph rebuilt correctly
    page_block = by_type["PAGE"][0]
    child_ids = page_block["Relationships"][0]["Ids"]
    assert child_ids == ["line-1", "line-2"]

    # re-parse: stable
    doc2 = tx_parse.parse(out)
    assert [w.text for w in doc2.iter_words()] == ["Hello", "world", "Bye"]
    print("OK: textract round-trip verified")


def test_cross_vision_to_textract():
    # Build a Vision doc whose single paragraph spans TWO visual lines
    # (word "world" ends its line via EOL_SURE_SPACE).
    from tests.test_google_roundtrip import FIXTURE
    doc = gv_parse.parse(FIXTURE)

    # Vision gave us ONE Line (paragraph) containing all three words.
    assert len(doc.pages[0].blocks[0].lines) == 1

    # Opt-in synthesis (Q2): split the paragraph into real visual lines.
    synth.split_lines_on_breaks(doc)
    lines = doc.pages[0].blocks[0].lines
    assert len(lines) == 2
    assert lines[0].text == "Hello world"
    assert lines[1].text == "Bye"

    # Now emit to Textract: two LINE blocks, three WORD blocks.
    out = tx_emit.emit(doc)
    line_blocks = [b for b in out["Blocks"] if b["BlockType"] == "LINE"]
    word_blocks = [b for b in out["Blocks"] if b["BlockType"] == "WORD"]
    assert [lb["Text"] for lb in line_blocks] == ["Hello world", "Bye"]
    assert [wb["Text"] for wb in word_blocks] == ["Hello", "world", "Bye"]

    # Cross-format confidence made it across (Vision 0.99 -> Textract 99.0)
    assert abs(word_blocks[0]["Confidence"] - 99.0) < 1e-6
    print("OK: Vision -> Textract cross-format verified")


if __name__ == "__main__":
    test_textract_roundtrip()
    test_cross_vision_to_textract()
