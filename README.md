# ocronverter

[![PyPI](https://img.shields.io/pypi/v/ocronverter.svg)](https://pypi.org/project/ocronverter/)
[![Python versions](https://img.shields.io/pypi/pyversions/ocronverter.svg)](https://pypi.org/project/ocronverter/)
[![CI](https://github.com/gxlarson/ocronverter/actions/workflows/ci.yml/badge.svg)](https://github.com/gxlarson/ocronverter/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/pypi/l/ocronverter.svg)](https://github.com/gxlarson/ocronverter/blob/main/LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

Convert between OCR output formats through a single neutral intermediate model.

```
<provider data> --parse--> Document (neutral) --emit--> <provider data>
```

Instead of writing an N×N matrix of direct converters, every format has one
**parser** (provider → `Document`) and one **emitter** (`Document` → provider).
Any source can then be converted to any target.

## Installation

```bash
pip install ocronverter
```

Requires Python 3.10+. The library is pure Python with no runtime dependencies.

## Supported formats

| Engine | Canonical name | Aliases | Data shape |
|---|---|---|---|
| Google Cloud Vision | `google_vision` | `google`, `googlevision`, `vision`, `gcv` | JSON |
| AWS Textract | `textract` | `aws`, `aws_textract` | JSON |
| Tesseract (`image_to_data`) | `tesseract` | `tess`, `tsv` | JSON dict / TSV |
| Azure AI Document Intelligence | `azure` | `azure_di`, `document_intelligence`, `form_recognizer`, `di` | JSON |
| hOCR | `hocr` | `ocr_html` | XHTML string |
| EasyOCR (`readtext`) | `easyocr` | `easy_ocr`, `easy` | list of detections |

Format names are case-insensitive and `-`/`_` interchangeable.
`ocronverter.list_formats()` returns the canonical list at runtime.

## Usage

```python
import ocronverter

# Parse provider output into the neutral Document
doc = ocronverter.parse(data, "google_vision")

# Emit the neutral Document as another provider's format
out = ocronverter.emit(doc, "textract")

# Or do both in one step
out = ocronverter.convert(data, "google_vision", "textract")
out = ocronverter.convert(data, "gcv", "hocr", as_json=False)   # aliases OK
```

`data` may be a `dict`, a JSON string, a Python `list` (EasyOCR's native
detections shape), or an hOCR/XHTML string. `convert` returns a `dict` (or a
`list` for EasyOCR, or a `str` for hOCR); pass `as_json=True` for a JSON string
where the target is JSON-based.

### Line synthesis (`split_lines`)

Google Vision groups by paragraph and has no real line level, while
line-oriented targets (Textract, Tesseract, Azure, hOCR, EasyOCR) read best with
one entry per visual line. `convert(..., split_lines=...)` controls this:

- `"auto"` (default) — split only when going from a paragraph source to a
  line-oriented target.
- `True` / `False` — force on or off.

## The neutral model

```
Document
 └─ Page[]        size + rotation; the coordinate anchor
     └─ Block[]   ~ paragraph / region
         └─ Line[]
             └─ Word[]
                 └─ Symbol[]   (optional; char/glyph level)
```

Conventions:

- Every level is optional. Parsers fill only what the source provides; the
  library never invents levels on parse. Missing levels are synthesized on
  demand via `synth.py` (opt-in).
- Geometry is stored **normalized** (0.0–1.0 of the page) as both an
  axis-aligned bbox and a polygon, kept in sync. `Page.width/height/unit`
  anchor denormalization back to provider pixels (or Azure inches).
- Confidence is always stored 0.0–1.0 internally; parsers rescale.
- `provider_meta` on every node carries source-specific fields verbatim, so a
  same-format round-trip is best-effort lossless.

### Format-specific notes

- **Tesseract / hOCR** have a paragraph level the model lacks; it is carried on
  `Line.provider_meta` (`par_num` / `par_id`) and regrouped on emit.
- **Azure** uses flat per-page `words[]`/`lines[]` lists whose nesting is
  reconstructed from character span offsets, and may use `inch` page units.
- **hOCR** is an XHTML string: geometry and confidence live in each element's
  `title` attribute (`bbox`, `x_wconf`). Optional char-level `ocrx_cinfo` is not
  modeled (no glyph level).
- **EasyOCR** is a flat `[polygon, text, confidence]` list with no hierarchy and
  no page dimensions. Each detection becomes a `Line` + single `Word`; page dims
  are inferred from the max extent of all polygons (pass a
  `{"width", "height", "results"}` wrapper to supply true dims).

## Tests

```
python -m pytest tests/
```

Each format has a round-trip test (provider → `Document` → provider) plus
cross-format bridge tests. Tests are stdlib-only and need no OCR binaries,
except `test_real_tesseract`, which runs only if the `tesseract` binary and PIL
are installed.

## License

MIT — see [LICENSE](LICENSE).
