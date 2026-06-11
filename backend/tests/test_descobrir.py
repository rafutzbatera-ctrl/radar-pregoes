"""Feature — PNCP ao vivo: explorar a busca do PNCP sem persistir + importar.

Usa o cliente_fake (fixture real de busca) monkeypatchado em pncp.cliente,
sem bater na API.
"""
from app import pncp as pncp_mod


def _patch_pncp(monkeypatch, cliente):
    monkeypatch.setattr(pncp_mod, "cliente", lambda: cliente)


def test_descobrir_retorna_total_e_itens_adaptados(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    r = client.get("/descobrir?q=áudio&ufs=SP")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["total"] == 39       # fixture real: total nacional do hit
    assert corpo["pagina"] == 1
    assert corpo["tamanho"] == 50
    assert len(corpo["itens"]) == 10  # fixture real: 10 hits
    item = corpo["itens"][0]
    # campos adaptados para o cartão
    for campo in ("numero_controle", "titulo", "orgao", "uf", "cnpj", "ano", "seq",
                  "ja_no_radar", "pregao_id", "hit"):
        assert campo in item
    assert item["ja_no_radar"] is False
    assert item["pregao_id"] is None
    # hit cru preservado para reenviar no importar
    assert item["hit"]["numero_controle_pncp"] == item["numero_controle"]


def test_descobrir_q_vazio_nao_quebra(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    r = client.get("/descobrir")
    assert r.status_code == 200
    assert r.json()["total"] == 39


def test_descobrir_marca_ja_no_radar(client, con, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    # pega o numero_controle do primeiro hit e insere localmente
    hit = cliente_fake.buscar("áudio")["items"][0]
    nc = hit["numero_controle_pncp"]
    con.execute(
        "INSERT INTO pregoes (cnpj, ano, seq, numero_controle) VALUES (?,?,?,?)",
        (hit["orgao_cnpj"], int(hit["ano"]), int(hit["numero_sequencial"]), nc),
    )
    con.commit()
    local_id = con.execute(
        "SELECT id FROM pregoes WHERE numero_controle=?", (nc,)
    ).fetchone()["id"]

    itens = client.get("/descobrir?q=áudio").json()["itens"]
    achado = next(i for i in itens if i["numero_controle"] == nc)
    assert achado["ja_no_radar"] is True
    assert achado["pregao_id"] == local_id


def test_importar_cria_pregao_e_e_idempotente(client, con, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    itens = client.get("/descobrir?q=áudio").json()["itens"]
    alvo = itens[0]

    r = client.post("/descobrir/importar", json={
        "numero_controle": alvo["numero_controle"], "hit": alvo["hit"],
    })
    assert r.status_code == 200
    pregao = r.json()
    assert pregao["numero_controle"] == alvo["numero_controle"]
    assert pregao["novo"] == 1
    assert pregao["link_pncp"].startswith("https://pncp.gov.br/app/editais/")
    assert pregao["busca_id"] is None
    assert con.execute("SELECT COUNT(*) c FROM pregoes").fetchone()["c"] == 1

    # repetir não duplica e retorna o existente (mesmo id)
    r2 = client.post("/descobrir/importar", json={
        "numero_controle": alvo["numero_controle"], "hit": alvo["hit"],
    })
    assert r2.status_code == 200
    assert r2.json()["id"] == pregao["id"]
    assert con.execute("SELECT COUNT(*) c FROM pregoes").fetchone()["c"] == 1


def test_descobrir_pncp_fora_retorna_503(client, monkeypatch):
    class ClienteQuebrado:
        def buscar(self, *a, **k):
            raise RuntimeError("PNCP indisponível após 5 tentativas")

    _patch_pncp(monkeypatch, ClienteQuebrado())
    r = client.get("/descobrir?q=áudio")
    assert r.status_code == 503
