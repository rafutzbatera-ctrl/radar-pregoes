"""M1 — descoberta: rodar busca, dedup, flag novo."""
from app.services import descoberta


def _criar_busca(con) -> int:
    cur = con.execute(
        "INSERT INTO buscas_salvas (nome, termos, ufs) VALUES (?,?,?)",
        ("AV SP", "áudio", "SP"),
    )
    con.commit()
    return cur.lastrowid


def test_rodar_busca_persiste_pregoes(con, cliente_fake):
    busca_id = _criar_busca(con)
    r = descoberta.rodar_busca(con, busca_id, cliente_fake)
    assert r["hits"] == 10          # fixture real tem 10 hits
    assert r["novos"] == r["hits"]  # primeira rodada: tudo novo

    pregoes = con.execute("SELECT * FROM pregoes").fetchall()
    assert len(pregoes) == r["novos"]
    p = pregoes[0]
    assert p["numero_controle"]
    assert p["link_pncp"].startswith("https://pncp.gov.br/app/editais/")
    assert p["novo"] == 1
    assert p["json_busca"]  # hit cru persistido (fonte oficial)


def test_mesma_busca_duas_vezes_nao_duplica(con, cliente_fake):
    """Teste exigido no CLAUDE.md M1."""
    busca_id = _criar_busca(con)
    r1 = descoberta.rodar_busca(con, busca_id, cliente_fake)
    total_apos_1 = con.execute("SELECT COUNT(*) c FROM pregoes").fetchone()["c"]

    r2 = descoberta.rodar_busca(con, busca_id, cliente_fake)
    total_apos_2 = con.execute("SELECT COUNT(*) c FROM pregoes").fetchone()["c"]

    assert r1["novos"] > 0
    assert r2["novos"] == 0
    assert total_apos_1 == total_apos_2


def test_ultima_exec_atualizada(con, cliente_fake):
    busca_id = _criar_busca(con)
    assert con.execute(
        "SELECT ultima_exec FROM buscas_salvas WHERE id=?", (busca_id,)
    ).fetchone()["ultima_exec"] is None
    descoberta.rodar_busca(con, busca_id, cliente_fake)
    assert con.execute(
        "SELECT ultima_exec FROM buscas_salvas WHERE id=?", (busca_id,)
    ).fetchone()["ultima_exec"] is not None


def test_rodar_todas_ativas_pula_inativas(con, cliente_fake):
    ativa = _criar_busca(con)
    con.execute(
        "INSERT INTO buscas_salvas (nome, termos, ativo) VALUES ('pausada','x',0)"
    )
    con.commit()
    resultados = descoberta.rodar_todas_ativas(con, cliente_fake)
    assert [r["busca_id"] for r in resultados] == [ativa]
