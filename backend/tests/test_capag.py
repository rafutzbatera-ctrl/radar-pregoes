"""CAPAG — risco de pagamento do comprador (Tesouro/SICONFI).

Fixture pequena montada direto no `con` (NÃO baixa o XLSX de ~22MB). Asserções:
- município SP → disponível True, nota B, indicador[0] = 32.75% nota A;
- federal (CNPJ fora de capag_entes, há entes carregados) → False motivo federal;
- CNPJ desconhecido sem entes → sem_dados;
- endpoint GET /pregoes/{id}/capag (client + con).
"""
from app.services import capag

# CNPJ fake do Município de São Paulo (só dígitos; o serviço normaliza)
CNPJ_SP = "46395000000139"
COD_SP = "3550308"


def _montar_capag(con):
    """capag_entes + capag_notas mínimos: São Paulo (município) com nota B."""
    con.execute(
        "INSERT OR REPLACE INTO capag_entes(cnpj, cod_ibge, ente, uf, esfera)"
        " VALUES (?,?,?,?,?)",
        (CNPJ_SP, COD_SP, "Prefeitura de São Paulo", "SP", "M"),
    )
    con.execute(
        "INSERT OR REPLACE INTO capag_notas"
        "(cod_ibge, municipio, uf, nota, ind1, nota1, ind2, nota2,"
        " ind3, nota3, icf, origem, esfera)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (COD_SP, "São Paulo", "SP", "B",
         0.32746, "A", 0.9378, "B", 0.04857, "B",
         "Bicf", "CAPAG Ano Base 2024", "M"),
    )
    con.commit()


def test_cor_da_nota():
    assert capag.cor_da_nota("A") == "ok"
    assert capag.cor_da_nota("B") == "atencao"
    assert capag.cor_da_nota("C") == "ruim"
    assert capag.cor_da_nota("D") == "ruim"
    assert capag.cor_da_nota(None) is None


def test_so_digitos():
    assert capag.so_digitos("46.395.000/0001-39") == CNPJ_SP
    assert capag.so_digitos(None) == ""


def test_municipal_sp_disponivel(con):
    _montar_capag(con)
    r = capag.capag_do_pregao(con, CNPJ_SP, "SP", "São Paulo")
    assert r["disponivel"] is True
    assert r["nota"] == "B"
    assert r["cor"] == "atencao"
    assert r["icf"] == "Bicf"
    assert r["origem"] == "CAPAG Ano Base 2024"
    assert r["esfera"] == "M"
    assert r["fonte"] == "Tesouro Nacional / SICONFI"
    inds = r["indicadores"]
    assert len(inds) == 3
    assert inds[0]["rotulo"] == "Endividamento"
    assert inds[0]["nota"] == "A"
    assert inds[0]["valor_pct"] == 32.75
    assert inds[1]["nota"] == "B" and inds[1]["valor_pct"] == 93.78
    assert inds[2]["nota"] == "B" and inds[2]["valor_pct"] == 4.86


def test_fallback_por_municipio_uf(con):
    """CNPJ não casa em capag_entes, mas há entes carregados e o município/UF
    bate em capag_notas → resolve pelo nome normalizado (com acento diferente)."""
    _montar_capag(con)
    # CNPJ diferente do cadastrado, mas município/UF do mesmo ente
    r = capag.capag_do_pregao(con, "99999999000199", "SP", "SAO PAULO")
    # esse CNPJ não está em capag_entes → cairia em "federal"; mas o fallback
    # por município+UF deve resolver ANTES (município existe no XLSX).
    assert r["disponivel"] is True
    assert r["nota"] == "B"


def test_federal_sem_capag(con):
    """Ente federal: CNPJ fora de capag_entes, há entes carregados, sem
    município que case → motivo 'federal' (nunca inventa nota)."""
    _montar_capag(con)
    r = capag.capag_do_pregao(con, "00394445000170", "DF", "Brasília")
    assert r["disponivel"] is False
    assert r["motivo"] == "federal"
    assert r.get("nota") is None


def test_cnpj_desconhecido_sem_entes(con):
    """Sem nenhum ente carregado (base não populada): qualquer CNPJ →
    sem_dados (não dá pra inferir federal)."""
    r = capag.capag_do_pregao(con, "12345678000199", "MG", "Cidade Nova")
    assert r["disponivel"] is False
    assert r["motivo"] == "sem_dados"


def test_endpoint_capag(client, con):
    """GET /pregoes/{id}/capag com um pregão municipal de SP."""
    _montar_capag(con)
    con.execute(
        "INSERT INTO pregoes(cnpj, ano, seq, numero_controle, uf, municipio)"
        " VALUES (?,?,?,?,?,?)",
        (CNPJ_SP, 2026, 1, "NC-CAPAG-1", "SP", "São Paulo"),
    )
    con.commit()
    pid = con.execute("SELECT id FROM pregoes").fetchone()["id"]

    r = client.get(f"/pregoes/{pid}/capag")
    assert r.status_code == 200
    body = r.json()
    assert body["disponivel"] is True
    assert body["nota"] == "B"
    assert body["indicadores"][0]["valor_pct"] == 32.75


def test_endpoint_capag_pregao_inexistente(client):
    r = client.get("/pregoes/999999/capag")
    assert r.status_code == 404
