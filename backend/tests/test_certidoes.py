"""Minhas certidões — status de validade (puro) + CRUD via API + alertas."""
from datetime import date, timedelta

from app.services import certidoes as svc

HOJE = date(2026, 6, 15)


# ---------- status_certidao (puro, com `hoje` fixo) ----------

def test_status_sem_validade():
    assert svc.status_certidao(None, HOJE) == "sem_validade"
    assert svc.status_certidao("", HOJE) == "sem_validade"


def test_status_vencida():
    ontem = (HOJE - timedelta(days=1)).isoformat()
    assert svc.status_certidao(ontem, HOJE) == "vencida"


def test_status_vence_em_breve_limite_0_vence_hoje():
    # vence HOJE (0 dias) ainda é "vence_em_breve", não "vencida"
    assert svc.status_certidao(HOJE.isoformat(), HOJE) == "vence_em_breve"
    assert svc.dias_restantes(HOJE.isoformat(), HOJE) == 0


def test_status_vence_em_breve_limite_30():
    em30 = (HOJE + timedelta(days=30)).isoformat()
    assert svc.status_certidao(em30, HOJE) == "vence_em_breve"
    assert svc.dias_restantes(em30, HOJE) == 30


def test_status_ok_acima_de_30():
    em31 = (HOJE + timedelta(days=31)).isoformat()
    assert svc.status_certidao(em31, HOJE) == "ok"
    assert svc.dias_restantes(em31, HOJE) == 31


def test_dias_restantes_negativo_quando_vencida():
    passado = (HOJE - timedelta(days=10)).isoformat()
    assert svc.dias_restantes(passado, HOJE) == -10


def test_validade_valida():
    assert svc.validade_valida("2026-12-31")
    assert not svc.validade_valida("31/12/2026")
    assert not svc.validade_valida("não é data")
    assert not svc.validade_valida(None)


# ---------- CRUD via TestClient ----------

def test_criar_e_listar(client):
    r = client.post("/certidoes", json={
        "nome": "CND Federal", "orgao_emissor": "Receita Federal",
        "validade": "2099-01-01", "observacao": "renovar antes"})
    assert r.status_code == 201
    corpo = r.json()
    assert corpo["nome"] == "CND Federal"
    assert corpo["orgao_emissor"] == "Receita Federal"
    assert corpo["status"] == "ok"
    assert corpo["dias_restantes"] is not None
    assert corpo["id"] > 0

    lista = client.get("/certidoes").json()
    assert len(lista) == 1
    assert lista[0]["nome"] == "CND Federal"


def test_criar_sem_nome_422(client):
    assert client.post("/certidoes", json={"nome": "   "}).status_code == 422
    # nome ausente → pydantic 422
    assert client.post("/certidoes", json={}).status_code == 422


def test_criar_validade_invalida_422(client):
    r = client.post("/certidoes",
                    json={"nome": "FGTS", "validade": "31/12/2026"})
    assert r.status_code == 422


def test_criar_sem_validade_status_sem_validade(client):
    r = client.post("/certidoes", json={"nome": "Contrato social"})
    assert r.status_code == 201
    corpo = r.json()
    assert corpo["validade"] is None
    assert corpo["status"] == "sem_validade"
    assert corpo["dias_restantes"] is None


def test_listar_ordenado_por_urgencia(client):
    hoje = date.today()
    # ok (longe)
    client.post("/certidoes", json={
        "nome": "OK", "validade": (hoje + timedelta(days=200)).isoformat()})
    # vencida
    client.post("/certidoes", json={
        "nome": "Vencida", "validade": (hoje - timedelta(days=5)).isoformat()})
    # sem validade
    client.post("/certidoes", json={"nome": "SemValidade"})
    # vence em breve
    client.post("/certidoes", json={
        "nome": "Breve", "validade": (hoje + timedelta(days=10)).isoformat()})

    nomes = [c["nome"] for c in client.get("/certidoes").json()]
    # vencida e breve primeiro; sem_validade e ok depois
    assert nomes[0] == "Vencida"
    assert nomes[1] == "Breve"
    assert set(nomes[2:]) == {"SemValidade", "OK"}
    assert nomes.index("SemValidade") < nomes.index("OK")


def test_patch_atualiza_e_seta_atualizado_em(client):
    cid = client.post("/certidoes", json={"nome": "CND"}).json()["id"]
    r = client.patch(f"/certidoes/{cid}", json={
        "nome": "CND Trabalhista", "validade": "2030-05-05"})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["nome"] == "CND Trabalhista"
    assert corpo["validade"] == "2030-05-05"
    assert corpo["atualizado_em"] is not None
    assert corpo["status"] == "ok"


def test_patch_limpa_validade(client):
    cid = client.post(
        "/certidoes", json={"nome": "X", "validade": "2030-01-01"}).json()["id"]
    r = client.patch(f"/certidoes/{cid}", json={"validade": ""})
    assert r.status_code == 200
    assert r.json()["validade"] is None
    assert r.json()["status"] == "sem_validade"


def test_patch_validade_invalida_422(client):
    cid = client.post("/certidoes", json={"nome": "X"}).json()["id"]
    assert client.patch(
        f"/certidoes/{cid}", json={"validade": "ontem"}).status_code == 422


def test_patch_inexistente_404(client):
    assert client.patch(
        "/certidoes/999", json={"nome": "Nada"}).status_code == 404


def test_delete_remove(client):
    cid = client.post("/certidoes", json={"nome": "Apagar"}).json()["id"]
    assert client.delete(f"/certidoes/{cid}").status_code == 204
    assert client.get("/certidoes").json() == []


def test_delete_inexistente_404(client):
    assert client.delete("/certidoes/999").status_code == 404


# ---------- /certidoes/alertas ----------

def test_alertas_so_traz_urgentes(client):
    hoje = date.today()
    client.post("/certidoes", json={
        "nome": "OK", "validade": (hoje + timedelta(days=200)).isoformat()})
    client.post("/certidoes", json={"nome": "SemValidade"})
    client.post("/certidoes", json={
        "nome": "Vencida", "validade": (hoje - timedelta(days=2)).isoformat()})
    client.post("/certidoes", json={
        "nome": "Breve", "validade": (hoje + timedelta(days=5)).isoformat()})

    r = client.get("/certidoes/alertas").json()
    assert r["total"] == 2
    nomes = {c["nome"] for c in r["certidoes"]}
    assert nomes == {"Vencida", "Breve"}
