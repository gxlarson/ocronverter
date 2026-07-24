"""
Azure Document Intelligence tests.

  test_azure_roundtrip : analyzeResult -> Document -> analyzeResult, verifying
        the span-containment reconstruction (flat words/lines -> nested) and
        unit-based (inch) geometry normalization survive.
  test_cross_azure_to_textract / _to_tesseract : Azure bridges to the other
        two hierarchy styles.
  test_cross_vision_to_azure : paragraph source -> Azure with auto line-split.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ocronverter
from ocronverter.emitters import azure as az_emit
from ocronverter.parsers import azure as az_parse
from tests.test_google_roundtrip import FIXTURE as VISION_FIXTURE

# content: "Hello world\nBye"  (offsets: Hello 0-5, world 6-11, \n 11, Bye 12-15)
# 8.5 x 11 inch page; polygons are in inches.
AZURE = {
    "status": "succeeded",
    "analyzeResult": {
        "apiVersion": "2023-07-31",
        "modelId": "prebuilt-layout",
        "content": "Hello world\nBye",
        "pages": [{
            "pageNumber": 1,
            "angle": 0.0,
            "width": 8.5,
            "height": 11.0,
            "unit": "inch",
            "words": [
                {"content": "Hello", "confidence": 0.99,
                 "polygon": [0.85, 1.1, 2.55, 1.1, 2.55, 1.65, 0.85, 1.65],
                 "span": {"offset": 0, "length": 5}},
                {"content": "world", "confidence": 0.98,
                 "polygon": [2.72, 1.1, 4.25, 1.1, 4.25, 1.65, 2.72, 1.65],
                 "span": {"offset": 6, "length": 5}},
                {"content": "Bye", "confidence": 0.97,
                 "polygon": [0.85, 2.2, 1.7, 2.2, 1.7, 2.75, 0.85, 2.75],
                 "span": {"offset": 12, "length": 3}},
            ],
            "lines": [
                {"content": "Hello world",
                 "polygon": [0.85, 1.1, 4.25, 1.1, 4.25, 1.65, 0.85, 1.65],
                 "spans": [{"offset": 0, "length": 11}]},
                {"content": "Bye",
                 "polygon": [0.85, 2.2, 1.7, 2.2, 1.7, 2.75, 0.85, 2.75],
                 "spans": [{"offset": 12, "length": 3}]},
            ],
        }],
        "paragraphs": [
            {"spans": [{"offset": 0, "length": 11}],
             "boundingRegions": [{"pageNumber": 1,
                                  "polygon": [0.85, 1.1, 4.25, 1.1, 4.25, 1.65, 0.85, 1.65]}],
             "content": "Hello world"},
            {"spans": [{"offset": 12, "length": 3}],
             "boundingRegions": [{"pageNumber": 1,
                                  "polygon": [0.85, 2.2, 1.7, 2.2, 1.7, 2.75, 0.85, 2.75]}],
             "content": "Bye"},
        ],
    },
}


def test_azure_roundtrip():
    doc = az_parse.parse(AZURE)
    page = doc.pages[0]
    assert (page.width, page.height, page.unit) == (8.5, 11.0, "inch")

    # span containment nested the flat words under the right lines
    blocks = page.blocks
    assert len(blocks) == 2  # two paragraphs -> two blocks
    assert blocks[0].lines[0].text == "Hello world"
    assert [w.text for w in blocks[0].lines[0].words] == ["Hello", "world"]
    assert blocks[1].lines[0].text == "Bye"
    assert [w.text for w in doc.iter_words()] == ["Hello", "world", "Bye"]

    # inch geometry normalized: "Hello" left 0.85/8.5 = 0.10
    hello = list(doc.iter_words())[0]
    assert abs(hello.geometry.bbox.left - 0.10) < 1e-9
    assert abs(hello.confidence - 0.99) < 1e-9

    # emit back
    out = az_emit.emit(doc)
    r = out["analyzeResult"]
    assert r["content"] == "Hello world\nBye"
    apage = r["pages"][0]
    assert apage["unit"] == "inch"
    assert [w["content"] for w in apage["words"]] == ["Hello", "world", "Bye"]
    # polygon denormalized back to inches (Hello left ~0.85)
    assert abs(apage["words"][0]["polygon"][0] - 0.85) < 1e-3
    assert len(r["paragraphs"]) == 2

    # re-parse stable
    doc2 = az_parse.parse(out)
    assert [w.text for w in doc2.iter_words()] == ["Hello", "world", "Bye"]
    assert doc2.pages[0].blocks[0].lines[0].text == "Hello world"
    print("OK: azure round-trip (span reconstruction + inch geometry)")


def test_cross_azure_to_textract():
    out = ocronverter.convert(AZURE, "azure", "textract")
    lines = [b["Text"] for b in out["Blocks"] if b["BlockType"] == "LINE"]
    words = [b["Text"] for b in out["Blocks"] if b["BlockType"] == "WORD"]
    assert lines == ["Hello world", "Bye"]
    assert words == ["Hello", "world", "Bye"]
    print("OK: azure -> textract")


def test_cross_azure_to_tesseract():
    out = ocronverter.convert(AZURE, "di", "tsv")  # alias exercise too
    wtext = [out["text"][i] for i, lv in enumerate(out["level"]) if lv == 5]
    assert wtext == ["Hello", "world", "Bye"]
    print("OK: azure -> tesseract")


def test_cross_vision_to_azure():
    # Vision paragraph -> Azure, auto-split into two lines.
    out = ocronverter.convert(VISION_FIXTURE, "vision", "azure")
    apage = out["analyzeResult"]["pages"][0]
    assert [ln["content"] for ln in apage["lines"]] == ["Hello world", "Bye"]
    assert out["analyzeResult"]["content"].startswith("Hello world")
    print("OK: vision -> azure (auto line-split)")


if __name__ == "__main__":
    test_azure_roundtrip()
    test_cross_azure_to_textract()
    test_cross_azure_to_tesseract()
    test_cross_vision_to_azure()
