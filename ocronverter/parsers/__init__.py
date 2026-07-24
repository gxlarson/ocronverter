"""Parsers: provider JSON -> neutral Document."""

from . import azure, easyocr, google_vision, hocr, tesseract, textract

__all__ = ["google_vision", "textract", "tesseract", "azure", "hocr", "easyocr"]
