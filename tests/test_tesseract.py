"""
Tesseract tests.

  test_tesseract_roundtrip_fixture : column-dict -> Document -> column-dict,
        no binary needed (hand-built Output.DICT fixture).
  test_real_tesseract : if the tesseract binary + PIL are present, render an
        image, run pytesseract.image_to_data, and round-trip the REAL output.
  test_cross_tesseract_to_vision : Tesseract fixture -> Vision text.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ocronverter
from ocronverter.emitters import tesseract as ts_emit
from ocronverter.parsers import tesseract as ts_parse

# Output.DICT-shaped fixture: page > block > para > 2 lines, "Hello world" / "Bye"
FIXTURE = {
    "level":    [1, 2, 3, 4, 5, 5, 4, 5],
    "page_num": [1, 1, 1, 1, 1, 1, 1, 1],
    "block_num":[0, 1, 1, 1, 1, 1, 1, 1],
    "par_num":  [0, 0, 1, 1, 1, 1, 1, 1],
    "line_num": [0, 0, 0, 1, 1, 1, 2, 2],
    "word_num": [0, 0, 0, 0, 1, 2, 0, 1],
    "left":     [0, 10, 10, 10, 10, 60, 10, 10],
    "top":      [0, 10, 10, 10, 10, 10, 30, 30],
    "width":    [200, 120, 120, 90, 40, 40, 30, 30],
    "height":   [100, 45, 45, 15, 15, 15, 15, 15],
    "conf":     [-1, -1, -1, -1, 96.0, 95.0, 94.0, -1],
    "text":     ["", "", "", "", "Hello", "world", "", "Bye"],
}


def test_tesseract_roundtrip_fixture():
    doc = ts_parse.parse(FIXTURE)
    assert doc.pages[0].width == 200 and doc.pages[0].height == 100
    assert [w.text for w in doc.iter_words()] == ["Hello", "world", "Bye"]
    # confidence normalized
    assert abs(list(doc.iter_words())[0].confidence - 0.96) < 1e-9
    # geometry: "Hello" left 10/200 = 0.05
    assert abs(list(doc.iter_words())[0].geometry.bbox.left - 0.05) < 1e-9

    out = ts_emit.emit(doc)
    # pixels restored
    wi = [i for i, lv in enumerate(out["level"]) if lv == 5]
    words = [(out["text"][i], out["left"][i], out["conf"][i]) for i in wi]
    assert words[0] == ("Hello", 10, 96.0)
    # par grouping preserved (both lines share par_num 1)
    par_rows = [i for i, lv in enumerate(out["level"]) if lv == 3]
    assert len(par_rows) == 1

    # re-parse stable
    doc2 = ts_parse.parse(out)
    assert [w.text for w in doc2.iter_words()] == ["Hello", "world", "Bye"]
    print("OK: tesseract fixture round-trip")


def test_cross_tesseract_to_vision():
    out = ocronverter.convert(FIXTURE, "tesseract", "vision")
    text = out["responses"][0]["fullTextAnnotation"]["text"]
    assert "Hello world" in text and "Bye" in text
    print("OK: tesseract -> vision cross-format")


def test_real_tesseract():
    import shutil
    try:
        import pytesseract
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("SKIP: pytesseract/PIL not installed")
        return

    binary = shutil.which("tesseract") or \
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if not Path(binary).exists():
        print("SKIP: tesseract binary not found")
        return
    pytesseract.pytesseract.tesseract_cmd = binary

    # Render a simple two-line image.
    img = Image.new("RGB", (600, 200), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 48)
    except OSError:
        font = ImageFont.load_default()
    draw.text((20, 20), "Hello world", fill="black", font=font)
    draw.text((20, 100), "Goodbye", fill="black", font=font)

    data = pytesseract.image_to_data(
        img, output_type=pytesseract.Output.DICT)

    # Round-trip the REAL output through the neutral model.
    doc = ts_parse.parse(data)
    words = [w.text for w in doc.iter_words() if w.text.strip()]
    assert any("Hello" in w for w in words), words
    assert any("world" in w for w in words), words
    assert any("Goodbye" in w for w in words), words

    out = ts_emit.emit(doc)
    doc2 = ts_parse.parse(out)
    words2 = [w.text for w in doc2.iter_words() if w.text.strip()]
    assert words == words2

    # And cross-format: real Tesseract -> Vision text carries the words.
    vis = ocronverter.convert(data, "tesseract", "vision")
    vtext = vis["responses"][0]["fullTextAnnotation"]["text"]
    assert "Hello" in vtext and "Goodbye" in vtext
    print(f"OK: REAL tesseract round-trip + cross-format  (words={words})")


if __name__ == "__main__":
    test_tesseract_roundtrip_fixture()
    test_cross_tesseract_to_vision()
    test_real_tesseract()
