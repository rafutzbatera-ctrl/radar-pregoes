"""Endpoints FastAPI (CLAUDE.md §7) sobre banco de teste."""


def test_raiz_tem_aviso(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "PNCP" in r.json()["aviso"]


def test_crud_buscas(client):
    r = client.post("/buscas", json={"nome": "AV SP", "termos": "áudio, vídeo",
                                     "ufs": "SP"})
    assert r.status_code == 201
    busca = r.json()
    assert busca["ativo"] == 1

    r = client.get("/buscas")
    assert len(r.json()) == 1 and r.json()[0]["novos"] == 0

    r = client.patch(f"/buscas/{busca['id']}", json={"ativo": False})
    assert r.json()["ativo"] == 0


def test_crud_catalogo(client):
    r = client.post("/catalogo", json={
        "nome": "Microfone de mesa USB", "custo_unit": 820.0,
        "codigo": "MIC-USB-01", "ncm": "8518.10.00",
        "origem": "2 — Importada", "csosn": "102", "cst": "060",
    })
    assert r.status_code == 201
    produto = r.json()

    r = client.patch(f"/catalogo/{produto['id']}", json={"custo_unit": 850.0})
    assert r.json()["custo_unit"] == 850.0

    assert len(client.get("/catalogo").json()) == 1


def test_config_get_patch_e_validacao(client):
    cfg = client.get("/config").json()
    assert cfg["regime_tributario"] == "simples"

    r = client.patch("/config", json={"regime_tributario": "presumido",
                                      "uf_origem": "GO"})
    assert r.json()["regime_tributario"] == "presumido"
    assert r.json()["uf_origem"] == "GO"

    assert client.patch("/config", json={"regime_tributario": "lucro_real"}).status_code == 400
    assert client.patch("/config", json={"chave_qualquer": "x"}).status_code == 400


def test_fluxo_match_recalcula_pregao(client, con):
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,1,'NC-1')")
    pregao_id = con.execute("SELECT id FROM pregoes").fetchone()["id"]
    con.execute("INSERT INTO catalogo_produtos (id, nome, custo_unit) VALUES (1,'P',100)")
    con.execute("""INSERT INTO itens_pregao
        (pregao_id, numero, descricao, qtd, valor_unit_estimado, produto_id, match_score)
        VALUES (?,1,'Item',10,150,1,0.9)""", (pregao_id,))
    con.commit()
    item_id = con.execute("SELECT id FROM itens_pregao").fetchone()["id"]

    # confirmar o match sugerido
    r = client.post(f"/itens/{item_id}/match", json={"produto_id": 1, "confirmado": True})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["item"]["match_confirmado"] == 1
    assert corpo["pregao"]["lucro_potencial"] == 500.0

    # itens do pregão expõem números crus + margem/lucro calculados
    itens = client.get(f"/pregoes/{pregao_id}/itens").json()
    assert itens[0]["margem"] is not None
    assert itens[0]["produto_nome"] == "P"

    # recusar o match → sai da conta
    r = client.post(f"/itens/{item_id}/match", json={"produto_id": None})
    assert r.json()["pregao"]["lucro_potencial"] is None

    # detalhe do pregão traz agregados
    d = client.get(f"/pregoes/{pregao_id}").json()
    assert d["itens_total"] == 1 and d["itens_confirmados"] == 0


def test_habilitacao_patch_status(client, con):
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,1,'NC-1')")
    pregao_id = con.execute("SELECT id FROM pregoes").fetchone()["id"]
    con.execute("""INSERT INTO habilitacao
        (pregao_id, requisito, categoria, pagina, excerto, verificada)
        VALUES (?,'CND Federal','fiscal',4,'Prova de regularidade…',1)""", (pregao_id,))
    con.commit()
    hid = con.execute("SELECT id FROM habilitacao").fetchone()["id"]

    r = client.patch(f"/habilitacao/{hid}", json={"status_usuario": "ok"})
    assert r.json()["status_usuario"] == "ok"

    assert client.patch(f"/habilitacao/{hid}",
                        json={"status_usuario": "talvez"}).status_code == 422

    lista = client.get(f"/pregoes/{pregao_id}/habilitacao").json()
    assert lista[0]["verificada"] == 1


def test_fiscal_endpoint(client, con):
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, uf) "
                "VALUES ('1',2026,1,'NC-1','SP')")
    pregao_id = con.execute("SELECT id FROM pregoes").fetchone()["id"]
    con.execute("""INSERT INTO itens_pregao (pregao_id, numero, descricao, unidade)
                   VALUES (?,1,'Item','UN')""", (pregao_id,))
    con.commit()
    r = client.get(f"/pregoes/{pregao_id}/fiscal")
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert "contador" in r.json()["aviso"]


def test_arquivos_do_banco_quando_sincronizado(client, con):
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,1,'NC-1')")
    pregao_id = con.execute("SELECT id FROM pregoes").fetchone()["id"]
    con.execute(
        """INSERT INTO arquivos (pregao_id, titulo, tipo, url, caminho_local)
           VALUES (?,'Edital X','Edital','https://pncp.gov.br/x/arquivos/1','/tmp/x.pdf')""",
        (pregao_id,))
    con.commit()
    r = client.get(f"/pregoes/{pregao_id}/arquivos")
    assert r.status_code == 200
    assert r.json()[0]["url"] == "https://pncp.gov.br/x/arquivos/1"
    assert r.json()[0]["tipo"] == "Edital"


def test_arquivos_sem_sincronizar_consulta_pncp(client, con, cliente_fake, monkeypatch):
    """Pregão não sincronizado: o endpoint relê só os METADADOS na API do PNCP
    (sem download) para o PDF oficial ficar a um clique."""
    from app import pncp as pncp_mod
    monkeypatch.setattr(pncp_mod, "cliente", lambda: cliente_fake)
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('01613770000172',2026,67,'NC-67')")
    pregao_id = con.execute("SELECT id FROM pregoes").fetchone()["id"]
    con.commit()
    r = client.get(f"/pregoes/{pregao_id}/arquivos")
    assert r.status_code == 200
    corpo = r.json()
    assert len(corpo) == 1                      # fixture real: 1 arquivo (Edital)
    assert corpo[0]["url"].startswith("https://pncp.gov.br/")
    assert corpo[0]["caminho_local"] is None    # metadados, nada baixado
    assert cliente_fake.chamadas["baixar"] == 0


def test_404s(client):
    assert client.get("/pregoes/999").status_code == 404
    assert client.get("/pregoes/999/arquivos").status_code == 404
    assert client.post("/itens/999/match", json={"produto_id": None}).status_code == 404
    assert client.patch("/habilitacao/999", json={"status_usuario": "ok"}).status_code == 404
    assert client.patch("/catalogo/999", json={"nome": "x"}).status_code == 404
