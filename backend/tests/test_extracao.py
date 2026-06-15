"""Testes do ramo de densidade/OCR de extracao.extrair_paginas (CLAUDE.md §6.3).

100% offline: o texto nativo (pymupdf4llm) é monkeypatchado e o OCR é injetado
como fake via o parâmetro `ocr=` — não baixa PDF, não instala docling.

Casos:
- densidade ALTA → OCR NÃO é chamado; usa o texto nativo;
- densidade BAIXA → OCR é chamado e seu retorno é usado;
- densidade BAIXA mas OCR retorna None (docling ausente/off) → mantém o nativo.
"""
import pytest

from app.services import extracao


@pytest.fixture
def paginas_nativas(monkeypatch):
    """Permite cravar o texto nativo retornado por _texto_nativo."""
    def _set(paginas):
        monkeypatch.setattr(extracao, "_texto_nativo", lambda _p: paginas)
    return _set


def test_densidade_alta_nao_chama_ocr(paginas_nativas):
    # páginas longas → densidade bem acima do mínimo (200)
    nativas = ["x" * 500, "y" * 500]
    paginas_nativas(nativas)

    chamado = {"ocr": False}

    def ocr_fake(_p):
        chamado["ocr"] = True
        return ["NAO DEVERIA"]

    resultado = extracao.extrair_paginas("qualquer.pdf", ocr=ocr_fake)

    assert resultado == nativas
    assert chamado["ocr"] is False, "OCR não deve rodar com densidade alta"


def test_densidade_baixa_usa_ocr(paginas_nativas):
    # páginas curtíssimas → densidade abaixo de 200 → dispara OCR
    paginas_nativas(["abc", "de"])

    chamado = {"ocr": False}

    def ocr_fake(_p):
        chamado["ocr"] = True
        return ["TEXTO OCR PAGINA 1", "TEXTO OCR PAGINA 2"]

    resultado = extracao.extrair_paginas("escaneado.pdf", ocr=ocr_fake)

    assert chamado["ocr"] is True, "OCR deve rodar com densidade baixa"
    assert resultado == ["TEXTO OCR PAGINA 1", "TEXTO OCR PAGINA 2"]


def test_densidade_baixa_ocr_ausente_mantem_nativo(paginas_nativas):
    # densidade baixa, mas OCR indisponível (None, ex.: docling ausente / RADAR_OCR=off)
    nativas = ["abc", "de"]
    paginas_nativas(nativas)

    resultado = extracao.extrair_paginas("escaneado.pdf", ocr=lambda _p: None)

    assert resultado == nativas, "sem OCR utilizável, mantém o texto nativo"


def test_ocr_backend_off_desliga():
    """settings.OCR_MODO='off' → backend que sempre devolve None."""
    backend = extracao._ocr_backend("off")
    assert backend("qualquer.pdf") is None


def test_ocr_backend_docling_e_o_fallback_atual():
    """Modo 'docling' (e desconhecidos) → a impl atual _fallback_ocr."""
    assert extracao._ocr_backend("docling") is extracao._fallback_ocr
    assert extracao._ocr_backend("xpto") is extracao._fallback_ocr
