# CLAUDE.md

Guidance for working in this repo. See `README.md` for user-facing usage.

## What this is

`ocronverter` converts between OCR output formats via a neutral intermediate
model: `<provider> --parse--> Document --emit--> <provider>`. One parser and one
emitter per format; no direct format-to-format converters.

## Layout

```
ocronverter/
  __init__.py        public exports (model types + api functions)
  api.py             parse / emit / convert / list_formats; registry + aliases
  model.py           neutral dataclasses: Document > Page > Block > Line > Word > Symbol
  geometry.py        bbox<->polygon, normalize<->denormalize helpers
  synth.py           opt-in synthesis of missing levels (line splitting, block wrapping)
  parsers/<fmt>.py   provider data -> Document
  emitters/<fmt>.py  Document -> provider data
tests/
  test_<fmt>.py      round-trip + cross-format tests (stdlib only, no binaries)
  test_api.py        registry, aliases, convert options
```

## Supported formats

`google_vision`, `textract`, `tesseract`, `azure`, `hocr`, `easyocr`.
Canonical names + aliases live in `api.FORMAT_ALIASES`; the parser/emitter
registry is `api._REGISTRY`. Keep those two in sync when adding a format.

## Core conventions (don't break these)

- **Normalized geometry.** All coordinates are 0.0–1.0 of the page, stored as
  both bbox and polygon (`Geometry`). Parsers normalize using page dims;
  emitters denormalize. Use `geometry.py` helpers, never hand-roll.
- **Confidence is 0.0–1.0** internally. Rescale in the parser/emitter (e.g.
  Tesseract 0–100, hOCR `x_wconf` 0–100).
- **Levels are optional and never invented on parse.** If a target needs a level
  the source lacked, the caller opts into `synth.py`. `convert` does this
  automatically only for paragraph-source → line-target (`_PARAGRAPH_SOURCES` /
  `_LINE_TARGETS` in `api.py`).
- **`provider_meta`** carries source-specific fields verbatim for best-effort
  lossless same-format round-trips. Paragraph identity for the level-less model
  rides here (`par_num` for Tesseract, `par_id` for hOCR).

## Data-shape gotchas

- Most formats are JSON (`dict`/JSON string); `api._as_dict` also passes Python
  `list`s through for **EasyOCR** (bare detections list).
- **hOCR** is a markup **string**, not JSON. It's in `api._TEXT_INPUT_FORMATS`,
  so `parse` hands the raw string to the parser instead of `json.loads`-ing it;
  its emitter returns a string. If you add another string/XML format (ALTO,
  PAGE), add it to `_TEXT_INPUT_FORMATS` too.
- **EasyOCR** has no page dims — the parser infers them from max polygon extent
  so emit→parse is stable. Don't assume `Page.width/height` came from the source.
- **hOCR** parsing only tracks `div/p/span` on its stack so `<head>` void tags
  (`<meta>`, `<link>`) can't unbalance nesting. Keep that invariant if editing
  the parser.
- No char/glyph level is modeled (hOCR `ocrx_cinfo`, Azure not exposed). The
  model has a `Symbol` tier but current parsers/emitters stop at `Word`.

## Adding a format

1. `parsers/<fmt>.py` with `SOURCE_FORMAT` and `parse(data) -> Document`.
2. `emitters/<fmt>.py` with `emit(doc) -> <provider shape>`.
3. Register in both `parsers/__init__.py` and `emitters/__init__.py`.
4. Add to `api._REGISTRY`, `api.FORMAT_ALIASES`, and (if line-oriented)
   `api._LINE_TARGETS`. Add to `_TEXT_INPUT_FORMATS` if it's a string format.
5. `tests/test_<fmt>.py`: a round-trip test + at least one cross-format bridge.
   Update the format-list assertion in `tests/test_api.py`.

## Testing

```
python -m pytest tests/
```

Stdlib only; no OCR binaries required (except `test_real_tesseract`, which
self-skips when `tesseract`/PIL are absent). Run individual test modules
directly too: `python tests/test_hocr.py`.
