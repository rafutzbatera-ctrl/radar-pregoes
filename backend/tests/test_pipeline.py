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


def test_migracao_v2_backfill_salvos_legados(tmp_path):
    """Pregão salvo ANTES da v2 (status NULL) entra no funil como cotacao —
    senão ficaria visível em Meus pregões mas invisível no resumo (achado
    do review). Não-salvos continuam fora do funil (status NULL)."""
    caminho = tmp_path / "radar.db"
    con = sqlite3.connect(caminho)
    con.executescript(db.MIGRACOES[0])
    con.execute("PRAGMA user_version = 1")
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, salvo) "
                "VALUES ('1',2026,1,'NC-SALVO',1)")
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, salvo) "
                "VALUES ('1',2026,2,'NC-NAO',0)")
    con.commit(); con.close()

    c2 = db.abrir(caminho)
    salvo = c2.execute("SELECT status_pipeline s FROM pregoes "
                       "WHERE numero_controle='NC-SALVO'").fetchone()["s"]
    nao_salvo = c2.execute("SELECT status_pipeline s FROM pregoes "
                           "WHERE numero_controle='NC-NAO'").fetchone()["s"]
    assert salvo == "cotacao"
    assert nao_salvo is None
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


def test_resumo_vazio(client):
    r = client.get("/pipeline/resumo")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["total_funil"] == 0
    assert corpo["taxa_ganho"] is None
    assert corpo["valor_ganho"] is None


def test_resumo_com_funil(client, con):
    dados = [  # (nc, status, valor_final)
        ("NC-1", "cotacao", None), ("NC-2", "disputando", None),
        ("NC-3", "ganho", 10000.0), ("NC-4", "ganho", None),
        ("NC-5", "perdido", None),
    ]
    for i, (nc, st, vf) in enumerate(dados, 1):
        con.execute(
            "INSERT INTO pregoes (cnpj, ano, seq, numero_controle, salvo, "
            "status_pipeline, valor_final) VALUES ('1',2026,?,?,1,?,?)",
            (i, nc, st, vf))
    # salvo=0 fica FORA do funil mesmo com status
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, salvo, "
                "status_pipeline) VALUES ('1',2026,99,'NC-99',0,'ganho')")
    con.commit()

    corpo = client.get("/pipeline/resumo").json()
    assert corpo["total_funil"] == 5
    assert corpo["por_status"]["ganho"] == 2
    assert corpo["ganhos"] == 2 and corpo["perdidos"] == 1
    assert corpo["taxa_ganho"] == 2 / 3
    assert corpo["valor_ganho"] == 10000.0   # só valores PREENCHIDOS
    assert corpo["ganhos_sem_valor"] == 1    # honestidade: 1 ganho sem valor
