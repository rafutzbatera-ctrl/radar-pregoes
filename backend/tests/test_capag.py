"""CAPAG — risco de pagamento do comprador (Tesouro/SICONFI), ESFERA-AWARE.

Fixture pequena montada direto no `con` (NÃO baixa o XLSX de ~22MB). Asserções:
- município SP por CNPJ-ente → disponível True, nota B, indicador[0] = 32.75% nota A;
- esfera "F" (federal) → False motivo "federal", MESMO que o município informado
  exista na base (prova que NÃO misatribui a nota do município — bug do Zionn);
- esfera "M" com CNPJ de sub-órgão (não-ente) + município/UF na base → disponível
  via fallback (herda a nota do município, que a esfera confirma ser municipal);
- esfera None com CNPJ desconhecido → "nao_avaliado" (sem fallback);
- endpoint GET /pregoes/{id}/capag passa a esfera persistida (client + con).
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
    """CNPJ casa em capag_entes → nota por cod_ibge. Vale mesmo sem esfera
    informada (o CNPJ ser um ente já prova M/E)."""
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


def test_fallback_por_municipio_uf_esfera_municipal(con):
    """esfera "M" com CNPJ de SUB-ÓRGÃO (não-ente: fundo/secretaria) mas
    município/UF que existe na base → disponível via fallback (herda a nota do
    município). A esfera M confirma que é seguro casar pelo nome (com acento
    diferente)."""
    _montar_capag(con)
    # CNPJ diferente do cadastrado (sub-órgão municipal), mas município/UF do
    # mesmo ente — e a esfera do PNCP confirma "M".
    r = capag.capag_do_pregao(con, "99999999000199", "SP", "SAO PAULO",
                              esfera="M")
    assert r["disponivel"] is True
    assert r["nota"] == "B"


def test_fallback_nao_roda_sem_esfera(con):
    """MESMO CNPJ/município/UF do teste acima, mas SEM esfera (None) → NÃO faz
    fallback (evita misatribuir). Cai em 'nao_avaliado'."""
    _montar_capag(con)
    r = capag.capag_do_pregao(con, "99999999000199", "SP", "SAO PAULO")
    assert r["disponivel"] is False
    assert r["motivo"] == "nao_avaliado"
    assert r.get("nota") is None


def test_federal_nao_herda_nota_do_municipio(con):
    """BUG DO ZIONN: órgão FEDERAL sediado em São Paulo (município que EXISTE na
    base) NÃO pode herdar a CAPAG do município. esfera "F" → motivo 'federal',
    nota None, mesmo informando município="São Paulo"."""
    _montar_capag(con)
    # IFSP-like: CNPJ federal, localizado em São Paulo/SP (na base!), esfera F.
    r = capag.capag_do_pregao(con, "10882594000165", "SP", "São Paulo",
                              esfera="F")
    assert r["disponivel"] is False
    assert r["motivo"] == "federal"
    assert r.get("nota") is None


def test_federal_normaliza_esfera(con):
    """Esfera vem do PNCP variando caixa/forma — normaliza para 'F'."""
    _montar_capag(con)
    r = capag.capag_do_pregao(con, "10882594000165", "SP", "São Paulo",
                              esfera="federal")
    assert r["disponivel"] is False
    assert r["motivo"] == "federal"


def test_cnpj_desconhecido_sem_esfera_nao_avaliado(con):
    """CNPJ desconhecido, esfera None → 'nao_avaliado'. NÃO inferimos federal
    por ausência de CNPJ em capag_entes (rotulava errado sub-órgãos municipais)."""
    _montar_capag(con)
    r = capag.capag_do_pregao(con, "12345678000199", "MG", "Cidade Nova")
    assert r["disponivel"] is False
    assert r["motivo"] == "nao_avaliado"
    assert r.get("nota") is None


def _montar_capag_estadual_pr(con):
    """Nota ESTADUAL do Paraná (esfera='E'): o seed grava o NOME DO ESTADO em
    capag_notas.municipio e cod_ibge de 2 díg ('41'). Sem ente por CNPJ casado e
    sem nota municipal p/ a cidade-sede — só casa por UF."""
    con.execute(
        "INSERT OR REPLACE INTO capag_notas"
        "(cod_ibge, municipio, uf, nota, ind1, nota1, ind2, nota2,"
        " ind3, nota3, icf, origem, esfera)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("41", "Paraná", "PR", "B",
         0.30, "A", 0.90, "B", 0.05, "B",
         "Bicf", "CAPAG Ano Base 2024", "E"),
    )
    con.commit()


def test_estadual_por_uf(con):
    """Pregão ESTADUAL no PR (esfera 'E'), sem nota municipal p/ a cidade-sede →
    casa a nota ESTADUAL por UF (determinística, 1 por UF). NÃO usa nome de
    cidade (capag_notas.municipio guarda o nome do estado)."""
    _montar_capag_estadual_pr(con)
    r = capag.capag_do_pregao(con, "12345678000199", "PR", "Curitiba",
                              esfera="E")
    assert r["disponivel"] is True
    assert r["nota"] == "B"
    assert r["esfera"] == "E"
    assert r["uf"] == "PR"


def test_federal_em_estado_nao_herda(con):
    """Órgão FEDERAL (esfera 'F') num estado que TEM nota estadual → NÃO herda a
    nota do estado. motivo 'federal', sem nota (esfera-aware)."""
    _montar_capag_estadual_pr(con)
    r = capag.capag_do_pregao(con, "10882594000165", "PR", "Curitiba",
                              esfera="F")
    assert r["disponivel"] is False
    assert r["motivo"] == "federal"
    assert r.get("nota") is None


def test_nao_avaliado_sem_entes(con):
    """Sem nenhum ente carregado (base não populada) e sem esfera → nao_avaliado."""
    r = capag.capag_do_pregao(con, "12345678000199", "MG", "Cidade Nova")
    assert r["disponivel"] is False
    assert r["motivo"] == "nao_avaliado"


def test_endpoint_capag(client, con):
    """GET /pregoes/{id}/capag com um pregão municipal de SP (casa por CNPJ)."""
    _montar_capag(con)
    con.execute(
        "INSERT INTO pregoes(cnpj, ano, seq, numero_controle, uf, municipio, esfera)"
        " VALUES (?,?,?,?,?,?,?)",
        (CNPJ_SP, 2026, 1, "NC-CAPAG-1", "SP", "São Paulo", "M"),
    )
    con.commit()
    pid = con.execute("SELECT id FROM pregoes").fetchone()["id"]

    r = client.get(f"/pregoes/{pid}/capag")
    assert r.status_code == 200
    body = r.json()
    assert body["disponivel"] is True
    assert body["nota"] == "B"
    assert body["indicadores"][0]["valor_pct"] == 32.75


def test_endpoint_capag_federal_em_sp(client, con):
    """O endpoint lê a coluna `esfera` do pregão e a repassa: pregão FEDERAL
    sediado em São Paulo (município na base) → 'federal', NÃO herda a nota."""
    _montar_capag(con)
    con.execute(
        "INSERT INTO pregoes(cnpj, ano, seq, numero_controle, uf, municipio, esfera)"
        " VALUES (?,?,?,?,?,?,?)",
        ("10882594000165", 2026, 67, "NC-CAPAG-FED", "SP", "São Paulo", "F"),
    )
    con.commit()
    pid = con.execute(
        "SELECT id FROM pregoes WHERE numero_controle='NC-CAPAG-FED'"
    ).fetchone()["id"]

    r = client.get(f"/pregoes/{pid}/capag")
    assert r.status_code == 200
    body = r.json()
    assert body["disponivel"] is False
    assert body["motivo"] == "federal"
    assert body.get("nota") is None


def test_endpoint_capag_pregao_inexistente(client):
    r = client.get("/pregoes/999999/capag")
    assert r.status_code == 404
