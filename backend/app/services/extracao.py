"""Extração de texto de PDF (CLAUDE.md §6.3).

pymupdf4llm para texto nativo; se a densidade média for < 200 chars/página,
tenta fallback OCR via docling (dependência opcional — se ausente, segue com
o texto nativo e loga aviso).
"""
import logging
from collections.abc import Callable
from pathlib import Path

from app import settings

log = logging.getLogger("radar.extracao")

DENSIDADE_MINIMA = 200  # chars por página (default; sobreponível por RADAR_OCR_DENSIDADE)

# tipo do seam de OCR: recebe o caminho do PDF, devolve texto por página ou None
OcrBackend = Callable[[Path | str], "list[str] | None"]


def _texto_nativo(pdf_path: Path | str) -> list[str]:
    """Texto nativo por página via pymupdf4llm (ponto de monkeypatch nos testes)."""
    import pymupdf4llm

    paginas_md = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True)
    return [p.get("text", "") for p in paginas_md]


def _ocr_backend(modo: str) -> OcrBackend:
    """Resolve o backend de OCR pelo modo configurado (settings.OCR_MODO).

    "docling" → impl atual (_fallback_ocr); "off" → desliga (sempre None).
    Modos desconhecidos caem em docling (comportamento atual preservado).
    """
    if modo == "off":
        return lambda _p: None
    return _fallback_ocr


def extrair_paginas(
    pdf_path: Path | str,
    ocr: OcrBackend | None = None,
) -> list[str]:
    """Retorna o texto por página (índice 0 = página 1).

    `ocr` é um seam injetável (callable (pdf_path)->list[str]|None) usado quando
    a densidade média fica abaixo de settings.OCR_DENSIDADE_MIN. Se None,
    resolve o backend por settings.OCR_MODO (default "docling"); o default
    preserva 100% o comportamento anterior para os chamadores.
    """
    if ocr is None:
        ocr = _ocr_backend(settings.OCR_MODO)

    paginas = _texto_nativo(pdf_path)

    densidade = (sum(len(p) for p in paginas) / len(paginas)) if paginas else 0
    if densidade < settings.OCR_DENSIDADE_MIN:
        log.warning("Densidade baixa (%.0f chars/pág) em %s — tentando OCR", densidade, pdf_path)
        resultado = ocr(pdf_path)
        if resultado is not None:
            return resultado
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
