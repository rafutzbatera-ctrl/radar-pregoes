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
