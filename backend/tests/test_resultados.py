"""Resultados do pregão — vencedor + deságio REAL por item (inteligência de
mercado). Tudo via cliente_fake (fixture resultados_item.json), NUNCA bate na
API real. O fake serve a fixture para numeroItem==1 e [] para os demais.
"""
import pytest

from app.services import resultados

CNPJ = "01613770000172"


def _patch_pncp(monkeypatch, cliente):
    from app import pncp as pncp_mod
    monkeypatch.setattr(pncp_mod, "cliente", lambda: cliente)


def _criar_pregao(con, **extra):
    cols = {
        "cnpj": CNPJ, "ano": 2026, "seq": 67, "numero_controle": "NC-RES",
        "titulo": "Pregão homologado", "descricao": "x",
        "orgao": "Município de Imbaú", "municipio": "Imbaú", "uf": "PR",
        "modalidade": "Pregão - Eletrônico", "situacao": "Homologado",
        "data_fim_vigencia": "2026-06-01",
        "valor_global": 5000.0, "link_pncp": "https://pncp.gov.br/app/editais/x",
    }
    cols.update(extra)
    campos = ", ".join(cols)
    marks = ", ".join("?" for _ in cols)
    con.execute(f"INSERT INTO pregoes({campos}) VALUES ({marks})", tuple(cols.values()))
    con.commit()
    return con.execute("SELECT id FROM pregoes WHERE numero_controle=?",
                       (cols["numero_controle"],)).fetchone()["id"]


def _inserir_itens(con, pregao_id, itens):
    con.executemany(
        "INSERT INTO itens_pregao(pregao_id, numero, descricao, qtd, unidade,"
        " valor_unit_estimado, valor_total, sigiloso) VALUES (?,?,?,?,?,?,?,?)",
        [(pregao_id, *it) for it in itens],
    )
    con.commit()


# ---------- service: cálculo por item + agregado ----------

def test_item_com_resultado_calcula_desagio(con, cliente_fake):
    """Item 1 (fixture MEDCOM: homologado_unit 630, qtd 7) com estimado 900 →
    deságio real = (900-630)/900 = 0.30; item 2 sem resultado → homologado False.
    """
    pid = _criar_pregao(con)
    _inserir_itens(con, pid, [
        # numero, descricao, qtd, unidade, valor_unit_estimado, valor_total, sigiloso
        (1, "Item homologado", 7, "UN", 900.0, 6300.0, 0),
        (2, "Item ainda aberto", 3, "UN", 500.0, 1500.0, 0),
    ])
    out = resultados.resultados_do_pregao(con, pid, cliente=cliente_fake)

    assert out["homologado"] is True
    assert len(out["itens"]) == 2

    item1 = next(d for d in out["itens"] if d["numero"] == 1)
    assert item1["homologado"] is True
    assert item1["vencedor_nome"] == "MEDCOM - DISTRIBUIDORA HOSPITALAR LTDA"
    assert item1["vencedor_cnpj"] == "34318729000122"
    assert item1["porte"] == "Demais"  # porteFornecedorId 3
    assert item1["valor_homologado_unit"] == 630.0
    assert item1["qtd_homologada"] == 7.0
    assert item1["valor_homologado_total"] == 4410.0
    assert item1["data_resultado"] == "2026-05-21"
    assert item1["desagio_real_pct"] == pytest.approx(0.30)

    item2 = next(d for d in out["itens"] if d["numero"] == 2)
    assert item2["homologado"] is False
    assert item2["vencedor_nome"] is None
    assert item2["desagio_real_pct"] is None


def test_resumo_agregado(con, cliente_fake):
    """Resumo: 1 homologado; deságio médio ponderado = 0.30 (só item 1 tem
    deságio); economia = (900-630)*7 = 1890."""
    pid = _criar_pregao(con)
    _inserir_itens(con, pid, [
        (1, "Item homologado", 7, "UN", 900.0, 6300.0, 0),
        (2, "Item ainda aberto", 3, "UN", 500.0, 1500.0, 0),
    ])
    out = resultados.resultados_do_pregao(con, pid, cliente=cliente_fake)
    resumo = out["resumo"]
    assert resumo["n_homologados"] == 1
    assert resumo["desagio_medio_real"] == pytest.approx(0.30)
    assert resumo["economia_total"] == pytest.approx(1890.0)


def test_nenhum_resultado_homologado_false(con, cliente_fake):
    """Pregão só com itens SEM resultado (nenhum numero==1) → homologado False,
    resumo None, todos os itens com homologado False (princípio nº 1)."""
    pid = _criar_pregao(con, numero_controle="NC-RES-ABERTO")
    _inserir_itens(con, pid, [
        (2, "Item aberto A", 3, "UN", 500.0, 1500.0, 0),
        (3, "Item aberto B", 1, "UN", 200.0, 200.0, 0),
    ])
    out = resultados.resultados_do_pregao(con, pid, cliente=cliente_fake)
    assert out["homologado"] is False
    assert out["resumo"] is None
    assert all(d["homologado"] is False for d in out["itens"])


def test_falha_de_um_item_nao_derruba_lote(con):
    """Exceção na chamada de UM item é logada e tratada como sem resultado; o
    lote continua (o item 1 com sucesso ainda homologa)."""
    from tests.conftest import carregar_fixture

    class ClienteParcial:
        def resultados_item(self, cnpj, ano, seq, numero_item, usar_cache=True):
            if int(numero_item) == 1:
                return carregar_fixture("resultados_item.json")
            raise RuntimeError("PNCP indisponível para este item")

    pid = _criar_pregao(con, numero_controle="NC-RES-PARCIAL")
    _inserir_itens(con, pid, [
        (1, "Item homologado", 7, "UN", 900.0, 6300.0, 0),
        (2, "Item que falha", 3, "UN", 500.0, 1500.0, 0),
    ])
    out = resultados.resultados_do_pregao(con, pid, cliente=ClienteParcial())
    assert out["homologado"] is True
    item2 = next(d for d in out["itens"] if d["numero"] == 2)
    assert item2["homologado"] is False


def test_pregao_inexistente_levanta_valueerror(con, cliente_fake):
    with pytest.raises(ValueError):
        resultados.resultados_do_pregao(con, 999999, cliente=cliente_fake)


# ---------- endpoint ----------

def test_endpoint_resultados_200(client, con, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    pid = _criar_pregao(con, numero_controle="NC-RES-EP")
    _inserir_itens(con, pid, [
        (1, "Item homologado", 7, "UN", 900.0, 6300.0, 0),
        (2, "Item aberto", 3, "UN", 500.0, 1500.0, 0),
    ])
    r = client.get(f"/pregoes/{pid}/resultados")
    assert r.status_code == 200
    body = r.json()
    assert body["homologado"] is True
    assert body["resumo"]["n_homologados"] == 1
    item1 = next(d for d in body["itens"] if d["numero"] == 1)
    assert item1["vencedor_cnpj"] == "34318729000122"


def test_endpoint_resultados_404(client):
    r = client.get("/pregoes/999999/resultados")
    assert r.status_code == 404
