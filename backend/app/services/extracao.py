"""Extração de texto de PDF (CLAUDE.md §6.3).

pymupdf4llm para texto nativo; se a densidade média for < 200 chars/página,
tenta fallback OCR via docling (dependência opcional — se ausente, segue com
o texto nativo e loga aviso).
"""
import logging
from pathlib import Path

log = logging.getLogger("radar.extracao")

DENSIDADE_MINIMA = 200  # chars por página


def extrair_paginas(pdf_path: Path | str) -> list[str]:
    """Retorna o texto por página (índice 0 = página 1)."""
    import pymupdf4llm

    paginas_md = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True)
    paginas = [p.get("text", "") for p in paginas_md]

    densidade = (sum(len(p) for p in paginas) / len(paginas)) if paginas else 0
    if densidade < DENSIDADE_MINIMA:
        log.warning("Densidade baixa (%.0f chars/pág) em %s — tentando OCR", densidade, pdf_path)
        ocr = _fallback_ocr(pdf_path)
        if ocr is not None:
            return ocr
    return paginas


def _fallback_ocr(pdf_path: Path | str) -> list[str] | None:
    """OCR via docling, se instalado. PDF escaneado sem docling → texto nativo mesmo."""
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        log.warning("docling não instalado — sem OCR; usando texto nativo")
        return None
    try:
        conv = DocumentConverter()
        resultado = conv.convert(str(pdf_path))
        doc = resultado.document
        n_paginas = max((getattr(p, "page_no", 0) for p in doc.pages.values()), default=1)
        paginas = [""] * n_paginas
        for item, _nivel in doc.iterate_items():
            for prov in getattr(item, "prov", []):
                idx = prov.page_no - 1
                if 0 <= idx < n_paginas and hasattr(item, "text"):
                    paginas[idx] += item.text + "\n"
        return paginas
    except Exception as exc:  # OCR é melhor-esforço
        log.error("Fallback OCR falhou em %s: %s", pdf_path, exc)
        return None
