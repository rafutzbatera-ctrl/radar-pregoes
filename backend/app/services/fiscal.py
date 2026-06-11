"""Sugestões fiscais (CLAUDE.md §6.4). Tudo aqui é SUGESTÃO — a UI exibe
sempre com a etiqueta "sugestão — confirme com contador".
"""
import sqlite3


def config_fiscal(con: sqlite3.Connection) -> dict:
    linhas = con.execute(
        "SELECT chave, valor FROM config WHERE chave IN ('regime_tributario','uf_origem')"
    ).fetchall()
    return {ln["chave"]: ln["valor"] for ln in linhas}


def fiscal_do_item(item: sqlite3.Row, produto: sqlite3.Row | None,
                   uf_pregao: str | None, cfg: dict) -> dict:
    """NCM (PNCP→catálogo→vazio), CFOP por regra local, CST/CSOSN por regime."""
    # NCM: dado oficial do PNCP tem precedência; senão o do catálogo
    if item["ncm_pncp"]:
        ncm, ncm_fonte = item["ncm_pncp"], "pncp"
    elif produto is not None and produto["ncm"]:
        ncm, ncm_fonte = produto["ncm"], "catalogo"
    else:
        ncm, ncm_fonte = None, None

    # CFOP: mesma UF → 5102; diferente → 6102 (regra local, sem API)
    cfop = None
    if uf_pregao and cfg.get("uf_origem"):
        cfop = "5102" if uf_pregao.upper() == cfg["uf_origem"].upper() else "6102"

    # CST/CSOSN conforme o regime tributário
    regime = cfg.get("regime_tributario", "simples")
    if produto is not None:
        cst_csosn = produto["csosn"] if regime == "simples" else produto["cst"]
    else:
        cst_csosn = None

    unidade = item["unidade"] or (produto["unidade"] if produto is not None else None)
    pronto = bool(ncm and unidade and cst_csosn)
    faltas = [campo for campo, v in
              (("ncm", ncm), ("unidade", unidade), ("cst_csosn", cst_csosn)) if not v]

    return {
        "ncm": ncm,
        "ncm_fonte": ncm_fonte,
        "cfop": cfop,
        "cst_csosn": cst_csosn,
        "regime": regime,
        "unidade": unidade,
        "pronto": pronto,
        "faltas": faltas,
    }


def fiscal_do_pregao(con: sqlite3.Connection, pregao_id: int) -> dict:
    pregao = con.execute("SELECT uf FROM pregoes WHERE id=?", (pregao_id,)).fetchone()
    cfg = config_fiscal(con)
    itens = con.execute(
        "SELECT * FROM itens_pregao WHERE pregao_id=? ORDER BY numero", (pregao_id,)
    ).fetchall()
    resultado = []
    prontos = 0
    cobertos = 0
    for it in itens:
        produto = None
        if it["produto_id"] and it["match_confirmado"]:
            produto = con.execute(
                "SELECT * FROM catalogo_produtos WHERE id=?", (it["produto_id"],)
            ).fetchone()
        f = fiscal_do_item(it, produto, pregao["uf"] if pregao else None, cfg)
        f["item_id"] = it["id"]
        f["numero"] = it["numero"]
        f["tem_produto"] = produto is not None
        if produto is not None:
            cobertos += 1
            if f["pronto"]:
                prontos += 1
        resultado.append(f)
    return {
        "itens": resultado,
        "prontos": prontos,
        "cobertos": cobertos,
        "total": len(itens),
        "regime": cfg.get("regime_tributario"),
        "uf_origem": cfg.get("uf_origem"),
        "aviso": ("Sugestões fiscais (NCM, CFOP, CST/CSOSN) são apoio, não orientação "
                  "contábil. Confirme com seu contador antes de emitir a nota."),
    }
