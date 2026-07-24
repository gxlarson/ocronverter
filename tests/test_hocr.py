"""
hOCR tests.

  test_hocr_roundtrip : hOCR string -> Document -> hOCR string, verifying the
        class/title parsing (bbox + x_wconf), the page/carea/par/line/word
        nesting, and paragraph regrouping survive.
  test_cross_hocr_to_textract / _tesseract : hOCR bridges to other hierarchies.
  test_cross_vision_to_hocr : paragraph source -> hOCR with auto line-split.
  test_hocr_tolerates_head_voids : <meta>/<link> voids don't desync nesting.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ocronverter
from ocronverter.emitters import hocr as hocr_emit
from ocronverter.parsers import hocr as hocr_parse
from tests.test_google_roundtrip import FIXTURE as VISION_FIXTURE

# 100 x 50 page; "Hello world" on one line, "Bye" on the next. Absolute pixels.
HOCR = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
 "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
<meta name="ocr-system" content="tesseract 5.0.0" />
<link rel="stylesheet" href="x.css" />
</head>
<body>
 <div class='ocr_page' id='page_1' title='image "x.png"; bbox 0 0 100 50; ppageno 0'>
  <div class='ocr_carea' id='block_1_1' title='bbox 10 10 90 45'>
   <p class='ocr_par' id='par_1_1' title='bbox 10 10 90 45'>
    <span class='ocr_line' id='line_1_1' title='bbox 10 10 90 25; baseline 0 -2'>
     <span class='ocrx_word' id='word_1_1' title='bbox 10 10 45 25; x_wconf 96'>Hello</span>
     <span class='ocrx_word' id='word_1_2' title='bbox 55 10 90 25; x_wconf 95'>world</span>
    </span>
    <span class='ocr_line' id='line_1_2' title='bbox 10 30 40 45; baseline 0 -2'>
     <span class='ocrx_word' id='word_1_3' title='bbox 10 30 40 45; x_wconf 94'>Bye</span>
    </span>
   </p>
  </div>
 </div>
</body>
</html>
"""


def test_hocr_roundtrip():
    doc = hocr_parse.parse(HOCR)
    page = doc.pages[0]
    assert (page.width, page.height) == (100, 50)

    blocks = page.blocks
    assert len(blocks) == 1
    assert [ln.text for ln in blocks[0].lines] == ["Hello world", "Bye"]
    assert [w.text for w in doc.iter_words()] == ["Hello", "world", "Bye"]

    # geometry normalized: "Hello" left 10/100 = 0.10
    hello = list(doc.iter_words())[0]
    assert abs(hello.geometry.bbox.left - 0.10) < 1e-9
    # x_wconf 96 -> 0.96
    assert abs(hello.confidence - 0.96) < 1e-9

    # emit back to hOCR string
    out = hocr_emit.emit(doc)
    assert isinstance(out, str)
    assert "class='ocr_page'" in out
    assert ">Hello<" in out and ">world<" in out and ">Bye<" in out
    assert "x_wconf 96" in out

    # re-parse stable (text + geometry + confidence survive)
    doc2 = hocr_parse.parse(out)
    assert [w.text for w in doc2.iter_words()] == ["Hello", "world", "Bye"]
    assert [ln.text for ln in doc2.pages[0].blocks[0].lines] == ["Hello world", "Bye"]
    h2 = list(doc2.iter_words())[0]
    assert abs(h2.geometry.bbox.left - 0.10) < 1e-9
    assert abs(h2.confidence - 0.96) < 1e-9
    print("OK: hOCR round-trip (class/title parse + nesting + confidence)")


def test_hocr_tolerates_head_voids():
    # The <meta>/<link> void tags in <head> must not push onto the element
    # stack; if they did, the page would nest under them and be lost.
    doc = hocr_parse.parse(HOCR)
    assert len(doc.pages) == 1 and doc.pages[0].blocks
    print("OK: hOCR tolerates head void tags")


def test_cross_hocr_to_textract():
    out = ocronverter.convert(HOCR, "hocr", "textract")
    lines = [b["Text"] for b in out["Blocks"] if b["BlockType"] == "LINE"]
    words = [b["Text"] for b in out["Blocks"] if b["BlockType"] == "WORD"]
    assert lines == ["Hello world", "Bye"]
    assert words == ["Hello", "world", "Bye"]
    print("OK: hocr -> textract")


def test_cross_hocr_to_tesseract():
    out = ocronverter.convert(HOCR, "ocr_html", "tsv")  # alias exercise too
    wtext = [out["text"][i] for i, lv in enumerate(out["level"]) if lv == 5]
    assert wtext == ["Hello", "world", "Bye"]
    print("OK: hocr -> tesseract")


def test_cross_vision_to_hocr():
    out = ocronverter.convert(VISION_FIXTURE, "vision", "hocr")
    assert isinstance(out, str)
    # auto line-split: two ocr_line elements, "Hello world" then "Bye"
    assert out.count("class='ocr_line'") == 2
    assert ">Hello<" in out and ">Bye<" in out
    print("OK: vision -> hocr (auto line-split)")


if __name__ == "__main__":
    test_hocr_roundtrip()
    test_hocr_tolerates_head_voids()
    test_cross_hocr_to_textract()
    test_cross_hocr_to_tesseract()
    test_cross_vision_to_hocr()
