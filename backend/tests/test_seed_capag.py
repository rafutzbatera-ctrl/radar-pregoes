"""Teste da derivação de UF no seed da CAPAG (sigla a partir do código IBGE).

Garante que notas ESTADUAIS recebam a sigla da UF mesmo quando o XLSX do
Tesouro não traz coluna 'uf' — sem isso o casamento estadual (UF + esfera 'E')
em capag.py nunca funcionaria em produção. Importa o script por caminho de
arquivo; seed_capag tem guarda __main__, então importar NÃO dispara download.
"""
import importlib.util
import pathlib

import pytest

_P = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "seed_capag.py"


@pytest.fixture(scope="module")
def seed():
    spec = importlib.util.spec_from_file_location("seed_capag", _P)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_uf_estadual_derivada_do_cod_ibge(seed):
    # estado: cod_ibge de 2 dígitos e XLSX sem coluna 'uf' → deriva a sigla
    assert seed._uf_da_linha("41", None) == "PR"
    assert seed._uf_da_linha("35", "") == "SP"


def test_uf_municipal_derivada_do_prefixo(seed):
    # município (Curitiba 4106902) → PR pelos 2 primeiros dígitos do cod_ibge
    assert seed._uf_da_linha("4106902", None) == "PR"


def test_uf_usa_coluna_quando_valida(seed):
    # coluna 'uf' válida (2 letras) prevalece sobre a derivação
    assert seed._uf_da_linha("9999999", "rj") == "RJ"


def test_uf_desconhecida_vira_none(seed):
    assert seed._uf_da_linha("99", None) is None
    assert seed._uf_da_linha(None, None) is None
