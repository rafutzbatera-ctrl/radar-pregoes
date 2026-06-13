"""RAG leve, extrativo e citation-grounded (Fase 1) — Q&A sobre os documentos
de UM edital por vez (CLAUDE.md princípios 1 e 2).

EXTRATIVO: a resposta SÃO os trechos recuperados do PDF, verbatim — nunca há
síntese nem LLM nesta camada. Cada trecho carrega página + offsets de caractere
na string ORIGINAL da página, então `pagina[offset_inicio:offset_fim]` reproduz
exatamente o `texto` indexado (verificável pelo gate de citação). Nada é
inventado: abaixo do threshold a resposta é "não encontrado".

Pipeline:
- _chunkar: quebra cada página (texto cru) em blocos por linha em branco,
  preferindo fronteiras de cláusula numerada; empacota até RAG_CHUNK_MAX chars
  com overlap, preservando offsets verbatim.
- indexar_chunks: embeda os chunks com o e5 ("passage: ") e grava o vetor como
  BLOB float32; idempotente por pregão.
- ingerir: parte de IO — obtém os PDFs (já baixados ou via PNCP), extrai páginas
  e chama indexar_chunks.
- perguntar: embeda a pergunta ("query: "), faz cosseno (numpy) contra a matriz
  de vetores e devolve os top-k acima do threshold.

Reusa: matching.embed_padrao (e5, vetores normalizados), extracao.extrair_paginas,
sincronizacao._baixar_arquivos, pncp.cliente().
"""
import logging
import re
import sqlite3

import numpy as np

from .. import pncp, settings
from . import extracao, matching, sincronizacao

log = logging.getLogger("radar.rag")

# fronteira de cláusula numerada no início de linha (ex.: "1 ", "1.2 ", "10.3) ")
_RE_CLAUSULA = re.compile(r"^\s*\d+(\.\d+)*[\.\)]?\s")
# mínimo de caracteres ÚTEIS (sem espaços) para um chunk valer a pena
# (configurável via RADAR_RAG_CHUNK_MIN; default 40)
_MIN_UTEIS = settings.RAG_CHUNK_MIN


def _texto_util(s: str) -> int:
    """Quantos caracteres não-espaço o trecho tem (descarta chunks só de espaço)."""
    return len(re.sub(r"\s+", "", s))


# ruído de extração de PDF escaneado/com imagem (pymupdf4llm): placeholders de
# imagem e blobs hex/base64 de assinatura digital. NÃO é conteúdo do edital e,
# por ser quase idêntico entre páginas, achata o cosseno (tudo ~0.84) e engana o
# threshold. Filtra-se por BLOCO — o verbatim dos chunks sobreviventes é mantido
# (só escolhemos quais spans viram chunk; nunca editamos o texto).
_RE_RUIDO = re.compile(
    r"intentionally omitted|-{3,}\s*(start|end) of picture text|==>\s*picture"
    r"|[A-F0-9]{20,}",
    re.IGNORECASE,
)


def _e_ruido(texto: str) -> bool:
    """True para blocos que são ruído de extração (não conteúdo do edital)."""
    return bool(_RE_RUIDO.search(texto))


def _blocos_da_pagina(pagina: str) -> list[tuple[int, int]]:
    """Quebra a página em blocos (parágrafos), retornando (inicio, fim) de cada
    bloco como índices na string ORIGINAL. Fronteiras: linha em branco e início
    de cláusula numerada. Não inclui blocos vazios.

    Os offsets são fechados-abertos [inicio, fim) e SEMPRE índices na `pagina`
    crua — pagina[inicio:fim] é o bloco verbatim.
    """
    if not pagina:
        return []
    # offsets de início de cada linha na string original
    linhas: list[tuple[int, int]] = []  # (inicio_linha, fim_linha) sem o \n
    pos = 0
    for linha in pagina.splitlines(keepends=True):
        sem_quebra = linha.rstrip("\r\n")
        linhas.append((pos, pos + len(sem_quebra)))
        pos += len(linha)

    blocos: list[tuple[int, int]] = []
    bloco_ini: int | None = None
    bloco_fim: int | None = None
    for ini, fim in linhas:
        conteudo = pagina[ini:fim]
        vazia = conteudo.strip() == ""
        nova_clausula = bool(_RE_CLAUSULA.match(conteudo))
        if vazia:
            # fecha o bloco corrente numa linha em branco
            if bloco_ini is not None:
                blocos.append((bloco_ini, bloco_fim))
                bloco_ini = bloco_fim = None
            continue
        if nova_clausula and bloco_ini is not None:
            # nova cláusula numerada inicia um bloco novo
            blocos.append((bloco_ini, bloco_fim))
            bloco_ini = bloco_fim = None
        if bloco_ini is None:
            bloco_ini = ini
        bloco_fim = fim
    if bloco_ini is not None:
        blocos.append((bloco_ini, bloco_fim))
    return blocos


def _chunkar(paginas: list[str]) -> list[dict]:
    """Chunka o texto CRU de cada página preservando offsets verbatim.

    Para cada página (1-based), agrupa blocos consecutivos até RAG_CHUNK_MAX
    chars; chunks curtos (< _MIN_UTEIS úteis) são descartados. Há overlap de
    ~RAG_CHUNK_OVERLAP chars entre chunks da mesma página (o próximo chunk
    recua o início para incluir a cauda do anterior, sem nunca cruzar páginas).

    INVARIANTE (asseverada em teste): para todo chunk,
        chunk["texto"] == paginas[chunk["pagina"]-1][offset_inicio:offset_fim]
    """
    chunk_max = settings.RAG_CHUNK_MAX
    overlap = settings.RAG_CHUNK_OVERLAP
    out: list[dict] = []

    for idx, pagina in enumerate(paginas):
        if not pagina or not pagina.strip():
            continue
        num_pagina = idx + 1
        blocos = _blocos_da_pagina(pagina)
        # descarta blocos de ruído de extração (placeholder de imagem, blob hex
        # de assinatura) — preserva o verbatim: só remove spans inteiros
        blocos = [b for b in blocos if not _e_ruido(pagina[b[0]:b[1]])]
        if not blocos:
            continue
        ordem = 0
        cur_ini: int | None = None
        cur_fim: int | None = None

        def fechar(ini: int, fim: int):
            nonlocal ordem
            texto = pagina[ini:fim]
            if _texto_util(texto) < _MIN_UTEIS:
                return
            out.append({
                "pagina": num_pagina,
                "ordem": ordem,
                "offset_inicio": ini,
                "offset_fim": fim,
                "texto": texto,
            })
            ordem += 1

        for b_ini, b_fim in blocos:
            if cur_ini is None:
                cur_ini, cur_fim = b_ini, b_fim
                continue
            # cabe no chunk corrente? (mede do início atual até o fim do bloco)
            if (b_fim - cur_ini) <= chunk_max:
                cur_fim = b_fim
            else:
                # fecha o atual e começa um novo com overlap (recua o início
                # para a cauda do chunk anterior, sem ultrapassar o seu começo)
                fechar(cur_ini, cur_fim)
                novo_ini = max(cur_ini, cur_fim - overlap)
                # se o bloco já é maior que o teto sozinho, não força overlap
                cur_ini = min(novo_ini, b_ini)
                cur_fim = b_fim
        if cur_ini is not None:
            fechar(cur_ini, cur_fim)
    return out


def _vetor_para_blob(v) -> bytes:
    """Serializa um vetor (lista/np.ndarray) como float32 contíguo → BLOB."""
    return np.asarray(v, dtype=np.float32).tobytes()


def indexar_chunks(con: sqlite3.Connection, pregao_id: int, fontes,
                   embed=matching.embed_padrao) -> dict:
    """Chunka, embeda e persiste os chunks de um pregão. Idempotente.

    `fontes` = lista de (arquivo_id:int|None, paginas:list[str]). Reindexar um
    pregão apaga os chunks anteriores antes de inserir (DELETE por pregao_id).
    Os textos vão ao embed com o prefixo "passage: " do e5; o vetor (já
    normalizado) é gravado como BLOB float32.
    """
    n_paginas = sum(len(paginas) for _arq_id, paginas in fontes)

    # chunka cada fonte mantendo o arquivo_id de origem
    registros: list[dict] = []
    textos: list[str] = []
    for arquivo_id, paginas in fontes:
        for ch in _chunkar(paginas):
            ch["arquivo_id"] = arquivo_id
            registros.append(ch)
            textos.append("passage: " + ch["texto"])

    con.execute("DELETE FROM rag_chunks WHERE pregao_id=?", (pregao_id,))

    if registros:
        vetores = embed(textos)
        for ch, vetor in zip(registros, vetores):
            con.execute(
                """INSERT INTO rag_chunks
                     (pregao_id, arquivo_id, pagina, ordem, offset_inicio,
                      offset_fim, texto, vetor)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (pregao_id, ch["arquivo_id"], ch["pagina"], ch["ordem"],
                 ch["offset_inicio"], ch["offset_fim"], ch["texto"],
                 _vetor_para_blob(vetor)),
            )

    con.execute(
        """INSERT OR REPLACE INTO rag_status
             (pregao_id, ingerido_em, n_chunks, n_paginas, modelo)
           VALUES (?, datetime('now'), ?, ?, ?)""",
        (pregao_id, len(registros), n_paginas, settings.MATCH_MODELO),
    )
    con.commit()
    return {"n_chunks": len(registros), "n_paginas": n_paginas}


def ingerir(con: sqlite3.Connection, pregao_id: int,
            cliente: pncp.ClientePNCP | None = None,
            embed=matching.embed_padrao) -> dict:
    """Parte de IO: obtém os PDFs do edital e indexa seus chunks.

    Usa os PDFs Edital/TR já baixados (tabela arquivos); se não houver nenhum,
    baixa via PNCP (cliente.arquivos + sincronizacao._baixar_arquivos). Sem PDF
    → {n_chunks:0, n_paginas:0, motivo:"sem_arquivos"} (honesto, princípio 1).
    """
    pregao = con.execute(
        "SELECT * FROM pregoes WHERE id=?", (pregao_id,)
    ).fetchone()
    if pregao is None:
        raise ValueError(f"Pregão {pregao_id} não existe")

    cliente = cliente or pncp.cliente()

    # PDFs Edital/TR já baixados (caminho_local existente)
    baixados = con.execute(
        """SELECT caminho_local FROM arquivos
           WHERE pregao_id=? AND caminho_local IS NOT NULL
             AND lower(caminho_local) LIKE '%.pdf'
             AND (lower(tipo) LIKE '%edital%' OR lower(tipo) LIKE '%termo%')""",
        (pregao_id,),
    ).fetchall()
    pdfs = [r["caminho_local"] for r in baixados]

    if not pdfs:
        # baixa pela API (registra na tabela arquivos e devolve os PDFs Edital/TR)
        arquivos = cliente.arquivos(pregao["cnpj"], pregao["ano"], pregao["seq"])
        caminhos = sincronizacao._baixar_arquivos(con, pregao, arquivos, cliente)
        pdfs = [str(c) for c in caminhos]

    if not pdfs:
        return {"n_chunks": 0, "n_paginas": 0, "motivo": "sem_arquivos"}

    fontes: list[tuple[int | None, list[str]]] = []
    for caminho in pdfs:
        arq = con.execute(
            "SELECT id FROM arquivos WHERE pregao_id=? AND caminho_local=?",
            (pregao_id, caminho),
        ).fetchone()
        arquivo_id = arq["id"] if arq else None
        paginas = extracao.extrair_paginas(caminho)
        fontes.append((arquivo_id, paginas))

    return indexar_chunks(con, pregao_id, fontes, embed=embed)


def _carregar_matriz(con: sqlite3.Connection, pregao_id: int):
    """Carrega (rows, matriz) dos chunks de um pregão.

    `rows` = lista de dicts (id, arquivo_id, pagina, offset_inicio, offset_fim,
    texto); `matriz` = np.ndarray (n_chunks × dim) reconstruída dos BLOBs
    float32. Sem chunks → ([], None).
    """
    linhas = con.execute(
        """SELECT id, arquivo_id, pagina, offset_inicio, offset_fim, texto, vetor
           FROM rag_chunks WHERE pregao_id=? ORDER BY id""",
        (pregao_id,),
    ).fetchall()
    if not linhas:
        return [], None
    rows = []
    vetores = []
    for ln in linhas:
        rows.append({
            "id": ln["id"], "arquivo_id": ln["arquivo_id"],
            "pagina": ln["pagina"], "offset_inicio": ln["offset_inicio"],
            "offset_fim": ln["offset_fim"], "texto": ln["texto"],
        })
        vetores.append(np.frombuffer(ln["vetor"], dtype=np.float32))
    matriz = np.vstack(vetores)
    return rows, matriz


def perguntar(con: sqlite3.Connection, pregao_id: int, pergunta: str,
              k: int | None = None, embed=matching.embed_padrao,
              threshold: float | None = None, sintetizar: bool = False,
              sintetizador=None) -> dict:
    """Recuperação extrativa (Fase 1): devolve os trechos do edital mais
    próximos da pergunta (cosseno ≥ threshold). Os trechos são a resposta.

    Sem chunks → disponivel=False, motivo "nao_indexado".
    max(score) < threshold → disponivel=False, motivo "nao_encontrado".

    `sintetizar=True` (opt-in, Fase 2): quando há trechos E
    settings.RAG_SINTESE_MODO != "off", anexa uma síntese em prosa em
    `resposta["sintese"]` (gate de citação duro em rag_sintese). Os TRECHOS
    NUNCA são removidos — a prosa nunca substitui a fonte (princípio 1/4).
    A síntese é injetável p/ teste via `sintetizador` (default usa
    rag_sintese.sintetizar) — assim os testes nunca chamam o CLI real.
    """
    k = k or settings.RAG_TOP_K
    threshold = threshold if threshold is not None else settings.RAG_THRESHOLD

    rows, matriz = _carregar_matriz(con, pregao_id)
    if matriz is None:
        return {"disponivel": False, "motivo": "nao_indexado", "trechos": []}

    q = np.asarray(embed(["query: " + pergunta])[0], dtype=np.float32)
    scores = matriz @ q  # cosseno (vetores e5 já normalizados)

    ordem = np.argsort(scores)[::-1][:k]
    if len(ordem) == 0 or float(scores[ordem[0]]) < threshold:
        return {"disponivel": False, "motivo": "nao_encontrado", "trechos": []}

    # títulos dos arquivos (JOIN arquivos.titulo) — um lookup por arquivo_id
    titulos: dict[int, str] = {}
    arq_ids = {rows[i]["arquivo_id"] for i in ordem if rows[i]["arquivo_id"] is not None}
    for aid in arq_ids:
        a = con.execute(
            "SELECT titulo FROM arquivos WHERE id=?", (aid,)
        ).fetchone()
        if a:
            titulos[aid] = a["titulo"]

    trechos = []
    for i in ordem:
        score = float(scores[i])
        if score < threshold:
            break  # top-k ordenado; abaixo do threshold não entra
        r = rows[i]
        trechos.append({
            "texto": r["texto"],
            "arquivo_id": r["arquivo_id"],
            "arquivo_titulo": titulos.get(r["arquivo_id"]),
            "pagina": r["pagina"],
            "offset_inicio": r["offset_inicio"],
            "offset_fim": r["offset_fim"],
            "score": round(score, 4),
        })

    if not trechos:
        return {"disponivel": False, "motivo": "nao_encontrado", "trechos": []}

    resposta = {
        "disponivel": True,
        "pergunta": pergunta,
        "trechos": trechos,
        "fonte": "documentos do edital (PNCP)",
    }

    # Fase 2 (opt-in): síntese em prosa SOBRE os trechos, sem removê-los.
    if sintetizar and settings.RAG_SINTESE_MODO != "off":
        sint = sintetizador or _sintetizar_padrao
        resposta["sintese"] = sint(pergunta, trechos)

    return resposta


def _sintetizar_padrao(pergunta: str, trechos: list[dict]) -> dict:
    """Default de perguntar(): chama rag_sintese.sintetizar (import local p/
    evitar ciclo). Substituível por um fake nos testes via `sintetizador`."""
    from . import rag_sintese
    return rag_sintese.sintetizar(pergunta, trechos)
