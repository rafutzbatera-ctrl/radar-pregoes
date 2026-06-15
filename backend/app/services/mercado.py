"""Inteligência de mercado — AGREGAÇÕES sobre `resultados_itens` (Dores #8/#9).

Lê os itens HOMOLOGADOS já coletados (sob demanda via POST /mercado/coletar e
gravados por `services/resultados.coletar_resultados`) e responde duas
perguntas, SEM bater no PNCP:

  #8 histórico de preços — por quanto produtos parecidos foram homologados,
     qual o deságio real praticado;
  #9 concorrentes — quem vence, em quantos itens, com que deságio, em que UFs.

Princípio nº 1 (NUNCA inventar) e honestidade da amostra: a base reflete SÓ os
editais já coletados pelo usuário — não é uma base nacional. Por isso toda
resposta expõe o tamanho da amostra (`amostra`/`amostra_itens`); sem dados a
resposta é vazia e explícita (resumo None / listas vazias), nunca um chute.
"""
import re
import sqlite3
import statistics
import unicodedata


def _normalizar(texto: str) -> str:
    """Caixa baixa + sem acento (NFKD) + espaços colapsados.

    Mesmo estilo do gate de citação (services/habilitacao._normalizar), aqui
    com remoção de acentos (NFKD + descarte de combinantes) porque o match de
    termo precisa casar 'audio' com 'áudio'. Pontuação vira espaço para não
    grudar tokens.
    """
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = texto.lower()
    texto = re.sub(r"[^\w\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _palavras_conteudo(termo: str) -> list[str]:
    """Palavras de conteúdo do termo normalizado (descarta tokens <= 2 chars,
    que costumam ser ruído tipo 'de'/'da'). Se sobrar nada, devolve [] e o
    chamador trata como 'sem filtro de termo casável'."""
    return [w for w in _normalizar(termo).split() if len(w) > 2]


def _casa_termo(descricao: str, palavras: list[str]) -> bool:
    """Match previsível: a descrição NORMALIZADA contém TODAS as palavras de
    conteúdo do termo (cada palavra como substring). Conjunção simples,
    determinística, sem stemming nem embeddings."""
    if not palavras:
        return True
    alvo = _normalizar(descricao)
    return all(p in alvo for p in palavras)


def historico_precos(con: sqlite3.Connection, termo: str | None = None,
                     ncm: str | None = None, limite: int = 80) -> dict:
    """Histórico de preços homologados (#8) filtrando `resultados_itens`.

    Filtros (combináveis, AND): `ncm` exato (se dado) e `termo` (a descrição
    normalizada precisa conter TODAS as palavras de conteúdo do termo — ver
    `_casa_termo`). SÓ entram itens com `valor_homologado_unit` não nulo.

    A amostra reflete só os editais já coletados pelo usuário (não é base
    nacional) — por isso `amostra` (N) vem sempre exposto.

    Retorna {amostra, resumo, itens}:
      - resumo = {preco_unit_min, preco_unit_mediana, preco_unit_max,
        desagio_medio_pct, amostra_desagio, unidades} (mediana via
        statistics.median em Python; deságio = média aritmética dos
        desagio_real_pct NÃO-nulos);
        `amostra_desagio` = nº de itens com desagio_real_pct não-nulo (o N REAL
        sobre o qual desagio_medio_pct foi calculado, ≤ amostra);
        `unidades` = lista de {unidade, n} (contagem por unidade na amostra),
        para a UI avisar quando o "preço unitário" mistura unidades (UN, m...);
      - itens = até `limite`, ordenados por data_resultado desc;
      - sem dados → {amostra: 0, resumo: None, itens: []}.
    """
    where = ["valor_homologado_unit IS NOT NULL"]
    params: list = []
    if ncm:
        where.append("ncm = ?")
        params.append(ncm)
    sql = (
        "SELECT descricao, ncm, unidade, valor_estimado_unit,"
        " valor_homologado_unit, desagio_real_pct, vencedor_nome,"
        " vencedor_porte, orgao_nome, uf, ano, data_resultado"
        " FROM resultados_itens WHERE " + " AND ".join(where) +
        " ORDER BY data_resultado DESC"
    )
    linhas = con.execute(sql, params).fetchall()

    palavras = _palavras_conteudo(termo) if termo else []
    if termo:
        linhas = [r for r in linhas if _casa_termo(r["descricao"], palavras)]

    if not linhas:
        return {"amostra": 0, "resumo": None, "itens": []}

    precos = [float(r["valor_homologado_unit"]) for r in linhas]
    desagios = [float(r["desagio_real_pct"]) for r in linhas
                if r["desagio_real_pct"] is not None]
    # contagem por unidade na amostra (None vira "?" para não sumir da conta)
    cont_unid: dict = {}
    for r in linhas:
        u = r["unidade"] if r["unidade"] is not None else "?"
        cont_unid[u] = cont_unid.get(u, 0) + 1
    unidades = [{"unidade": u, "n": n} for u, n in
                sorted(cont_unid.items(), key=lambda kv: (-kv[1], kv[0]))]
    resumo = {
        "preco_unit_min": min(precos),
        "preco_unit_mediana": statistics.median(precos),
        "preco_unit_max": max(precos),
        "desagio_medio_pct": (sum(desagios) / len(desagios)) if desagios else None,
        "amostra_desagio": len(desagios),
        "unidades": unidades,
    }
    itens = [
        {
            "descricao": r["descricao"],
            "ncm": r["ncm"],
            "unidade": r["unidade"],
            "valor_estimado_unit": r["valor_estimado_unit"],
            "valor_homologado_unit": r["valor_homologado_unit"],
            "desagio_real_pct": r["desagio_real_pct"],
            "vencedor_nome": r["vencedor_nome"],
            "vencedor_porte": r["vencedor_porte"],
            "orgao_nome": r["orgao_nome"],
            "uf": r["uf"],
            "ano": r["ano"],
            "data_resultado": r["data_resultado"],
        }
        for r in linhas[:limite]
    ]
    return {"amostra": len(linhas), "resumo": resumo, "itens": itens}


def _mais_frequente(valores: list, ignorar_none: bool = False):
    """Valor mais frequente de uma lista (moda simples; primeiro a atingir o
    pico em caso de empate). `ignorar_none` descarta None antes de contar.
    Lista vazia (ou só None com ignorar_none) → None."""
    if ignorar_none:
        valores = [v for v in valores if v is not None]
    if not valores:
        return None
    contagem: dict = {}
    melhor = None
    melhor_n = 0
    for v in valores:
        n = contagem.get(v, 0) + 1
        contagem[v] = n
        if n > melhor_n:
            melhor_n = n
            melhor = v
    return melhor


def concorrentes(con: sqlite3.Connection, uf: str | None = None,
                 termo: str | None = None, limite: int = 60) -> dict:
    """Quem vence (#9) — agrega `resultados_itens` por `vencedor_cnpj`.

    Linhas com `vencedor_cnpj` nulo são ignoradas. Filtros opcionais: `uf` (=
    uf do edital) e `termo` (match normalizado em descricao, ver `_casa_termo`).

    A amostra reflete só os editais já coletados pelo usuário (não é base
    nacional) — por isso `amostra_itens` (N de itens considerados) vem sempre.

    Por concorrente: {cnpj, nome (vencedor_nome mais frequente), porte (idem,
    mais frequente não-nulo), n_vitorias, desagio_medio_pct (média dos
    desagio_real_pct não-nulos), n_com_desagio (nº de linhas com desagio não-
    nulo — base do desagio_medio_pct, ≤ n_vitorias), valor_total_homologado
    (Σ homologado_unit*qtd quando ambos), n_com_valor (nº de linhas que entraram
    nesse total, ≤ n_vitorias), n_orgaos (órgãos distintos), ufs (UFs distintas)}.
    n_com_desagio/n_com_valor deixam a UI mostrar que esses agregados podem vir
    de MENOS linhas que n_vitorias.

    O corte por `limite` é POR n_vitorias (quem mais venceu). Desempate
    determinístico/reproduzível: key=(-n_vitorias, -(valor_total or 0), cnpj).

    Retorna {amostra_itens, concorrentes (até `limite`)}; sem dados →
    {amostra_itens: 0, concorrentes: []}.
    """
    where = ["vencedor_cnpj IS NOT NULL"]
    params: list = []
    if uf:
        where.append("uf = ?")
        params.append(uf)
    sql = (
        "SELECT vencedor_cnpj, vencedor_nome, vencedor_porte, descricao,"
        " desagio_real_pct, valor_homologado_unit, qtd_homologada,"
        " orgao_nome, uf FROM resultados_itens WHERE " + " AND ".join(where)
    )
    linhas = con.execute(sql, params).fetchall()

    palavras = _palavras_conteudo(termo) if termo else []
    if termo:
        linhas = [r for r in linhas if _casa_termo(r["descricao"], palavras)]

    if not linhas:
        return {"amostra_itens": 0, "concorrentes": []}

    grupos: dict[str, list] = {}
    for r in linhas:
        grupos.setdefault(r["vencedor_cnpj"], []).append(r)

    saida = []
    for cnpj, rows in grupos.items():
        desagios = [float(x["desagio_real_pct"]) for x in rows
                    if x["desagio_real_pct"] is not None]
        valor_total = 0.0
        tem_valor = False
        for x in rows:
            hom = x["valor_homologado_unit"]
            qtd = x["qtd_homologada"]
            if hom is not None and qtd is not None:
                valor_total += float(hom) * float(qtd)
                tem_valor = True
        orgaos = {x["orgao_nome"] for x in rows if x["orgao_nome"] is not None}
        ufs = sorted({x["uf"] for x in rows if x["uf"] is not None})
        n_com_valor = sum(
            1 for x in rows
            if x["valor_homologado_unit"] is not None and x["qtd_homologada"] is not None
        )
        saida.append({
            "cnpj": cnpj,
            "nome": _mais_frequente([x["vencedor_nome"] for x in rows]),
            "porte": _mais_frequente([x["vencedor_porte"] for x in rows],
                                     ignorar_none=True),
            "n_vitorias": len(rows),
            "desagio_medio_pct": (sum(desagios) / len(desagios)) if desagios else None,
            "n_com_desagio": len(desagios),
            "valor_total_homologado": valor_total if tem_valor else None,
            "n_com_valor": n_com_valor,
            "n_orgaos": len(orgaos),
            "ufs": ufs,
        })

    # desempate determinístico: mais vitórias, depois maior valor, depois cnpj.
    saida.sort(key=lambda c: (-c["n_vitorias"],
                              -(c["valor_total_homologado"] or 0),
                              c["cnpj"]))
    return {"amostra_itens": len(linhas), "concorrentes": saida[:limite]}
