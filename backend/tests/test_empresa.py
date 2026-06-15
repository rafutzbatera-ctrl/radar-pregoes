"""Cadastro da EMPRESA do licitante (RAG Fase 3) — GET/PUT linha única."""


def test_get_vazio_retorna_campos_null(client):
    r = client.get("/empresa")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["id"] == 1
    for c in ("razao_social", "cnpj", "endereco", "representante_nome",
              "representante_cpf", "representante_cargo", "porte"):
        assert corpo[c] is None


def test_put_grava_e_get_rele(client):
    r = client.put("/empresa", json={
        "razao_social": "ACME Audio LTDA",
        "cnpj": "01.613.770/0001-72",
        "endereco": "Rua X, 100",
        "representante_nome": "João Silva",
        "representante_cpf": "123.456.789-00",
        "representante_cargo": "Sócio",
        "porte": "me_epp",
    })
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["razao_social"] == "ACME Audio LTDA"
    # CNPJ/CPF normalizados para só dígitos
    assert corpo["cnpj"] == "01613770000172"
    assert corpo["representante_cpf"] == "12345678900"
    assert corpo["porte"] == "me_epp"
    assert corpo["atualizado_em"] is not None

    # relê
    lido = client.get("/empresa").json()
    assert lido["razao_social"] == "ACME Audio LTDA"
    assert lido["cnpj"] == "01613770000172"
    assert lido["porte"] == "me_epp"


def test_put_parcial_atualiza_so_o_enviado(client):
    client.put("/empresa", json={
        "razao_social": "ACME Audio LTDA", "porte": "normal"})
    # PUT parcial: só endereco — razao_social e porte permanecem
    r = client.put("/empresa", json={"endereco": "Av. Nova, 200"})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["endereco"] == "Av. Nova, 200"
    assert corpo["razao_social"] == "ACME Audio LTDA"
    assert corpo["porte"] == "normal"


def test_put_porte_invalido_422(client):
    r = client.put("/empresa", json={"porte": "gigante"})
    assert r.status_code == 422


def test_put_porte_normal_e_null_ok(client):
    assert client.put("/empresa", json={"porte": "normal"}).json()["porte"] == "normal"
    # limpar porte com null
    assert client.put("/empresa", json={"porte": None}).json()["porte"] is None


def test_put_vazio_seta_atualizado_em(client):
    r = client.put("/empresa", json={})
    assert r.status_code == 200
    assert r.json()["atualizado_em"] is not None
