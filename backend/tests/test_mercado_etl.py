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


class _ClienteResultadoFixo:
    """Cliente fake que devolve uma lista de resultados FIXA para o item 1
    (e [] para os demais). Permite testar item homologado SEM preço."""

    def __init__(self, resultado_item1):
        self._r = resultado_item1

    def resultados_item(self, cnpj, ano, seq, numero_item, usar_cache=True):
        return self._r if int(numero_item) == 1 else []


class _ClienteMutavel:
    """Cliente fake cuja resposta para o item 1 MUDA entre coletas (lista de
    respostas consumida em ordem). Para testar reconciliação."""

    def __init__(self, respostas_item1):
        self._respostas = list(respostas_item1)
        self._i = 0

    def resultados_item(self, cnpj, ano, seq, numero_item, usar_cache=True):
        if int(numero_item) != 1:
            return []
        idx = min(self._i, len(self._respostas) - 1)
        return self._respostas[idx]

    def avancar(self):
        self._i += 1


def test_item_homologado_sem_valor_unit_nao_grava(con):
    """Item com vencedor (ordem 1) mas SEM valorUnitarioHomologado NÃO é fato
    de mercado → não grava (não há 'por quanto venceu')."""
    pid = _criar_pregao(con, numero_controle="NC-MKT-SEMVAL")
    _inserir_itens(con, pid, [(1, "Hom sem preço", 7, "UN", 900.0, 6300.0, 0, "85183000")])
    cliente = _ClienteResultadoFixo([{
        "numeroItem": 1,
        "niFornecedor": "34318729000122",
        "nomeRazaoSocialFornecedor": "Sem Preço LTDA",
        "porteFornecedorId": 3,
        "ordemClassificacaoSrp": 1,
        "dataCancelamento": None,
        "valorUnitarioHomologado": None,  # <- sem preço homologado
        "quantidadeHomologada": 7.0,
        "valorTotalHomologado": None,
        "dataResultado": "2026-05-21",
    }])
    out = resultados.coletar_resultados(con, pregao_ids=[pid], cliente=cliente)
    assert out["pregoes_homologados"] == 0
    assert out["itens_gravados"] == 0
    total = con.execute(
        "SELECT COUNT(*) c FROM resultados_itens WHERE pregao_id=?", (pid,)
    ).fetchone()["c"]
    assert total == 0


def test_reconciliacao_apaga_linha_obsoleta(con):
    """1ª coleta grava o item 1; 2ª coleta devolve o MESMO pregão sem o item 1
    como fato (lista vazia = resultado revogado) → a linha SOME."""
    pid = _criar_pregao(con, numero_controle="NC-MKT-RECON")
    _inserir_itens(con, pid, [(1, "Hom", 7, "UN", 900.0, 6300.0, 0, "85183000")])
    venc = {
        "numeroItem": 1,
        "niFornecedor": "34318729000122",
        "nomeRazaoSocialFornecedor": "MEDCOM",
        "porteFornecedorId": 3,
        "ordemClassificacaoSrp": 1,
        "dataCancelamento": None,
        "valorUnitarioHomologado": 630.0,
        "quantidadeHomologada": 7.0,
        "valorTotalHomologado": 4410.0,
        "dataResultado": "2026-05-21",
    }
    cliente = _ClienteMutavel([[venc], []])  # 1ª: homologado; 2ª: nada

    resultados.coletar_resultados(con, pregao_ids=[pid], cliente=cliente)
    assert con.execute(
        "SELECT COUNT(*) c FROM resultados_itens WHERE pregao_id=?", (pid,)
    ).fetchone()["c"] == 1

    cliente.avancar()
    out2 = resultados.coletar_resultados(con, pregao_ids=[pid], cliente=cliente)
    assert out2["pregoes_homologados"] == 0
    assert con.execute(
        "SELECT COUNT(*) c FROM resultados_itens WHERE pregao_id=?", (pid,)
    ).fetchone()["c"] == 0  # linha obsoleta foi apagada


def test_reconciliacao_apaga_item_removido_mantendo_os_demais(con):
    """1ª coleta grava itens 1 e 2; 2ª coleta só traz o item 1 como fato → a
    linha do item 2 some, a do item 1 fica."""
    pid = _criar_pregao(con, numero_controle="NC-MKT-RECON2")
    _inserir_itens(con, pid, [
        (1, "Item 1", 7, "UN", 900.0, 6300.0, 0, "85183000"),
        (2, "Item 2", 3, "UN", 500.0, 1500.0, 0, None),
    ])
    # 1ª coleta: insere item 2 manualmente como linha pré-existente; cliente
    # devolve fato só para item 1 (item 2 = []). Grava item 1; reconcilia
    # apagando qualquer linha de outro numero — então pré-insiro item 2 antes.
    con.execute(
        "INSERT INTO resultados_itens(pregao_id, numero_item, descricao,"
        " valor_homologado_unit, vencedor_cnpj, coletado_em)"
        " VALUES (?,?,?,?,?,datetime('now'))",
        (pid, 2, "Item 2 antigo", 400.0, "99999999000199"),
    )
    con.commit()
    cliente = _ClienteFakeItem1()
    out = resultados.coletar_resultados(con, pregao_ids=[pid], cliente=cliente)
    assert out["itens_gravados"] == 1
    nums = [r["numero_item"] for r in con.execute(
        "SELECT numero_item FROM resultados_itens WHERE pregao_id=? ORDER BY numero_item",
        (pid,),
    ).fetchall()]
    assert nums == [1]  # item 2 (obsoleto) apagado, item 1 mantido


class _ClienteFakeItem1:
    """Igual ao cliente_fake do conftest: item 1 = fixture MEDCOM, resto []."""

    def resultados_item(self, cnpj, ano, seq, numero_item, usar_cache=True):
        if int(numero_item) == 1:
            from tests.conftest import carregar_fixture
            return carregar_fixture("resultados_item.json")
        return []


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
