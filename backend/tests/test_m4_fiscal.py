"""M4 — fiscal: NCM (PNCP→catálogo→vazio), CFOP por UF, CST/CSOSN por regime.
Teste exigido: trocar o regime alterna CSOSN↔CST."""
from app.services import fiscal


def _montar(con, uf_pregao="SP"):
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, uf) "
                "VALUES ('1',2026,1,'NC-1',?)", (uf_pregao,))
    pregao_id = con.execute("SELECT id FROM pregoes").fetchone()["id"]
    con.execute("""INSERT INTO catalogo_produtos
        (id, nome, custo_unit, ncm, unidade, csosn, cst)
        VALUES (1,'Microfone',800,'8518.10.00','UN','102','060')""")
    # item com NCM do PNCP e match confirmado
    con.execute("""INSERT INTO itens_pregao
        (pregao_id, numero, descricao, unidade, ncm_pncp, produto_id, match_confirmado)
        VALUES (?,1,'Mic','Unidade','8518.99.99',1,1)""", (pregao_id,))
    # item sem NCM do PNCP (vem do catálogo) e match confirmado
    con.execute("""INSERT INTO itens_pregao
        (pregao_id, numero, descricao, unidade, produto_id, match_confirmado)
        VALUES (?,2,'Mic 2','Unidade',1,1)""", (pregao_id,))
    # item sem match → faltam dados
    con.execute("""INSERT INTO itens_pregao (pregao_id, numero, descricao)
        VALUES (?,3,'Canaleta')""", (pregao_id,))
    con.commit()
    return pregao_id


def test_ncm_precedencia_pncp_catalogo_vazio(con):
    pregao_id = _montar(con)
    r = fiscal.fiscal_do_pregao(con, pregao_id)
    por_numero = {f["numero"]: f for f in r["itens"]}
    assert por_numero[1]["ncm"] == "8518.99.99" and por_numero[1]["ncm_fonte"] == "pncp"
    assert por_numero[2]["ncm"] == "8518.10.00" and por_numero[2]["ncm_fonte"] == "catalogo"
    assert por_numero[3]["ncm"] is None and "ncm" in por_numero[3]["faltas"]


def test_cfop_mesma_uf_5102_diferente_6102(con):
    pregao_id = _montar(con, uf_pregao="SP")  # config padrão uf_origem=SP
    r = fiscal.fiscal_do_pregao(con, pregao_id)
    assert r["itens"][0]["cfop"] == "5102"

    con.execute("UPDATE pregoes SET uf='GO'")
    con.commit()
    r = fiscal.fiscal_do_pregao(con, pregao_id)
    assert r["itens"][0]["cfop"] == "6102"


def test_trocar_regime_alterna_csosn_cst(con):
    """Teste exigido no CLAUDE.md M4."""
    pregao_id = _montar(con)

    # regime padrão: simples → CSOSN do produto
    r = fiscal.fiscal_do_pregao(con, pregao_id)
    assert r["regime"] == "simples"
    assert r["itens"][0]["cst_csosn"] == "102"

    con.execute("UPDATE config SET valor='presumido' WHERE chave='regime_tributario'")
    con.commit()
    r = fiscal.fiscal_do_pregao(con, pregao_id)
    assert r["regime"] == "presumido"
    assert r["itens"][0]["cst_csosn"] == "060"

    # e volta
    con.execute("UPDATE config SET valor='simples' WHERE chave='regime_tributario'")
    con.commit()
    r = fiscal.fiscal_do_pregao(con, pregao_id)
    assert r["itens"][0]["cst_csosn"] == "102"


def test_prontidao_e_selo_agregado(con):
    pregao_id = _montar(con)
    r = fiscal.fiscal_do_pregao(con, pregao_id)
    por_numero = {f["numero"]: f for f in r["itens"]}
    assert por_numero[1]["pronto"] is True
    assert por_numero[2]["pronto"] is True
    assert por_numero[3]["pronto"] is False
    assert r["prontos"] == 2 and r["cobertos"] == 2 and r["total"] == 3
    assert "contador" in r["aviso"]  # aviso fixo (CLAUDE.md §9)
