"""P7 — fonte EM MASSA da API de Consulta do PNCP (§4.4).

Navegação SEM palavra-chave (status recebendo + tipo edital) usa o endpoint
bulk `consulta/v1/contratacoes/proposta`, onde TODO registro já traz
`valorTotalEstimado`. Com palavra-chave segue na busca textual (§4.1).

Usa o cliente_fake (fixtures reais) monkeypatchado em pncp.cliente.
"""
from app import pncp as pncp_mod


def _patch_pncp(monkeypatch, cliente):
    monkeypatch.setattr(pncp_mod, "cliente", lambda: cliente)


# ---------- dispatch: bulk vs busca textual ----------

def test_descobrir_sem_q_recebendo_usa_consulta(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    r = client.get("/descobrir")
    assert r.status_code == 200
    corpo = r.json()
    # usou a CONSULTA em massa, não a busca textual
    assert cliente_fake.chamadas["consulta"] == 1
    assert cliente_fake.chamadas["buscar"] == 0
    assert corpo["fonte"] == "consulta"
    # total = totalRegistros da fixture; exato (1 combinação, sem exclusão)
    assert corpo["total"] == 4874
    assert corpo["total_exato"] is True
    assert len(corpo["itens"]) == 10  # 10 registros na fixture


def test_descobrir_com_q_usa_busca_textual(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    r = client.get("/descobrir?q=áudio")
    assert r.status_code == 200
    corpo = r.json()
    # com termo → busca textual (§4.1), nunca a consulta em massa
    assert cliente_fake.chamadas["buscar"] == 1
    assert cliente_fake.chamadas["consulta"] == 0
    assert corpo["fonte"] == "busca"
    assert corpo["total"] == 39           # total da fixture de busca


def test_descobrir_status_encerradas_sem_q_usa_busca(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    r = client.get("/descobrir?status=encerradas")
    assert r.status_code == 200
    # status != recebendo_proposta → fora do bulk, mesmo sem termo
    assert cliente_fake.chamadas["consulta"] == 0
    assert cliente_fake.chamadas["buscar"] == 1
    assert r.json()["fonte"] == "busca"


def test_descobrir_tipo_ata_sem_q_usa_busca(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    r = client.get("/descobrir?tipos_documento=ata")
    assert r.status_code == 200
    # tipo != edital → fora do bulk
    assert cliente_fake.chamadas["consulta"] == 0
    assert cliente_fake.chamadas["buscar"] == 1
    assert r.json()["fonte"] == "busca"


# ---------- mapeamento dos registros da consulta ----------

def test_consulta_mapeia_registro_para_shape_de_item(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    itens = client.get("/descobrir").json()["itens"]
    # primeiro registro da fixture (Laranjal Paulista, valorTotalEstimado 100.0)
    item = itens[0]
    assert item["numero_controle"] == "46634606000180-1-000028/2024"
    assert item["valor_global"] == 100.0           # ← valorTotalEstimado embutido
    assert item["uf"] == "SP"
    assert item["municipio"] == "Laranjal Paulista"
    assert item["cnpj"] == "46634606000180"
    assert item["ano"] == 2024
    assert item["seq"] == 28
    # título montado: {tipoInstrumentoConvocatorioNome} nº {numeroCompra}/{anoCompra}
    assert item["titulo"] == "Edital de Chamamento Público nº 5/2024"
    assert item["modalidade"] == "Credenciamento"
    # campos para o cartão e o importar
    for campo in ("titulo", "orgao", "uf", "cnpj", "ano", "seq",
                  "ja_no_radar", "pregao_id", "hit"):
        assert campo in item


def test_consulta_hit_cru_completo_para_importar(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    item = client.get("/descobrir").json()["itens"][0]
    hit = item["hit"]
    # o hit pseudo-busca traz as chaves crus que persistir_hit espera
    assert hit["numero_controle_pncp"] == item["numero_controle"]
    assert hit["title"] == "Edital de Chamamento Público nº 5/2024"
    assert hit["orgao_cnpj"] == "46634606000180"
    assert hit["orgao_nome"] == "MUNICIPIO DE LARANJAL PAULISTA"
    assert hit["ano"] == 2024
    assert hit["numero_sequencial"] == 28
    assert hit["valor_global"] == 100.0
    assert hit["municipio_nome"] == "Laranjal Paulista"
    assert hit["uf"] == "SP"
    assert hit["unidade_nome"]
    # amparoLegal é objeto {nome, descricao} → texto extraído
    assert hit["fundamentacao_legal"] and "Credenciamento" in hit["fundamentacao_legal"]


def test_importar_registro_da_consulta_cria_pregao_com_valor(client, con,
                                                             cliente_fake, monkeypatch):
    """Fluxo completo: o hit pseudo-busca da consulta importa com valor_global."""
    _patch_pncp(monkeypatch, cliente_fake)
    item = client.get("/descobrir").json()["itens"][0]

    r = client.post("/descobrir/importar", json={
        "numero_controle": item["numero_controle"], "hit": item["hit"],
    })
    assert r.status_code == 200
    pregao = r.json()
    assert pregao["numero_controle"] == "46634606000180-1-000028/2024"
    assert pregao["valor_global"] == 100.0         # ← valor oficial persistido
    assert pregao["busca_id"] is None
    assert pregao["link_pncp"].startswith("https://pncp.gov.br/app/editais/")
    # idempotente
    r2 = client.post("/descobrir/importar", json={
        "numero_controle": item["numero_controle"], "hit": item["hit"],
    })
    assert r2.json()["id"] == pregao["id"]
    assert con.execute("SELECT COUNT(*) c FROM pregoes").fetchone()["c"] == 1


# ---------- params do bulk: janela, modalidade, uf, fan-out ----------

def test_consulta_envia_data_final_futura(client, cliente_fake, monkeypatch):
    from datetime import date, timedelta
    _patch_pncp(monkeypatch, cliente_fake)
    client.get("/descobrir")
    chamada = cliente_fake.consultas[-1]
    esperado = (date.today() + timedelta(days=90)).strftime("%Y%m%d")
    assert chamada["data_final"] == esperado
    # sem filtro → modalidade/uf vazios
    assert chamada["modalidade"] == ""
    assert chamada["uf"] == ""


def test_consulta_uma_modalidade_repassa_id(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    r = client.get("/descobrir?modalidades=6")
    assert r.status_code == 200
    assert cliente_fake.chamadas["consulta"] == 1
    assert cliente_fake.consultas[-1]["modalidade"] == "6"


def test_consulta_multi_modalidades_uma_chamada_por_id(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    r = client.get("/descobrir?modalidades=6,8")
    assert r.status_code == 200
    # 2 modalidades → 2 chamadas, uma por id
    assert cliente_fake.chamadas["consulta"] == 2
    mods = sorted(c["modalidade"] for c in cliente_fake.consultas)
    assert mods == ["6", "8"]
    # somou totalRegistros das duas; >1 combinação → não exato
    assert r.json()["total"] == 4874 * 2
    assert r.json()["total_exato"] is False


def test_consulta_modalidade_x_uf_produto_cartesiano(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    r = client.get("/descobrir?modalidades=6,8&ufs=SP,RJ")
    assert r.status_code == 200
    # 2 modalidades × 2 UFs = 4 chamadas
    assert cliente_fake.chamadas["consulta"] == 4
    combos = sorted((c["modalidade"], c["uf"]) for c in cliente_fake.consultas)
    assert combos == [("6", "RJ"), ("6", "SP"), ("8", "RJ"), ("8", "SP")]


def test_consulta_excesso_modalidades_filtra_no_client(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    # 6 modalidades > limite (5) → ignora o filtro server-side: 1 chamada sem mod
    r = client.get("/descobrir?modalidades=1,2,3,4,5,6")
    assert r.status_code == 200
    assert cliente_fake.chamadas["consulta"] == 1
    assert cliente_fake.consultas[-1]["modalidade"] == ""


# ---------- exclusão como pós-filtro no bulk ----------

def test_consulta_exclusao_pos_filtra_e_marca_inexato(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    # exclui "leiloeiros" → derruba o 1º registro (objeto fala em leiloeiros)
    r = client.get("/descobrir?excluir=leiloeiros")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["fonte"] == "consulta"
    ncs = [i["numero_controle"] for i in corpo["itens"]]
    assert "46634606000180-1-000028/2024" not in ncs   # derrubado
    assert len(ncs) == 9                               # 10 - 1
    assert corpo["total_exato"] is False               # exclusão → não exato


# ---------- ja_no_radar no bulk ----------

def test_consulta_marca_ja_no_radar(client, con, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    nc = "46634606000180-1-000028/2024"
    con.execute(
        "INSERT INTO pregoes (cnpj, ano, seq, numero_controle) VALUES (?,?,?,?)",
        ("46634606000180", 2024, 28, nc),
    )
    con.commit()
    local_id = con.execute(
        "SELECT id FROM pregoes WHERE numero_controle=?", (nc,)
    ).fetchone()["id"]
    itens = client.get("/descobrir").json()["itens"]
    achado = next(i for i in itens if i["numero_controle"] == nc)
    assert achado["ja_no_radar"] is True
    assert achado["pregao_id"] == local_id


# ---------- cliente PNCP: detalhe_compra ----------

def test_detalhe_compra_fake(cliente_fake):
    d = cliente_fake.detalhe_compra("46634606000180", 2024, 28)
    assert d["valorTotalEstimado"] == 12345.67
    assert cliente_fake.chamadas["detalhe"] == 1


def test_detalhe_compra_monta_url_consulta(tmp_path, monkeypatch):
    """detalhe_compra bate no caminho consulta/v1 (não no pncp/v1 que dá 301)."""
    import httpx
    monkeypatch.setattr("time.sleep", lambda s: None)
    capturado = {}

    def handler(request):
        capturado["url"] = str(request.url)
        return httpx.Response(200, json={"valorTotalEstimado": 50.0})

    cli = pncp_mod.ClientePNCP(cache_dir=tmp_path)
    cli._http = httpx.Client(
        transport=httpx.MockTransport(handler), headers={"User-Agent": "teste"},
    )
    d = cli.detalhe_compra("01613770000172", 2026, 67, usar_cache=False)
    assert d["valorTotalEstimado"] == 50.0
    assert "/api/consulta/v1/orgaos/01613770000172/compras/2026/67" in capturado["url"]


def test_consulta_propostas_monta_params(tmp_path, monkeypatch):
    """consulta_propostas envia dataFinal sempre; modalidade/uf só quando truthy."""
    import httpx
    monkeypatch.setattr("time.sleep", lambda s: None)
    capturado = {}

    def handler(request):
        capturado["url"] = str(request.url)
        return httpx.Response(200, json={"data": [], "totalRegistros": 0})

    cli = pncp_mod.ClientePNCP(cache_dir=tmp_path)
    cli._http = httpx.Client(
        transport=httpx.MockTransport(handler), headers={"User-Agent": "teste"},
    )
    cli.consulta_propostas("20260910", modalidade="6", uf="SP", usar_cache=False)
    url = capturado["url"]
    assert "dataFinal=20260910" in url
    assert "codigoModalidadeContratacao=6" in url
    assert "uf=SP" in url
    assert "/contratacoes/proposta" in url

    # sem modalidade/uf → params omitidos
    capturado.clear()
    cli.consulta_propostas("20260910", usar_cache=False)
    assert "codigoModalidadeContratacao" not in capturado["url"]
    assert "uf=" not in capturado["url"]
