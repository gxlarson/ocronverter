"""Convenience API: aliases, string input, convert both directions, auto-split."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ocronverter
from tests.test_google_roundtrip import FIXTURE
from tests.test_textract import TEXTRACT


def test_list_and_aliases():
    assert ocronverter.list_formats() == [
        "azure", "easyocr", "google_vision", "hocr", "tesseract", "textract"]
    assert ocronverter.canonical_format("Vision") == "google_vision"
    assert ocronverter.canonical_format("AWS") == "textract"
    assert ocronverter.canonical_format("aws-textract") == "textract"
    assert ocronverter.canonical_format("hOCR") == "hocr"
    assert ocronverter.canonical_format("Easy_OCR") == "easyocr"
    try:
        ocronverter.canonical_format("nope")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    print("OK: formats + aliases")


def test_convert_vision_to_textract_autosplit():
    # dict input, auto split (paragraph source -> line target)
    out = ocronverter.convert(FIXTURE, "vision", "textract")
    lines = [b["Text"] for b in out["Blocks"] if b["BlockType"] == "LINE"]
    assert lines == ["Hello world", "Bye"]  # auto-split kicked in
    print("OK: vision -> textract (auto-split)")


def test_convert_string_input_and_json_output():
    # JSON string in, JSON string out
    s = json.dumps(TEXTRACT)
    out = ocronverter.convert(s, "textract", "google_vision", as_json=True, indent=2)
    assert isinstance(out, str)
    reparsed = json.loads(out)
    words = reparsed["responses"][0]["fullTextAnnotation"]["text"]
    assert "Hello" in words and "Bye" in words
    print("OK: string in -> json out (textract -> vision)")


def test_emit_opts_passthrough():
    doc = ocronverter.parse(FIXTURE, "vision")
    fta = ocronverter.emit(doc, "vision", wrap_response=False)
    assert "pages" in fta and "responses" not in fta  # opt reached the emitter
    print("OK: emit opts passthrough")


if __name__ == "__main__":
    test_list_and_aliases()
    test_convert_vision_to_textract_autosplit()
    test_convert_string_input_and_json_output()
    test_emit_opts_passthrough()
