"""P2 — pipeline de disputa: migração, PATCH, resumo."""
import sqlite3

from app import db


def test_migracao_v2_preserva_dados_v1(tmp_path):
    caminho = tmp_path / "radar.db"
    con = sqlite3.connect(caminho)
    con.executescript(db.MIGRACOES[0])          # banco v1 com dados
    con.execute("PRAGMA user_version = 1")
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,1,'NC-1')")
    con.commit(); con.close()

    c2 = db.abrir(caminho)                      # migra para v2
    cols = {r[1] for r in c2.execute("PRAGMA table_info(pregoes)")}
    assert {"status_pipeline", "data_disputa", "valor_final"} <= cols
    assert c2.execute("SELECT COUNT(*) c FROM pregoes").fetchone()["c"] == 1
    assert c2.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRACOES)
    c2.close()


def _novo_pregao(con, nc="NC-1"):
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,1,?)", (nc,))
    con.commit()
    return con.execute("SELECT id FROM pregoes WHERE numero_controle=?",
                       (nc,)).fetchone()["id"]


def test_patch_campos_pipeline(client, con):
    pid = _novo_pregao(con)
    r = client.patch(f"/pregoes/{pid}", json={
        "status_pipeline": "disputando",
        "data_disputa": "2026-06-20 09:00",
        "valor_final": 12500.5,
    })
    assert r.status_code == 200
    assert r.json()["status_pipeline"] == "disputando"
    assert r.json()["data_disputa"] == "2026-06-20 09:00"
    assert r.json()["valor_final"] == 12500.5


def test_patch_status_invalido_422(client, con):
    pid = _novo_pregao(con)
    assert client.patch(f"/pregoes/{pid}",
                        json={"status_pipeline": "ganhei"}).status_code == 422


def test_salvar_seta_cotacao_e_preserva_status_existente(client, con):
    pid = _novo_pregao(con)
    r = client.patch(f"/pregoes/{pid}", json={"salvo": True})
    assert r.json()["status_pipeline"] == "cotacao"   # gatilho de entrada

    client.patch(f"/pregoes/{pid}", json={"status_pipeline": "ganho"})
    client.patch(f"/pregoes/{pid}", json={"salvo": False})   # dessalvar preserva
    r = client.patch(f"/pregoes/{pid}", json={"salvo": True})  # re-salvar idem
    assert r.json()["status_pipeline"] == "ganho"
