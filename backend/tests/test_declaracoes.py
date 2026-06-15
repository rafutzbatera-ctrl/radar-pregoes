"""Minutas de declarações de habilitação (RAG Fase 3).

Cobre: render com lacunas visíveis quando falta dado da empresa (princípio 1 —
nunca chuta), filtro por porte (ME/EPP), cruzamento conservador
`exigido_no_edital`, aviso fixo e os endpoints.
"""
from app.services import declaracoes

CAMPOS_EMPRESA = (
    "razao_social", "cnpj", "endereco",
    "representante_nome", "representante_cpf", "representante_cargo", "porte",
)


def _set_empresa(con, **campos):
    vals = {c: None for c in CAMPOS_EMPRESA}
    vals.update(campos)
    con.execute(
        "INSERT OR REPLACE INTO empresa"
        " (id, razao_social, cnpj, endereco, representante_nome,"
        "  representante_cpf, representante_cargo, porte)"
        " VALUES (1,?,?,?,?,?,?,?)",
        tuple(vals[c] for c in CAMPOS_EMPRESA),
    )
    con.commit()


def _criar_pregao(con, **extra):
    cols = {
        "cnpj": "01613770000172", "ano": 2026, "seq": 67,
        "numero_controle": "NC-DECL", "titulo": "Pregão", "descricao": "x",
        "orgao": "Órgão", "municipio": "Imbaú", "uf": "PR",
        "modalidade": "Pregão - Eletrônico", "situacao": "Recebendo proposta",
        "data_fim_vigencia": "2026-07-01", "valor_global": 1000.0,
        "link_pncp": "https://pncp.gov.br/app/editais/x",
    }
    cols.update(extra)
    campos = ", ".join(cols)
    marks = ", ".join("?" for _ in cols)
    con.execute(f"INSERT INTO pregoes({campos}) VALUES ({marks})", tuple(cols.values()))
    con.commit()
    return con.execute("SELECT id FROM pregoes WHERE numero_controle=?",
                       (cols["numero_controle"],)).fetchone()["id"]


def _add_requisito(con, pregao_id, requisito, categoria="juridica"):
    con.execute(
        "INSERT INTO habilitacao (pregao_id, requisito, categoria, pagina,"
        " excerto, verificada) VALUES (?,?,?,?,?,?)",
        (pregao_id, requisito, categoria, 1, requisito, 1),
    )
    con.commit()


EMPRESA_COMPLETA = dict(
    razao_social="Áudio AV Ltda", cnpj="12.345.678/0001-99",
    endereco="Rua X, 100, São Paulo/SP", representante_nome="Fulano de Tal",
    representante_cpf="123.456.789-00", representante_cargo="Sócio-administrador",
    porte="normal",
)


# ---------- render ----------

def test_render_empresa_completa_sem_lacunas():
    tpl = next(t for t in declaracoes.carregar_templates() if t["id"] == "menor")
    r = declaracoes.render(tpl, EMPRESA_COMPLETA)
    assert r["completo"] is True
    assert r["faltando"] == []
    assert "— preencher]" not in r["texto"]
    assert "Áudio AV Ltda" in r["texto"]
    assert "12.345.678/0001-99" in r["texto"]


def test_render_empresa_vazia_mostra_lacunas_nao_inventa():
    tpl = next(t for t in declaracoes.carregar_templates() if t["id"] == "menor")
    r = declaracoes.render(tpl, {})
    assert r["completo"] is False
    assert "razao_social" in r["faltando"]
    assert "[RAZÃO SOCIAL — preencher]" in r["texto"]
    assert "[CNPJ — preencher]" in r["texto"]


# ---------- sugestão por pregão ----------

def test_me_epp_so_aparece_para_porte_me_epp(con):
    pid = _criar_pregao(con)
    _set_empresa(con, **{**EMPRESA_COMPLETA, "porte": "normal"})
    ids = {d["id"] for d in declaracoes.declaracoes_do_pregao(con, pid)}
    assert "me_epp" not in ids
    # as "sempre" estão presentes
    assert {"menor", "idoneidade", "cumprimento_habilitacao"} <= ids

    _set_empresa(con, **{**EMPRESA_COMPLETA, "porte": "me_epp"})
    ids2 = {d["id"] for d in declaracoes.declaracoes_do_pregao(con, pid)}
    assert "me_epp" in ids2


def test_exigido_no_edital_conservador(con):
    pid = _criar_pregao(con, numero_controle="NC-DECL-EX")
    _set_empresa(con, **EMPRESA_COMPLETA)
    _add_requisito(con, pid, "Declaração de que não emprega menor de 18 anos (art. 7º, XXXIII)")
    decls = {d["id"]: d for d in declaracoes.declaracoes_do_pregao(con, pid)}
    assert decls["menor"]["exigido_no_edital"] is True
    # sem requisito correspondente → não inventa exigência
    assert decls["proposta_independente"]["exigido_no_edital"] is False


def test_todas_minutas_tem_aviso_fixo(con):
    pid = _criar_pregao(con, numero_controle="NC-DECL-AV")
    _set_empresa(con, **EMPRESA_COMPLETA)
    for d in declaracoes.declaracoes_do_pregao(con, pid):
        assert "jurídico" in d["aviso"].lower()


# ---------- endpoints ----------

def test_endpoint_catalogo(client):
    r = client.get("/declaracoes")
    assert r.status_code == 200
    body = r.json()
    ids = {t["id"] for t in body["templates"]}
    assert {"menor", "me_epp", "idoneidade"} <= ids
    assert "aviso" in body


def test_endpoint_pregao_200_e_404(client, con):
    pid = _criar_pregao(con, numero_controle="NC-DECL-EP")
    _set_empresa(con, **EMPRESA_COMPLETA)
    r = client.get(f"/pregoes/{pid}/declaracoes")
    assert r.status_code == 200
    assert len(r.json()["declaracoes"]) >= 5
    assert client.get("/pregoes/999999/declaracoes").status_code == 404
