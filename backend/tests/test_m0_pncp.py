"""M0 — cliente PNCP: cache, backoff, parsing (sem bater na API real)."""
import httpx
import pytest

from app import pncp


def _cliente_com_transport(tmp_path, handler):
    cli = pncp.ClientePNCP(cache_dir=tmp_path)
    cli._http = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": "teste"},
    )
    return cli


def test_cache_evita_segunda_requisicao(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    chamadas = {"n": 0}

    def handler(request):
        chamadas["n"] += 1
        return httpx.Response(200, json={"items": [{"x": 1}], "total": 1})

    cli = _cliente_com_transport(tmp_path, handler)
    r1 = cli.buscar("áudio", ufs="SP")
    r2 = cli.buscar("áudio", ufs="SP")
    assert r1 == r2
    assert chamadas["n"] == 1  # segunda veio do cache local


def test_backoff_em_erro_5xx(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    chamadas = {"n": 0}

    def handler(request):
        chamadas["n"] += 1
        if chamadas["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"items": [], "total": 0})

    cli = _cliente_com_transport(tmp_path, handler)
    resp = cli.buscar("áudio", usar_cache=False)
    assert resp == {"items": [], "total": 0}
    assert chamadas["n"] == 3  # 2 falhas + 1 sucesso


def test_erro_persistente_estoura(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)

    def handler(request):
        return httpx.Response(500)

    cli = _cliente_com_transport(tmp_path, handler)
    with pytest.raises(RuntimeError):
        cli.buscar("áudio", usar_cache=False)


def test_204_vira_lista_vazia(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)

    def handler(request):
        return httpx.Response(204)

    cli = _cliente_com_transport(tmp_path, handler)
    assert cli.itens("123", 2026, 1, usar_cache=False) == []


def test_nome_do_content_disposition():
    f = pncp._nome_do_content_disposition
    assert f('attachment; filename="Edital_27.pdf"') == "Edital_27.pdf"
    assert f("attachment; filename=Edital 27.pdf") == "Edital 27.pdf"
    assert f("attachment; filename*=UTF-8''Edital%2027.pdf") == "Edital%2027.pdf"
    assert f("") is None
    # separadores de caminho são higienizados
    assert "/" not in f('attachment; filename="a/b\\c.pdf"')


def test_link_pncp():
    assert pncp.link_pncp("01613770000172", 2026, 67) == \
        "https://pncp.gov.br/app/editais/01613770000172/2026/67"


def test_fixtures_reais_tem_campos_esperados():
    """As respostas reais gravadas têm o shape documentado no CLAUDE.md §4."""
    from tests.conftest import carregar_fixture

    busca = carregar_fixture("search_audio_sp.json")
    assert "items" in busca and "total" in busca
    hit = busca["items"][0]
    for campo in ("title", "orgao_cnpj", "ano", "numero_sequencial",
                  "numero_controle_pncp", "uf", "situacao_nome"):
        assert campo in hit

    itens = carregar_fixture("itens_01613770000172_2026_67.json")
    item = itens[0]
    for campo in ("numeroItem", "descricao", "quantidade", "unidadeMedida",
                  "valorUnitarioEstimado", "orcamentoSigiloso", "ncmNbsCodigo"):
        assert campo in item

    arquivos = carregar_fixture("arquivos_01613770000172_2026_67.json")
    assert arquivos[0]["tipoDocumentoNome"] == "Edital"
    assert arquivos[0]["url"].startswith("https://pncp.gov.br/")
