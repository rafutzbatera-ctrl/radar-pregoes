"""M0 — banco e migrações."""
from app import db


def test_migracao_cria_tabelas(con):
    tabelas = {ln["name"] for ln in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert {"buscas_salvas", "pregoes", "itens_pregao", "catalogo_produtos",
            "arquivos", "habilitacao", "config"} <= tabelas


def test_migracao_idempotente(tmp_path):
    caminho = tmp_path / "radar.db"
    c1 = db.abrir(caminho)
    c1.close()
    c2 = db.abrir(caminho)  # segunda abertura não re-executa migração
    versao = c2.execute("PRAGMA user_version").fetchone()[0]
    assert versao == len(db.MIGRACOES)
    c2.close()


def test_config_padrao(con):
    cfg = {ln["chave"]: ln["valor"] for ln in con.execute("SELECT * FROM config")}
    assert cfg["regime_tributario"] == "simples"
    assert cfg["uf_origem"] == "SP"
