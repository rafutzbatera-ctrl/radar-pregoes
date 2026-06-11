"""Cálculo de margem, lucro e veredito (CLAUDE.md §6.2 — atualizado P3/P4).

Custo efetivo do item = `custo_manual` (override local do pregão) ▸ custo do
produto com match CONFIRMADO ▸ sem custo. Todo item com custo efetivo e PREÇO
ESPERADO entra na conta — inclusive item com custo manual e SEM match. A
cobertura e o veredito usam os itens COM CUSTO; o `itens_confirmados` (matches
confirmados) segue para a UI de matching.

P4 — preço esperado de disputa: o valor do edital é TETO (leilão reverso, menor
preço vence); a conta no teto é o cenário mais otimista. O preço esperado do
item = `lance_previsto` (digitado) ▸ `teto × (1 − desagio_esperado)` ▸ teto.
Item sigiloso (teto nulo) só entra na conta se houver lance_previsto. Margem e
lucro passam a usar o preço esperado; o teto oficial do PNCP nunca some da tela
(princípio 1). O veredito nunca esconde a conta — os números crus acompanham.
"""
import sqlite3

from .. import settings


def desagio_da_config(con: sqlite3.Connection) -> float:
    """Deságio esperado global (% abaixo do teto). Default 0.00 = teto."""
    ln = con.execute(
        "SELECT valor FROM config WHERE chave='desagio_esperado'").fetchone()
    if ln is None:
        return 0.0
    try:
        return float(ln["valor"])
    except (ValueError, TypeError):
        return 0.0


def preco_esperado_row(it, desagio: float) -> tuple[float | None, str | None]:
    """Preço esperado e sua fonte: lance_previsto ▸ teto×(1−deságio) ▸ teto.
    Item sigiloso (sem teto) só tem preço se houver lance_previsto."""
    lance = it["lance_previsto"] if "lance_previsto" in it.keys() else None
    if lance is not None:
        return lance, "lance"
    if it["sigiloso"]:
        return None, None
    teto = it["valor_unit_estimado"]
    if teto is None or teto <= 0:
        return None, None
    if desagio and desagio > 0:
        return teto * (1 - desagio), "desagio"
    return teto, "teto"


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


def custo_efetivo_row(it) -> tuple[float | None, str | None]:
    """Custo efetivo e sua fonte a partir de uma linha (itens_pregao + custo_unit
    do produto confirmado). manual ▸ catálogo (só com match confirmado) ▸ None."""
    if it["custo_manual"] is not None:
        return it["custo_manual"], "manual"
    custo_cat = it["custo_unit"] if "custo_unit" in it.keys() else None
    if (custo_cat is not None and it["match_confirmado"]
            and it["produto_id"] is not None):
        return custo_cat, "catalogo"
    return None, None


def analisar_pregao(con: sqlite3.Connection, pregao_id: int) -> dict:
    """Recalcula agregados e veredito do pregão e persiste nas colunas calculadas."""
    itens = con.execute(
        """SELECT i.*, p.custo_unit FROM itens_pregao i
           LEFT JOIN catalogo_produtos p ON p.id = i.produto_id
           WHERE i.pregao_id = ?""",
        (pregao_id,),
    ).fetchall()

    # deságio esperado lido UMA vez por análise (P4)
    desagio = desagio_da_config(con)

    total_itens = len(itens)
    confirmados = 0          # matches confirmados (para a UI de matching)
    com_custo = 0            # itens com custo efetivo e preço esperado (na conta)
    lucro_potencial = 0.0
    soma_pesos = 0.0          # margem média ponderada pela RECEITA esperada
    soma_margem_peso = 0.0

    for it in itens:
        if it["match_confirmado"] and it["produto_id"] is not None:
            confirmados += 1
        custo, _fonte = custo_efetivo_row(it)
        if custo is None:
            continue
        # P4: a conta usa o PREÇO ESPERADO (lance ▸ teto×(1−deságio) ▸ teto),
        # não o teto cru. Sem preço esperado (sigiloso sem lance) → fora.
        preco, _fp = preco_esperado_row(it, desagio)
        if preco is None or preco <= 0:
            continue
        qtd = it["qtd"] or 0
        com_custo += 1
        margem = (preco - custo) / preco
        lucro_potencial += (preco - custo) * qtd
        peso = preco * qtd       # receita esperada — coerente com o lucro
        soma_pesos += peso
        soma_margem_peso += margem * peso

    margem_media = (soma_margem_peso / soma_pesos) if soma_pesos > 0 else None
    cobertura = (com_custo / total_itens) if total_itens else 0.0

    veredito = None
    if com_custo > 0 and margem_media is not None:
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
        (veredito, lucro_potencial if com_custo else None,
         margem_media, pregao_id),
    )
    con.commit()
    return {
        "veredito": veredito,
        "lucro_potencial": lucro_potencial if com_custo else None,
        "margem_media": margem_media,
        "cobertura": cobertura,
        "itens_total": total_itens,
        "itens_confirmados": confirmados,
        "itens_com_custo": com_custo,
    }


def margem_lucro_item(valor_unit, custo_unit, qtd) -> dict:
    """Conta por item (exposta nos endpoints junto dos dados crus)."""
    if valor_unit is None or custo_unit is None or not valor_unit:
        return {"margem": None, "lucro": None}
    margem = (valor_unit - custo_unit) / valor_unit
    lucro = (valor_unit - custo_unit) * (qtd or 0)
    return {"margem": margem, "lucro": lucro}
