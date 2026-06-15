"""v14 — descartar pregão do radar (soft-delete reversível).

DELETE /pregoes/{id} marca descartado=1 (tombstone, não apaga a linha); some
das listagens por padrão; é reversível por PATCH descartado=false; e a
DESCOBERTA não ressuscita um descartado já existente.
"""
from app.services import descoberta


def _criar_pregao(con, numero_controle="01613770000172-1-000067/2026") -> int:
    cur = con.execute(
        "INSERT INTO pregoes (cnpj, ano, seq, numero_controle, uf) "
        "VALUES ('01613770000172', 2026, 67, ?, 'PR')",
        (numero_controle,),
    )
    con.commit()
    return cur.lastrowid


def test_delete_marca_descartado_e_some_da_listagem(client, con):
    pid = _criar_pregao(con)
    # presente antes do descarte
    assert any(p["id"] == pid for p in client.get("/pregoes").json())

    r = client.delete(f"/pregoes/{pid}")
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    # linha NÃO apagada (tombstone), mas descartado=1
    row = con.execute("SELECT descartado, salvo, status_pipeline FROM pregoes "
                      "WHERE id=?", (pid,)).fetchone()
    assert row is not None
    assert row["descartado"] == 1
    assert row["salvo"] == 0
    assert row["status_pipeline"] is None

    # some da listagem padrão
    assert all(p["id"] != pid for p in client.get("/pregoes").json())


def test_listar_descartados_traz_so_os_descartados(client, con):
    ativo = _criar_pregao(con, "AAA-1-000001/2026")
    alvo = _criar_pregao(con, "BBB-1-000002/2026")
    client.delete(f"/pregoes/{alvo}")

    descartados = client.get("/pregoes?descartados=true").json()
    ids = [p["id"] for p in descartados]
    assert ids == [alvo]
    assert ativo not in ids

    # listagem padrão segue mostrando só o ativo
    padrao = [p["id"] for p in client.get("/pregoes").json()]
    assert padrao == [ativo]


def test_patch_descartado_false_restaura(client, con):
    pid = _criar_pregao(con)
    client.delete(f"/pregoes/{pid}")
    assert all(p["id"] != pid for p in client.get("/pregoes").json())

    r = client.patch(f"/pregoes/{pid}", json={"descartado": False})
    assert r.status_code == 200

    row = con.execute("SELECT descartado, novo FROM pregoes WHERE id=?",
                      (pid,)).fetchone()
    assert row["descartado"] == 0
    assert row["novo"] == 0  # restaura sem flag "novo"

    # volta a aparecer na listagem padrão
    assert any(p["id"] == pid for p in client.get("/pregoes").json())


def test_delete_id_inexistente_404(client):
    assert client.delete("/pregoes/999999").status_code == 404


def test_descoberta_nao_ressuscita_descartado(con, cliente_fake):
    """Re-rodar a descoberta com um pregão descartado NÃO o ressuscita."""
    busca_id = con.execute(
        "INSERT INTO buscas_salvas (nome, termos, ufs) VALUES ('AV','áudio','SP')"
    ).lastrowid
    con.commit()

    # 1ª rodada: insere os hits da fixture
    descoberta.rodar_busca(con, busca_id, cliente_fake, enriquecer=False)
    alvo = con.execute("SELECT id, numero_controle FROM pregoes "
                       "ORDER BY id LIMIT 1").fetchone()
    pid = alvo["id"]

    # descarta um deles (tombstone)
    con.execute("UPDATE pregoes SET descartado=1, novo=1 WHERE id=?", (pid,))
    con.commit()

    # 2ª rodada da MESMA busca: o hit do descartado volta a aparecer na fixture
    r2 = descoberta.rodar_busca(con, busca_id, cliente_fake, enriquecer=False)
    assert r2["novos"] == 0  # nada novo: dedup por numero_controle

    row = con.execute("SELECT descartado FROM pregoes WHERE id=?",
                      (pid,)).fetchone()
    assert row["descartado"] == 1  # tombstone intacto, não ressuscitou
