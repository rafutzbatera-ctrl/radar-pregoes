"""Resultados do pregão — inteligência de mercado por edital.

Num edital HOMOLOGADO, o vencedor por item + o valor unitário homologado
revelam o DESÁGIO real praticado (calibra o `desagio_esperado`, hoje 0.20) e
QUEM é o concorrente (CNPJ/razão social/porte). É inteligência de mercado por
edital — não substitui o valor oficial do PNCP, soma a ele.

Fonte: `cliente.resultados_item(cnpj, ano, seq, numeroItem)` (CLAUDE.md §4 /
endpoint .../itens/{numeroItem}/resultados). Cada chamada é UMA requisição na
pista PESADA do cliente → bater item a item pode ser LENTO (cap defensivo
`max_itens`). Princípio nº 1 do projeto: NUNCA inventar — item sem resultado
publicado entra como `homologado=False`, jamais um chute.

Regras de seleção do vencedor (por item):
- ignorar SEMPRE registros com `dataCancelamento != None` (resultado cancelado);
- vencedor = registro com `ordemClassificacaoSrp == 1`;
- se nenhum tem ordem 1, cai para o de MENOR `valorUnitarioHomologado`;
- sem nenhum registro válido → item sem resultado (vencedor None).
"""
import logging
import sqlite3

log = logging.getLogger("radar.resultados")

# porteFornecedorId → rótulo (CLAUDE.md): 1 ME · 2 EPP · 3 Demais.
_PORTE = {1: "ME", 2: "EPP", 3: "Demais"}


def _porte_rotulo(porte_id) -> str | None:
    """Mapeia porteFornecedorId para rótulo; desconhecido/ausente → None."""
    try:
        return _PORTE.get(int(porte_id))
    except (TypeError, ValueError):
        return None


def _valido(reg: dict) -> bool:
    """Resultado válido = sem dataCancelamento (cancelado se != None)."""
    return reg.get("dataCancelamento") is None


def _escolher_vencedor(resultados: list) -> dict | None:
    """Vencedor de um item: ordemClassificacaoSrp==1; senão menor
    valorUnitarioHomologado; cancelados já foram filtrados antes. None se nada."""
    validos = [r for r in (resultados or []) if _valido(r)]
    if not validos:
        return None
    for r in validos:
        if r.get("ordemClassificacaoSrp") == 1:
            return r
    # nenhum marcado como 1ª colocação → menor valor homologado (com valor)
    com_valor = [r for r in validos if r.get("valorUnitarioHomologado") is not None]
    if com_valor:
        return min(com_valor, key=lambda r: r["valorUnitarioHomologado"])
    # validos sem valor unitário: devolve o primeiro (vencedor sem preço)
    return validos[0]


def _desagio_real_pct(estimado, homologado) -> float | None:
    """(estimado - homologado) / estimado, só quando ambos > 0; senão None
    (não inventa deságio sobre valor ausente/zero — princípio nº 1)."""
    try:
        e = float(estimado)
        h = float(homologado)
    except (TypeError, ValueError):
        return None
    if e > 0 and h > 0:
        return (e - h) / e
    return None


def _linha_item(item_row: sqlite3.Row, resultados: list) -> dict:
    """Monta o dict de saída de UM item a partir dos resultados (já buscados)."""
    estimado = item_row["valor_unit_estimado"]
    base = {
        "numero": item_row["numero"],
        "descricao": item_row["descricao"],
        "valor_estimado_unit": estimado,
        "homologado": False,
        "vencedor_nome": None,
        "vencedor_cnpj": None,
        "porte": None,
        "valor_homologado_unit": None,
        "qtd_homologada": None,
        "valor_homologado_total": None,
        "data_resultado": None,
        "desagio_real_pct": None,
    }
    venc = _escolher_vencedor(resultados)
    if venc is None:
        return base
    hom_unit = venc.get("valorUnitarioHomologado")
    base.update({
        "homologado": True,
        "vencedor_nome": venc.get("nomeRazaoSocialFornecedor"),
        "vencedor_cnpj": venc.get("niFornecedor"),
        "porte": _porte_rotulo(venc.get("porteFornecedorId")),
        "valor_homologado_unit": hom_unit,
        "qtd_homologada": venc.get("quantidadeHomologada"),
        "valor_homologado_total": venc.get("valorTotalHomologado"),
        "data_resultado": venc.get("dataResultado"),
        "desagio_real_pct": _desagio_real_pct(estimado, hom_unit),
    })
    return base


def _resumo(itens: list[dict]) -> dict:
    """Agregado sobre os itens homologados.

    - desagio_medio_real: média do desagio_real_pct PONDERADA pela receita
      homologada (homologado_unit*qtd), só sobre itens com desagio_real_pct
      não-None (e peso > 0).
    - economia_total: Σ (estimado - homologado)*qtd_homologada sobre itens
      homologados que têm estimado e homologado.
    - n_homologados: contagem de itens homologados.
    """
    n_homologados = sum(1 for d in itens if d["homologado"])
    soma_peso = 0.0
    soma_pond = 0.0
    economia = 0.0
    tem_economia = False
    for d in itens:
        if not d["homologado"]:
            continue
        est = d["valor_estimado_unit"]
        hom = d["valor_homologado_unit"]
        qtd = d["qtd_homologada"]
        # economia (Σ (estimado-homologado)*qtd) sobre itens com estimado+homologado
        if est is not None and hom is not None and qtd is not None:
            economia += (float(est) - float(hom)) * float(qtd)
            tem_economia = True
        # deságio médio ponderado pela receita homologada
        if d["desagio_real_pct"] is not None and hom is not None and qtd is not None:
            peso = float(hom) * float(qtd)
            if peso > 0:
                soma_peso += peso
                soma_pond += d["desagio_real_pct"] * peso
    desagio_medio = (soma_pond / soma_peso) if soma_peso > 0 else None
    return {
        "n_homologados": n_homologados,
        "desagio_medio_real": desagio_medio,
        "economia_total": economia if tem_economia else None,
    }


def resultados_do_pregao(con: sqlite3.Connection, pregao_id: int,
                         cliente=None, max_itens: int = 60) -> dict:
    """Resultados (vencedor + deságio real) de cada item do pregão.

    Lê os itens persistidos (itens_pregao), bate item a item no PNCP via
    `cliente.resultados_item(...)` (pista pesada — pode ser lento), monta a
    linha por item e o agregado `resumo`.

    Retorno:
      - nenhum item com resultado → {homologado: False, itens: [...todos
        com homologado False...], resumo: None};
      - algum item com resultado → {homologado: True, itens: [...], resumo: {...}}.

    Robustez: cap `max_itens` (se truncar, logging.warning); falha de UM item
    (exceção da chamada) NÃO derruba o lote — loga e trata o item como sem
    resultado. Cliente None → usa a instância compartilhada do app.
    """
    if cliente is None:
        from .. import pncp
        cliente = pncp.cliente()

    p = con.execute(
        "SELECT cnpj, ano, seq FROM pregoes WHERE id=?", (pregao_id,)
    ).fetchone()
    if p is None:
        raise ValueError("Pregão não encontrado")

    linhas = con.execute(
        "SELECT numero, descricao, valor_unit_estimado FROM itens_pregao"
        " WHERE pregao_id=? ORDER BY numero", (pregao_id,)
    ).fetchall()

    if len(linhas) > max_itens:
        log.warning(
            "pregão %s tem %d itens > cap %d — resultados truncados ao cap",
            pregao_id, len(linhas), max_itens,
        )
        linhas = linhas[:max_itens]

    itens: list[dict] = []
    algum = False
    for ln in linhas:
        try:
            resultados = cliente.resultados_item(
                p["cnpj"], p["ano"], p["seq"], ln["numero"]
            )
        except Exception as exc:  # falha de UM item não derruba o lote
            log.warning(
                "resultados do item %s (pregão %s) falharam: %s — tratado como sem resultado",
                ln["numero"], pregao_id, exc,
            )
            resultados = []
        d = _linha_item(ln, resultados)
        if d["homologado"]:
            algum = True
        itens.append(d)

    if not algum:
        return {"homologado": False, "itens": itens, "resumo": None}
    return {"homologado": True, "itens": itens, "resumo": _resumo(itens)}
