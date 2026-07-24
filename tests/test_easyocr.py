"""
EasyOCR tests.

  test_easyocr_roundtrip : detections list -> Document -> detections list,
        verifying inferred page dims, polygon normalization, and per-detection
        confidence survive; and that each detection maps to a Line+Word.
  test_easyocr_dict_wrapper : explicit {width,height,results} dims are honored.
  test_cross_easyocr_to_textract : EasyOCR bridges to a block/line hierarchy.
  test_cross_vision_to_easyocr : paragraph source -> EasyOCR (auto line-split).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ocronverter
from ocronverter.emitters import easyocr as eo_emit
from ocronverter.parsers import easyocr as eo_parse
from tests.test_google_roundtrip import FIXTURE as VISION_FIXTURE

# EasyOCR readtext() output: [polygon(4 pts), text, confidence]. No page dims;
# max extent is (200, 80) -> inferred page size.
EASYOCR = [
    [[[10, 10], [110, 10], [110, 30], [10, 30]], "Hello world", 0.90],
    [[[10, 50], [60, 50], [60, 80], [10, 80]], "Bye", 0.85],
]


def test_easyocr_roundtrip():
    doc = eo_parse.parse(EASYOCR)
    page = doc.pages[0]
    # dims inferred from max extent of all polygon points
    assert (page.width, page.height) == (110, 80)

    # each detection -> one Line holding one Word
    lines = page.blocks[0].lines
    assert [ln.text for ln in lines] == ["Hello world", "Bye"]
    assert [w.text for w in doc.iter_words()] == ["Hello world", "Bye"]

    # geometry normalized: first box left 10/110
    first = lines[0]
    assert abs(first.geometry.bbox.left - 10 / 110) < 1e-9
    assert abs(first.confidence - 0.90) < 1e-9

    # emit back to EasyOCR list shape
    out = eo_emit.emit(doc)
    assert isinstance(out, list) and len(out) == 2
    box, text, conf = out[0]
    assert text == "Hello world"
    assert abs(conf - 0.90) < 1e-9
    # polygon denormalized back to pixels (top-left ~ [10, 10])
    assert box[0] == [10, 10]

    # re-parse stable (same inferred dims, so geometry recovers)
    doc2 = eo_parse.parse(out)
    assert [w.text for w in doc2.iter_words()] == ["Hello world", "Bye"]
    assert (doc2.pages[0].width, doc2.pages[0].height) == (110, 80)
    print("OK: easyocr round-trip (inferred dims + polygon + confidence)")


def test_easyocr_dict_wrapper():
    wrapped = {"width": 400, "height": 300, "results": EASYOCR}
    doc = eo_parse.parse(wrapped)
    assert (doc.pages[0].width, doc.pages[0].height) == (400, 300)
    # left now normalized against the true width: 10/400
    assert abs(doc.pages[0].blocks[0].lines[0].geometry.bbox.left - 10 / 400) < 1e-9
    print("OK: easyocr honors explicit dict-wrapped dims")


def test_easyocr_two_element_entry():
    # paragraph=True drops confidence -> 2-element entries.
    data = [[[[0, 0], [50, 0], [50, 20], [0, 20]], "Hi"]]
    doc = eo_parse.parse(data)
    assert [w.text for w in doc.iter_words()] == ["Hi"]
    assert doc.iter_words().__next__().confidence is None
    print("OK: easyocr handles confidence-less (paragraph) entries")


def test_cross_easyocr_to_textract():
    out = ocronverter.convert(EASYOCR, "easyocr", "textract")
    lines = [b["Text"] for b in out["Blocks"] if b["BlockType"] == "LINE"]
    assert lines == ["Hello world", "Bye"]
    print("OK: easyocr -> textract")


def test_cross_vision_to_easyocr():
    out = ocronverter.convert(VISION_FIXTURE, "vision", "easy")  # alias too
    assert isinstance(out, list)
    texts = [entry[1] for entry in out]
    assert texts == ["Hello world", "Bye"]  # auto line-split into two detections
    print("OK: vision -> easyocr (auto line-split)")


if __name__ == "__main__":
    test_easyocr_roundtrip()
    test_easyocr_dict_wrapper()
    test_easyocr_two_element_entry()
    test_cross_easyocr_to_textract()
    test_cross_vision_to_easyocr()
