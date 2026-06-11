"""Cálculo de margem, lucro e veredito (CLAUDE.md §6.2).

Princípio 4: só itens com match CONFIRMADO entram na conta. Item sigiloso
(valores nulos) não entra na soma mesmo confirmado. O veredito nunca
esconde a conta — os números crus acompanham sempre.
"""
import sqlite3

from .. import settings


def _regras(con: sqlite3.Connection) -> dict:
    regras = dict(settings.VEREDITO_PADRAO)
    linhas = con.execute(
        "SELECT chave, valor FROM config WHERE chave LIKE 'veredito_%'"
    ).fetchall()
    for ln in linhas:
        chave = ln["chave"].removeprefix("veredito_")
        if chave in regras:
            regras[chave] = float(ln["valor"])
    return regras


def analisar_pregao(con: sqlite3.Connection, pregao_id: int) -> dict:
    """Recalcula agregados e veredito do pregão e persiste nas colunas calculadas."""
    itens = con.execute(
        """SELECT i.*, p.custo_unit FROM itens_pregao i
           LEFT JOIN catalogo_produtos p ON p.id = i.produto_id
           WHERE i.pregao_id = ?""",
        (pregao_id,),
    ).fetchall()

    total_itens = len(itens)
    confirmados = 0
    lucro_potencial = 0.0
    soma_pesos = 0.0          # margem média ponderada pelo valor do item
    soma_margem_peso = 0.0

    for it in itens:
        if not it["match_confirmado"] or it["produto_id"] is None:
            continue
        confirmados += 1
        unit = it["valor_unit_estimado"]
        custo = it["custo_unit"]
        qtd = it["qtd"] or 0
        if it["sigiloso"] or unit is None or custo is None or unit <= 0:
            continue  # sem valor oficial não há conta a fazer
        margem = (unit - custo) / unit
        lucro_potencial += (unit - custo) * qtd
        peso = unit * qtd
        soma_pesos += peso
        soma_margem_peso += margem * peso

    margem_media = (soma_margem_peso / soma_pesos) if soma_pesos > 0 else None
    cobertura = (confirmados / total_itens) if total_itens else 0.0

    veredito = None
    if confirmados > 0 and margem_media is not None:
        r = _regras(con)
        if (margem_media >= r["vale_margem_min"]
                and cobertura >= r["vale_cobertura_min"]
                and lucro_potencial >= r["vale_lucro_min"]):
            veredito = "vale"
        elif (margem_media < r["nao_vale_margem_max"]
              or lucro_potencial < r["nao_vale_lucro_max"]):
            veredito = "nao_vale"
        else:
            veredito = "talvez"

    con.execute(
        "UPDATE pregoes SET veredito=?, lucro_potencial=?, margem_media=? WHERE id=?",
        (veredito, lucro_potencial if confirmados else None,
         margem_media, pregao_id),
    )
    con.commit()
    return {
        "veredito": veredito,
        "lucro_potencial": lucro_potencial if confirmados else None,
        "margem_media": margem_media,
        "cobertura": cobertura,
        "itens_total": total_itens,
        "itens_confirmados": confirmados,
    }


def margem_lucro_item(valor_unit, custo_unit, qtd) -> dict:
    """Conta por item (exposta nos endpoints junto dos dados crus)."""
    if valor_unit is None or custo_unit is None or not valor_unit:
        return {"margem": None, "lucro": None}
    margem = (valor_unit - custo_unit) / valor_unit
    lucro = (valor_unit - custo_unit) * (qtd or 0)
    return {"margem": margem, "lucro": lucro}
