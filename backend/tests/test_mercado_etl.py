"""ETL de inteligência de mercado: coletar_resultados → resultados_itens.

Tudo via cliente_fake (fixture resultados_item.json, item 1 = MEDCOM), NUNCA
bate na API real. Cobre: gravação denormalizada, idempotência (upsert),
pregão sem resultado não grava, e o endpoint POST /mercado/coletar.
"""
import pytest

from app.services import resultados

CNPJ = "01613770000172"


def _patch_pncp(monkeypatch, cliente):
    from app import pncp as pncp_mod
    monkeypatch.setattr(pncp_mod, "cliente", lambda: cliente)


def _criar_pregao(con, **extra):
    cols = {
        "cnpj": CNPJ, "ano": 2026, "seq": 67, "numero_controle": "NC-MKT",
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
        " valor_unit_estimado, valor_total, sigiloso, ncm_pncp) VALUES (?,?,?,?,?,?,?,?,?)",
        [(pregao_id, *it) for it in itens],
    )
    con.commit()


def test_coleta_grava_item_homologado_denormalizado(con, cliente_fake):
    """Item 1 (MEDCOM, hom_unit 630, qtd 7, estimado 900 → deságio 0.30) é
    gravado em resultados_itens com vencedor + denormalização (orgao/uf) +
    ncm de itens_pregao. Item 2 (sem resultado) NÃO entra."""
    pid = _criar_pregao(con)
    _inserir_itens(con, pid, [
        # numero, descricao, qtd, unidade, valor_unit_estimado, valor_total, sigiloso, ncm_pncp
        (1, "Item homologado", 7, "UN", 900.0, 6300.0, 0, "85183000"),
        (2, "Item ainda aberto", 3, "UN", 500.0, 1500.0, 0, None),
    ])
    out = resultados.coletar_resultados(con, pregao_ids=[pid], cliente=cliente_fake)
    assert out["pregoes_processados"] == 1
    assert out["pregoes_homologados"] == 1
    assert out["itens_gravados"] == 1

    rows = con.execute(
        "SELECT * FROM resultados_itens WHERE pregao_id=?", (pid,)
    ).fetchall()
    assert len(rows) == 1
    r = rows[0]
    assert r["numero_item"] == 1
    assert r["vencedor_cnpj"] == "34318729000122"
    assert r["vencedor_nome"] == "MEDCOM - DISTRIBUIDORA HOSPITALAR LTDA"
    assert r["vencedor_porte"] == "Demais"
    assert r["valor_homologado_unit"] == 630.0
    assert r["qtd_homologada"] == 7.0
    assert r["valor_estimado_unit"] == 900.0
    assert r["desagio_real_pct"] == pytest.approx(0.30)
    assert r["data_resultado"] == "2026-05-21"
    # denormalização do pregão
    assert r["orgao_nome"] == "Município de Imbaú"
    assert r["uf"] == "PR"
    assert r["cnpj"] == CNPJ
    assert r["ano"] == 2026
    assert r["seq"] == 67
    # ncm resolvido de itens_pregao
    assert r["ncm"] == "85183000"
    assert r["unidade"] == "UN"
    assert r["coletado_em"] is not None


def test_idempotente_rodar_2x_nao_duplica(con, cliente_fake):
    """UNIQUE(pregao_id, numero_item) + upsert: rodar 2x mantém 1 linha por item."""
    pid = _criar_pregao(con, numero_controle="NC-MKT-IDEM")
    _inserir_itens(con, pid, [
        (1, "Item homologado", 7, "UN", 900.0, 6300.0, 0, "85183000"),
    ])
    resultados.coletar_resultados(con, pregao_ids=[pid], cliente=cliente_fake)
    out2 = resultados.coletar_resultados(con, pregao_ids=[pid], cliente=cliente_fake)
    assert out2["itens_gravados"] == 1  # upsert, não novo INSERT
    total = con.execute(
        "SELECT COUNT(*) c FROM resultados_itens WHERE pregao_id=?", (pid,)
    ).fetchone()["c"]
    assert total == 1


def test_pregao_sem_resultado_nao_grava(con, cliente_fake):
    """Pregão só com itens sem resultado (nenhum numero==1) → nada gravado."""
    pid = _criar_pregao(con, numero_controle="NC-MKT-ABERTO")
    _inserir_itens(con, pid, [
        (2, "Item aberto A", 3, "UN", 500.0, 1500.0, 0, None),
        (3, "Item aberto B", 1, "UN", 200.0, 200.0, 0, None),
    ])
    out = resultados.coletar_resultados(con, pregao_ids=[pid], cliente=cliente_fake)
    assert out["pregoes_processados"] == 1
    assert out["pregoes_homologados"] == 0
    assert out["itens_gravados"] == 0
    total = con.execute(
        "SELECT COUNT(*) c FROM resultados_itens WHERE pregao_id=?", (pid,)
    ).fetchone()["c"]
    assert total == 0


def test_coleta_todos_quando_pregao_ids_none(con, cliente_fake):
    """pregao_ids None → varre todos os pregões da tabela."""
    p1 = _criar_pregao(con, numero_controle="NC-MKT-A")
    _inserir_itens(con, p1, [(1, "Hom", 7, "UN", 900.0, 6300.0, 0, "85183000")])
    p2 = _criar_pregao(con, numero_controle="NC-MKT-B", seq=68)
    _inserir_itens(con, p2, [(2, "Aberto", 3, "UN", 500.0, 1500.0, 0, None)])
    out = resultados.coletar_resultados(con, cliente=cliente_fake)
    assert out["pregoes_processados"] == 2
    assert out["pregoes_homologados"] == 1
    assert out["itens_gravados"] == 1


def test_endpoint_coletar_200(client, con, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    pid = _criar_pregao(con, numero_controle="NC-MKT-EP")
    _inserir_itens(con, pid, [
        (1, "Item homologado", 7, "UN", 900.0, 6300.0, 0, "85183000"),
        (2, "Item aberto", 3, "UN", 500.0, 1500.0, 0, None),
    ])
    r = client.post("/mercado/coletar", json={"pregao_ids": [pid]})
    assert r.status_code == 200
    body = r.json()
    assert body["pregoes_processados"] == 1
    assert body["pregoes_homologados"] == 1
    assert body["itens_gravados"] == 1


def test_endpoint_coletar_sem_body_200(client, con, cliente_fake, monkeypatch):
    """Sem body → varre todos; deve responder 200 com contagens."""
    _patch_pncp(monkeypatch, cliente_fake)
    pid = _criar_pregao(con, numero_controle="NC-MKT-EP2")
    _inserir_itens(con, pid, [(1, "Hom", 7, "UN", 900.0, 6300.0, 0, "85183000")])
    r = client.post("/mercado/coletar")
    assert r.status_code == 200
    assert r.json()["itens_gravados"] == 1
