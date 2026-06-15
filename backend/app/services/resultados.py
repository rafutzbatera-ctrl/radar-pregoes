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


def _cnpj_digitos(cnpj) -> str | None:
    """CNPJ só com dígitos. O PNCP costuma mandar assim, mas isto blinda contra
    formatação variada que fragmentaria o MESMO concorrente em grupos distintos
    na agregação de mercado (#9). Vazio/None → None (nunca inventa)."""
    if not cnpj:
        return None
    d = "".join(c for c in str(cnpj) if c.isdigit())
    return d or None


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
    """Monta o dict de saída de UM item a partir dos resultados (já buscados).

    NOTA sobre homologação: o projeto NÃO chuta — a homologação é INFERIDA por
    `ordemClassificacaoSrp == 1` (1ª colocação) + presença de
    `valorUnitarioHomologado`. Filtrar por `situacaoCompraItemResultadoId` seria
    o sinal canônico do PNCP, mas NÃO temos a semântica verificada desses ids
    (1, 2, ...), então é refinamento FUTURO que exige mapear/validar os ids do
    PNCP antes — sem mapa verificado, não usamos (princípio nº 1).
    O `coletar_resultados` só persiste FATO DE MERCADO quando há
    `valor_homologado_unit` (item homologado sem preço unitário não é fato)."""
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


# Cap defensivo da coleta em massa: bater item a item no PNCP por pregão é
# LENTO (pista pesada). Acima disso, trunca e loga (uso manual/sob demanda).
_CAP_PREGOES = 200


def _ncm_do_item(con: sqlite3.Connection, pregao_id: int, numero: int):
    """NCM do item em itens_pregao (ncm_pncp) por (pregao_id, numero).

    resultados_do_pregao NÃO traz ncm; aqui resolvemos da tabela de itens.
    Ausente/sem linha → None (NUNCA inventado — princípio nº 1)."""
    r = con.execute(
        "SELECT ncm_pncp, unidade FROM itens_pregao WHERE pregao_id=? AND numero=?",
        (pregao_id, numero),
    ).fetchone()
    if r is None:
        return None, None
    return r["ncm_pncp"], r["unidade"]


def coletar_resultados(con: sqlite3.Connection, pregao_ids=None,
                       cliente=None) -> dict:
    """ETL de inteligência de mercado: persiste FATOS DE MERCADO em
    resultados_itens (denormalizado, upsert idempotente por pregao+item).

    FATO DE MERCADO = item homologado (inferido por ordemClassificacaoSrp==1 +
    valor homologado presente — ver `_linha_item`) E COM `valor_homologado_unit`
    não nulo. Item homologado sem preço unitário homologado NÃO é fato de
    mercado → não grava (não há "por quanto venceu"). Filtrar por
    `situacaoCompraItemResultadoId` é refinamento FUTURO (exige mapeamento
    verificado dos ids do PNCP, hoje inexistente — princípio nº 1).

    - `pregao_ids` None → varre TODOS os pregões (cap defensivo _CAP_PREGOES,
      logando se truncar). Pregões sem fato simplesmente não gravam nada.
    - Para cada pregão: lê a linha (orgao/uf/cnpj/ano/seq), chama
      `resultados_do_pregao`; faz UPSERT de cada item homologado COM preço +
      denormalização + ncm/unidade de itens_pregao + coletado_em=datetime('now').
    - RECONCILIAÇÃO: a cada coleta, na MESMA transação do pregão e ANTES do
      commit, apaga de resultados_itens as linhas daquele pregão cujo
      numero_item NÃO veio na coleta atual como fato válido (resultado
      revogado/cancelado/sem preço some). Coleta sem nenhum fato → apaga TODAS
      as linhas do pregão. DELETE+UPSERT são atômicos por pregão.
    - Robustez: falha de UM pregão é logada, faz rollback e NÃO derruba o lote.

    LENTO: bate no PNCP item a item por pregão — é manual/sob demanda.
    Retorna {pregoes_processados, pregoes_homologados, itens_gravados}.
    """
    if cliente is None:
        from .. import pncp
        cliente = pncp.cliente()

    if pregao_ids is None:
        linhas = con.execute(
            "SELECT id FROM pregoes ORDER BY id"
        ).fetchall()
        ids = [r["id"] for r in linhas]
        if len(ids) > _CAP_PREGOES:
            log.warning(
                "coletar_resultados: %d pregões > cap %d — truncado ao cap",
                len(ids), _CAP_PREGOES,
            )
            ids = ids[:_CAP_PREGOES]
    else:
        ids = list(pregao_ids)

    pregoes_processados = 0
    pregoes_homologados = 0
    itens_gravados = 0

    for pid in ids:
        try:
            p = con.execute(
                "SELECT cnpj, ano, seq, orgao, uf FROM pregoes WHERE id=?",
                (pid,),
            ).fetchone()
            if p is None:
                log.warning("coletar_resultados: pregão %s inexistente — pulado", pid)
                continue
            pregoes_processados += 1
            out = resultados_do_pregao(con, pid, cliente)
            # FATO DE MERCADO: homologado E com preço unitário homologado.
            fatos = [
                d for d in out["itens"]
                if d.get("homologado") and d.get("valor_homologado_unit") is not None
            ]
            numeros_fato = [d["numero"] for d in fatos]
            # RECONCILIAÇÃO atômica (antes do commit deste pregão): apaga as
            # linhas órfãs — itens que não vieram como fato válido nesta coleta.
            if numeros_fato:
                marks = ",".join("?" for _ in numeros_fato)
                con.execute(
                    f"DELETE FROM resultados_itens WHERE pregao_id=?"
                    f" AND numero_item NOT IN ({marks})",
                    (pid, *numeros_fato),
                )
            else:
                # nenhum fato nesta coleta → resultado some por completo.
                con.execute(
                    "DELETE FROM resultados_itens WHERE pregao_id=?", (pid,)
                )
                con.commit()
                continue
            pregoes_homologados += 1
            for d in fatos:
                ncm, unidade = _ncm_do_item(con, pid, d["numero"])
                con.execute(
                    """
                    INSERT INTO resultados_itens(
                        pregao_id, cnpj, ano, seq, numero_item, descricao,
                        ncm, unidade, qtd_homologada, valor_estimado_unit,
                        valor_homologado_unit, desagio_real_pct,
                        vencedor_cnpj, vencedor_nome, vencedor_porte,
                        data_resultado, orgao_nome, uf, coletado_em
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
                    ON CONFLICT(pregao_id, numero_item) DO UPDATE SET
                        cnpj=excluded.cnpj, ano=excluded.ano, seq=excluded.seq,
                        descricao=excluded.descricao, ncm=excluded.ncm,
                        unidade=excluded.unidade,
                        qtd_homologada=excluded.qtd_homologada,
                        valor_estimado_unit=excluded.valor_estimado_unit,
                        valor_homologado_unit=excluded.valor_homologado_unit,
                        desagio_real_pct=excluded.desagio_real_pct,
                        vencedor_cnpj=excluded.vencedor_cnpj,
                        vencedor_nome=excluded.vencedor_nome,
                        vencedor_porte=excluded.vencedor_porte,
                        data_resultado=excluded.data_resultado,
                        orgao_nome=excluded.orgao_nome, uf=excluded.uf,
                        coletado_em=excluded.coletado_em
                    """,
                    (
                        pid, p["cnpj"], p["ano"], p["seq"], d["numero"],
                        d["descricao"], ncm, unidade, d["qtd_homologada"],
                        d["valor_estimado_unit"], d["valor_homologado_unit"],
                        d["desagio_real_pct"], _cnpj_digitos(d["vencedor_cnpj"]),
                        d["vencedor_nome"], d["porte"], d["data_resultado"],
                        p["orgao"], p["uf"],
                    ),
                )
                itens_gravados += 1
            con.commit()
        except Exception as exc:  # falha de UM pregão não derruba o lote
            log.warning(
                "coletar_resultados: pregão %s falhou: %s — pulado", pid, exc,
            )
            try:
                con.rollback()
            except Exception:
                pass

    return {
        "pregoes_processados": pregoes_processados,
        "pregoes_homologados": pregoes_homologados,
        "itens_gravados": itens_gravados,
    }
