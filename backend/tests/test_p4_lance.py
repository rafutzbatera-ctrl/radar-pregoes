"""P4 — preço esperado de disputa: migração v4, preço esperado na análise
(lance ▸ teto×(1−deságio) ▸ teto), pisos de lance, PATCH lance e config
desagio (com re-análise dos agregados persistidos)."""
import sqlite3

import pytest

from app import db
from app.services import analise


# ---------- migração v4 ----------

def test_migracao_v4_lance_e_desagio(tmp_path):
    """v4 sobre v3 populado: preserva dados, ganha a coluna lance_previsto e a
    config desagio_esperado=0.20 (default realista — decisão do dono). Idempotente."""
    caminho = tmp_path / "radar.db"
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    # banco até v3 (com dados): roda as 3 primeiras migrações na mão
    for i, script in enumerate(db.MIGRACOES[:3], start=1):
        con.executescript(script)
        con.execute(f"PRAGMA user_version = {i}")
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,1,'NC-1')")
    pid = con.execute("SELECT id FROM pregoes").fetchone()["id"]
    con.execute("INSERT INTO itens_pregao (pregao_id, numero, descricao, "
                "custo_manual) VALUES (?,1,'Item A',55)", (pid,))
    con.commit(); con.close()

    c2 = db.abrir(caminho)                      # migra v3 → v4
    cols = {r[1] for r in c2.execute("PRAGMA table_info(itens_pregao)")}
    assert "lance_previsto" in cols
    # dados v3 preservados (custo_manual mantido)
    assert c2.execute("SELECT custo_manual FROM itens_pregao").fetchone()[
        "custo_manual"] == 55
    # nova chave de config presente com o padrão 0.20 (cenário realista)
    assert c2.execute("SELECT valor FROM config WHERE chave='desagio_esperado'"
                      ).fetchone()["valor"] == "0.20"
    assert c2.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRACOES)

    # idempotente
    db.migrar(c2)
    assert c2.execute("SELECT COUNT(*) c FROM config WHERE "
                      "chave='desagio_esperado'").fetchone()["c"] == 1
    c2.close()


# ---------- análise com preço esperado ----------

def _montar(con):
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,1,'NC-1')")
    pid = con.execute("SELECT id FROM pregoes").fetchone()["id"]
    # item com custo manual 80, teto 100, qtd 30 → margem 20%, lucro 600 no teto
    # (cobertura 100% mas lucro < 1000 → "talvez"); deságio 15% derruba margem
    # abaixo de 8% → "nao_vale" (flip de veredito).
    con.execute("""INSERT INTO itens_pregao
        (pregao_id, numero, descricao, qtd, valor_unit_estimado, custo_manual)
        VALUES (?,1,'Item A',30,100,80)""", (pid,))
    con.commit()
    return pid


def test_desagio_zero_igual_ao_teto(con):
    """Deságio 0 (default): a conta usa o teto — comportamento idêntico ao P3."""
    pid = _montar(con)
    r = analise.analisar_pregao(con, pid)
    # (100-80)*30 = 600 no teto · margem 20% · talvez
    assert r["lucro_potencial"] == pytest.approx(600.0)
    assert r["margem_media"] == pytest.approx(0.20)
    assert r["itens_com_custo"] == 1
    assert r["veredito"] == "talvez"


def test_desagio_reduz_margem_e_lucro_e_pode_virar_veredito(con):
    """Deságio 15% baixa o preço esperado → margem e lucro caem; o veredito
    muda (margem < 8% → nao_vale)."""
    pid = _montar(con)
    base = analise.analisar_pregao(con, pid)
    assert base["margem_media"] == pytest.approx(0.20)
    assert base["veredito"] == "talvez"

    con.execute("INSERT OR REPLACE INTO config (chave, valor) "
                "VALUES ('desagio_esperado','0.15')")
    con.commit()
    r = analise.analisar_pregao(con, pid)
    # preço esperado = 100*0.85 = 85 → margem (85-80)/85 ≈ 5.88% · lucro 150
    assert r["margem_media"] == pytest.approx((85 - 80) / 85)
    assert r["lucro_potencial"] == pytest.approx((85 - 80) * 30)
    # margem ~5.9% < 8% → vira nao_vale (era talvez no teto)
    assert base["veredito"] != r["veredito"]
    assert r["veredito"] == "nao_vale"


def test_lance_previsto_vence_desagio(con):
    """lance_previsto digitado tem precedência sobre o deságio global."""
    pid = _montar(con)
    con.execute("INSERT OR REPLACE INTO config (chave, valor) "
                "VALUES ('desagio_esperado','0.15')")
    con.execute("UPDATE itens_pregao SET lance_previsto=95 WHERE numero=1")
    con.commit()
    r = analise.analisar_pregao(con, pid)
    # preço = lance 95 (não 85 do deságio) → margem (95-80)/95, lucro ×30
    assert r["margem_media"] == pytest.approx((95 - 80) / 95)
    assert r["lucro_potencial"] == pytest.approx((95 - 80) * 30)


def test_sigiloso_com_lance_entra_na_conta(con):
    """Item sigiloso (teto NULL) só entra na conta se houver lance_previsto;
    com lance, margem/lucro saem normais a partir do lance."""
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,1,'NC-1')")
    pid = con.execute("SELECT id FROM pregoes").fetchone()["id"]
    con.execute("""INSERT INTO itens_pregao
        (pregao_id, numero, descricao, qtd, valor_unit_estimado, sigiloso,
         custo_manual) VALUES (?,1,'Sigiloso',4,NULL,1,60)""", (pid,))
    con.commit()
    # sem lance → fora da conta (sigiloso sem teto)
    r0 = analise.analisar_pregao(con, pid)
    assert r0["itens_com_custo"] == 0
    assert r0["lucro_potencial"] is None
    # com lance 100 → entra: (100-60)*4 = 160
    con.execute("UPDATE itens_pregao SET lance_previsto=100 WHERE numero=1")
    con.commit()
    r1 = analise.analisar_pregao(con, pid)
    assert r1["itens_com_custo"] == 1
    assert r1["lucro_potencial"] == pytest.approx(160.0)
    assert r1["margem_media"] == pytest.approx((100 - 60) / 100)


def test_sem_lance_e_sem_teto_fica_fora(con):
    """Sigiloso sem lance e sem teto: custo não força conta (princípio 3)."""
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,1,'NC-1')")
    pid = con.execute("SELECT id FROM pregoes").fetchone()["id"]
    con.execute("""INSERT INTO itens_pregao
        (pregao_id, numero, descricao, qtd, valor_unit_estimado, sigiloso,
         custo_manual) VALUES (?,1,'Sigiloso',4,NULL,1,60)""", (pid,))
    con.commit()
    r = analise.analisar_pregao(con, pid)
    assert r["itens_com_custo"] == 0
    assert r["veredito"] is None


# ---------- GET /pregoes/{id}/itens: preço esperado, fonte e pisos ----------

def _pregao_item(con, **kw):
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,1,'NC-1')")
    pid = con.execute("SELECT id FROM pregoes").fetchone()["id"]
    cols = ", ".join(kw)
    ph = ", ".join("?" for _ in kw)
    con.execute(f"INSERT INTO itens_pregao (pregao_id, numero, descricao, "
                f"{cols}) VALUES (?,1,'Item',{ph})", (pid, *kw.values()))
    con.commit()
    return pid


def test_get_itens_fonte_preco_teto(client, con):
    """Sem lance e sem deságio: preço esperado = teto, fonte 'teto'."""
    _pregao_item(con, qtd=10, valor_unit_estimado=100, custo_manual=80)
    it = client.get("/pregoes/1/itens").json()[0]
    assert it["preco_esperado"] == 100
    assert it["fonte_preco"] == "teto"
    # pisos com custo: lance mínimo = 80/(1-0.20) = 100 · empate = 80
    assert it["lance_minimo_alvo"] == pytest.approx(80 / (1 - 0.20))
    assert it["empate"] == 80


def test_get_itens_fonte_preco_desagio(client, con):
    """Com deságio 10% e sem lance: preço = teto×0.9, fonte 'desagio'."""
    _pregao_item(con, qtd=10, valor_unit_estimado=100, custo_manual=80)
    client.patch("/config", json={"desagio_esperado": "0.10"})
    it = client.get("/pregoes/1/itens").json()[0]
    assert it["preco_esperado"] == pytest.approx(90.0)
    assert it["fonte_preco"] == "desagio"
    assert it["margem"] == pytest.approx((90 - 80) / 90)


def test_get_itens_fonte_preco_lance(client, con):
    """Com lance digitado: preço = lance, fonte 'lance' (vence o deságio)."""
    pid = _pregao_item(con, qtd=10, valor_unit_estimado=100, custo_manual=80)
    client.patch("/config", json={"desagio_esperado": "0.10"})
    item_id = con.execute("SELECT id FROM itens_pregao").fetchone()["id"]
    client.patch(f"/itens/{item_id}", json={"lance_previsto": 95})
    it = client.get(f"/pregoes/{pid}/itens").json()[0]
    assert it["preco_esperado"] == 95
    assert it["fonte_preco"] == "lance"


def test_get_itens_pisos_ausentes_sem_custo(client, con):
    """Sem custo efetivo: pisos (lance_minimo_alvo/empate) ausentes; preço
    esperado segue exposto (guia)."""
    _pregao_item(con, qtd=10, valor_unit_estimado=100)
    it = client.get("/pregoes/1/itens").json()[0]
    assert it["lance_minimo_alvo"] is None
    assert it["empate"] is None
    assert it["preco_esperado"] == 100 and it["fonte_preco"] == "teto"


# ---------- PATCH /itens/{id} lance ----------

def test_patch_lance_persiste_e_null_limpa(client, con):
    pid = _pregao_item(con, qtd=10, valor_unit_estimado=100, custo_manual=80)
    item_id = con.execute("SELECT id FROM itens_pregao").fetchone()["id"]
    r = client.patch(f"/itens/{item_id}", json={"lance_previsto": 90})
    assert r.status_code == 200
    assert r.json()["item"]["lance_previsto"] == 90
    # agregados recalculados com o lance: (90-80)*10 = 100
    assert r.json()["pregao"]["lucro_potencial"] == pytest.approx(100.0)
    # null limpa → volta ao teto (preço 100): (100-80)*10 = 200
    r = client.patch(f"/itens/{item_id}", json={"lance_previsto": None})
    assert r.json()["item"]["lance_previsto"] is None
    assert r.json()["pregao"]["lucro_potencial"] == pytest.approx(200.0)


def test_patch_lance_negativo_422(client, con):
    _pregao_item(con, qtd=10, valor_unit_estimado=100)
    item_id = con.execute("SELECT id FROM itens_pregao").fetchone()["id"]
    assert client.patch(f"/itens/{item_id}",
                        json={"lance_previsto": -5}).status_code == 422


def test_patch_lance_nao_toca_custo(client, con):
    """PATCH só com lance_previsto não zera o custo_manual (exclude_unset)."""
    _pregao_item(con, qtd=10, valor_unit_estimado=100, custo_manual=80)
    item_id = con.execute("SELECT id FROM itens_pregao").fetchone()["id"]
    client.patch(f"/itens/{item_id}", json={"lance_previsto": 90})
    assert con.execute("SELECT custo_manual FROM itens_pregao WHERE id=?",
                       (item_id,)).fetchone()["custo_manual"] == 80


# ---------- PATCH /config desagio: validação + re-análise ----------

def test_config_desagio_validacao(client):
    assert client.patch("/config", json={"desagio_esperado": "0.2"}
                        ).json()["desagio_esperado"] == "0.2"
    assert client.patch("/config", json={"desagio_esperado": "0.91"}
                        ).status_code == 422
    assert client.patch("/config", json={"desagio_esperado": "-0.1"}
                        ).status_code == 422
    assert client.patch("/config", json={"desagio_esperado": "abc"}
                        ).status_code == 422


def test_config_desagio_reanalisa_agregados_persistidos(client, con):
    """Mudar o deságio dispara re-análise: os agregados PERSISTIDOS do pregão
    (cartão/funil) mudam SEM um novo GET /pregoes/{id}/itens."""
    pid = _pregao_item(con, qtd=10, valor_unit_estimado=100, custo_manual=80)
    # análise inicial no teto
    analise.analisar_pregao(con, pid)
    antes = client.get(f"/pregoes/{pid}").json()
    assert antes["lucro_potencial"] == pytest.approx(200.0)

    # PATCH deságio 15% → re-análise no backend
    client.patch("/config", json={"desagio_esperado": "0.15"})
    # SEM tocar GET itens: o detalhe do pregão já reflete o novo agregado
    depois = client.get(f"/pregoes/{pid}").json()
    assert depois["lucro_potencial"] == pytest.approx((85 - 80) * 10)
    assert depois["margem_media"] == pytest.approx((85 - 80) / 85)
