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
  BLOB float32; popula tb. o índice léxico FTS5 (rag_fts); idempotente por pregão.
- ingerir: parte de IO — obtém os PDFs (já baixados ou via PNCP), extrai páginas
  e chama indexar_chunks.
- perguntar: recuperação HÍBRIDA — cosseno e5 (semântico) + BM25 via SQLite
  FTS5 (léxico) fundidos por Reciprocal Rank Fusion (RRF). FTS5 é nativo do
  SQLite (zero dependência nova); sem ele, degrada para só-vetor. Gate de
  honestidade preserva o "não encontrado" (cosseno ≥ threshold OU match léxico).

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


# ----------------------------- FTS5 (léxica BM25) -----------------------------
# A recuperação híbrida soma o ranking SEMÂNTICO (cosseno e5) com o LÉXICO (BM25
# via SQLite FTS5) por Reciprocal Rank Fusion. O FTS5 é NATIVO do SQLite (zero
# dependência nova), mas pode faltar em builds exóticos — por isso TUDO aqui é
# tolerante: se a tabela virtual não puder ser criada/consultada, o RAG degrada
# graciosamente para só-vetor (comportamento idêntico ao da Fase 1).

# tokenize unicode61 remove_diacritics 2 → casa "prazo"/"prázo" (sem acento) e
# quebra por não-alfanumérico, o que combina com a sanitização da pergunta.
_FTS_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS rag_fts USING fts5("
    "  texto, chunk_id UNINDEXED, pregao_id UNINDEXED,"
    "  tokenize='unicode61 remove_diacritics 2')"
)

# RRF: ranking fundido = Σ 1/(_RRF_K + rank_naquela_lista). k=60 é o valor
# canônico do paper (Cormack et al.) — amortece o peso das primeiras posições.
_RRF_K = 60
# candidatos por lista antes da fusão (amplo p/ a fusão ter material; o top-k
# final é settings.RAG_TOP_K).
_CAND_N = 20

# extrai termos alfanuméricos (inclui acentuados) da pergunta p/ o MATCH.
_RE_TERMO = re.compile(r"[0-9A-Za-zÀ-ÿ]+", re.UNICODE)

# stopwords PT-BR (palavras de função). Sem elas o MATCH só casa em termos de
# CONTEÚDO — crucial para a HONESTIDADE do gate: uma pergunta fora do tema
# ("qual a cor do papel timbrado?") não pode "casar" o FTS só porque compartilha
# "a"/"do"/"qual" com o edital (match espúrio que reabriria a porta a respostas
# inventadas). Lista enxuta e estática (determinística p/ teste; sem dependência
# externa). Termos de 1 letra também caem (filtro de tamanho), então não preciso
# listar "a"/"o"/"e".
_STOPWORDS = frozenset({
    "qual", "quais", "quanto", "quantos", "quanta", "quantas", "quando",
    "onde", "como", "porque", "por", "que", "qye", "para", "pra", "com",
    "sem", "sobre", "the", "de", "do", "da", "dos", "das", "no", "na", "nos",
    "nas", "em", "um", "uma", "uns", "umas", "ao", "aos", "se", "ou", "mas",
    "os", "as", "ser", "está", "esta", "este", "isso", "essa", "esse", "ela",
    "ele", "eu", "me", "meu", "minha", "qual", "tem", "ter", "há", "foi",
})


def _e_termo_util(termo: str) -> bool:
    """True se o termo deve entrar no MATCH: não é stopword e tem ≥ 2 chars
    (termos de 1 letra são ruído léxico — pegam tudo, não discriminam)."""
    return len(termo) >= 2 and termo.lower() not in _STOPWORDS


# hook de teste para simular ambiente SEM FTS5 (degradação para só-vetor) sem
# precisar de um build do SQLite sem o módulo. False em produção.
_FTS_FORCE_OFF = False


def _fts_disponivel(con: sqlite3.Connection) -> bool:
    """Garante (idempotente) a tabela virtual rag_fts e diz se o FTS5 existe.

    Cria a tabela sob demanda — a migração v11 é só um marcador (ver db.py),
    pois `CREATE VIRTUAL TABLE` num build sem FTS5 quebraria `db.abrir()`. O DDL
    usa IF NOT EXISTS (idempotente e barato), então é seguro chamar a cada
    request — não há cache (sqlite3.Connection desta build não aceita atributos
    nem weakref; um cache por id() corromperia em reuso de id após GC da
    conexão). Em qualquer erro (build sem FTS5) loga e devolve False: o RAG
    segue só-vetor. _FTS_FORCE_OFF (teste) força a degradação.
    """
    if _FTS_FORCE_OFF:
        return False
    try:
        con.execute(_FTS_DDL)
        return True
    except sqlite3.Error as exc:
        log.warning("FTS5 indisponível — RAG degrada para só-vetor: %s", exc)
        return False


def _sanitizar_match(pergunta: str) -> str:
    """Monta a expressão MATCH do FTS5 a partir da pergunta do usuário.

    Extrai os termos alfanuméricos de CONTEÚDO (descarta stopwords e termos de 1
    letra — ver _e_termo_util), envolve cada um em aspas duplas (escapando aspas
    internas — sintaxe de string FTS5: "" dentro de "...") e junta com OR. OR
    (não AND) para NÃO exigir todos os termos — recall amplo; quem ordena é o
    BM25 (rank) + o RRF. Sem termos úteis → "" (o chamador trata como sem-léxico,
    e o gate cai só no critério semântico — preserva a honestidade do RAG).
    """
    termos = [t for t in _RE_TERMO.findall(pergunta or "") if _e_termo_util(t)]
    if not termos:
        return ""
    return " OR ".join('"' + t.replace('"', '""') + '"' for t in termos)


def _indexar_fts(con: sqlite3.Connection, pregao_id: int,
                 linhas: list[tuple[int, str]]) -> None:
    """Popula o FTS do pregão (idempotente). `linhas` = [(chunk_id, texto)].

    Apaga as linhas do pregão antes de inserir (espelha o DELETE de rag_chunks).
    Tolerante: se o FTS estiver indisponível, não faz nada (degrada p/ só-vetor).
    """
    if not _fts_disponivel(con):
        return
    try:
        con.execute("DELETE FROM rag_fts WHERE pregao_id=?", (pregao_id,))
        con.executemany(
            "INSERT INTO rag_fts(texto, chunk_id, pregao_id) VALUES (?,?,?)",
            [(texto, chunk_id, pregao_id) for chunk_id, texto in linhas],
        )
    except sqlite3.Error as exc:
        log.warning("Falha ao popular FTS do pregão %s (segue só-vetor): %s",
                    pregao_id, exc)


def _buscar_fts(con: sqlite3.Connection, pregao_id: int,
                pergunta: str, limite: int = _CAND_N) -> list[int]:
    """Ranking léxico (BM25): lista de chunk_id ordenada por relevância FTS5.

    Vazia se o FTS estiver indisponível, a pergunta não tiver termos, ou nada
    casar. O `rank` do FTS5 já vem ordenável (menor = mais relevante); o ORDER
    BY rank devolve do melhor ao pior — a POSIÇÃO na lista é o rank usado no RRF.
    """
    if not _fts_disponivel(con):
        return []
    match = _sanitizar_match(pergunta)
    if not match:
        return []
    try:
        linhas = con.execute(
            "SELECT chunk_id FROM rag_fts "
            "WHERE rag_fts MATCH ? AND pregao_id=? ORDER BY rank LIMIT ?",
            (match, pregao_id, limite),
        ).fetchall()
    except sqlite3.Error as exc:
        log.warning("Falha na busca FTS do pregão %s (segue só-vetor): %s",
                    pregao_id, exc)
        return []
    return [ln[0] for ln in linhas]


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

    fts_linhas: list[tuple[int, str]] = []  # (chunk_id, texto) p/ popular o FTS
    if registros:
        vetores = embed(textos)
        for ch, vetor in zip(registros, vetores):
            cur = con.execute(
                """INSERT INTO rag_chunks
                     (pregao_id, arquivo_id, pagina, ordem, offset_inicio,
                      offset_fim, texto, vetor)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (pregao_id, ch["arquivo_id"], ch["pagina"], ch["ordem"],
                 ch["offset_inicio"], ch["offset_fim"], ch["texto"],
                 _vetor_para_blob(vetor)),
            )
            fts_linhas.append((cur.lastrowid, ch["texto"]))

    # popular o índice léxico (BM25) — idempotente (apaga as linhas do pregão
    # antes); se o FTS5 estiver indisponível, pula silenciosamente (só-vetor).
    _indexar_fts(con, pregao_id, fts_linhas)

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
    """Recuperação extrativa HÍBRIDA: devolve os trechos do edital mais
    relevantes para a pergunta. Os trechos SÃO a resposta (verbatim).

    Recuperação = fusão de dois rankings por Reciprocal Rank Fusion (RRF):
      - SEMÂNTICO: cosseno e5 de TODOS os chunks; top _CAND_N candidatos.
      - LÉXICO (BM25): SQLite FTS5 sobre os termos da pergunta; top _CAND_N.
    score_rrf(c) = Σ 1/(_RRF_K + rank_c). Ordena por RRF desc e pega top-k. O
    FTS5 pega o match léxico EXATO que o e5-small às vezes deixa fora do topo
    (ex.: "prazo de entrega"); o e5 pega a semântica. Sem FTS5 (build sem o
    módulo) → degrada para só-vetor, idêntico à Fase 1.

    GATE de honestidade (não regride): um trecho só entra se tiver SINAL real —
    cosseno ≥ threshold OU match léxico FTS para a pergunta. Pergunta fora do
    tema não casa o FTS nem tem cosseno alto → nao_encontrado (princípio 1).

    Sem chunks → disponivel=False, motivo "nao_indexado".
    Nenhum trecho com sinal → disponivel=False, motivo "nao_encontrado".
    Cada trecho mantém o shape da Fase 1 (texto/arquivo_id/arquivo_titulo/
    pagina/offsets/score=cosseno) e ganha `fonte_rank` ("vetor"|"lexico"|
    "ambos") só para transparência — o frontend não quebra.

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
    # Modelo de embedding trocado (ou upgrade da lib) sem reindexar: os vetores
    # gravados têm a dimensão antiga e `matriz @ q` estouraria ValueError → 500
    # cru. Devolve gracioso (padrão honesto: nao_indexado/nao_encontrado) pedindo
    # reindexação, em vez de quebrar a tela.
    if matriz.shape[1] != q.shape[0]:
        return {"disponivel": False, "motivo": "reindexar", "trechos": []}
    scores = matriz @ q  # cosseno (vetores e5 já normalizados)

    # mapeia chunk_id (rag_chunks.id) → posição na matriz/rows, p/ casar o
    # ranking léxico (que vem por chunk_id) com os índices da matriz.
    id_para_idx = {r["id"]: i for i, r in enumerate(rows)}

    # --- ranking VETORIAL: top _CAND_N candidatos por cosseno desc ---
    rank_vetor: dict[int, int] = {}  # idx_matriz → rank (0-based) na lista vetor
    ordem_vetor = np.argsort(scores)[::-1][:_CAND_N]
    for pos, idx in enumerate(ordem_vetor):
        rank_vetor[int(idx)] = pos

    # --- ranking LÉXICO (BM25/FTS5): top _CAND_N chunk_id por relevância ---
    rank_lexico: dict[int, int] = {}  # idx_matriz → rank (0-based) na lista FTS
    for pos, chunk_id in enumerate(_buscar_fts(con, pregao_id, pergunta, _CAND_N)):
        idx = id_para_idx.get(chunk_id)
        if idx is not None:  # ignora chunk órfão (FTS dessincronizado)
            rank_lexico[idx] = pos

    # --- Reciprocal Rank Fusion (RRF) sobre a UNIÃO dos dois rankings ---
    # score_rrf(c) = Σ 1/(_RRF_K + rank_c_naquela_lista). Quem aparece nas duas
    # listas soma duas parcelas → sobe. fonte_rank registra de onde o chunk veio.
    candidatos = set(rank_vetor) | set(rank_lexico)
    fundidos: list[tuple[float, int]] = []  # (score_rrf, idx_matriz)
    for idx in candidatos:
        rrf = 0.0
        if idx in rank_vetor:
            rrf += 1.0 / (_RRF_K + rank_vetor[idx])
        if idx in rank_lexico:
            rrf += 1.0 / (_RRF_K + rank_lexico[idx])
        fundidos.append((rrf, idx))
    # ordena por RRF desc; desempate determinístico pelo cosseno (idx estável)
    fundidos.sort(key=lambda t: (t[0], float(scores[t[1]])), reverse=True)
    topo = fundidos[:k]

    # --- GATE de honestidade (não pode regredir): só responde se houver SINAL
    # real. disponivel=True se algum chunk do topo tiver cosseno ≥ threshold OU
    # vier do ranking léxico (match BM25 = termo exato da pergunta no chunk). A
    # pergunta fora do tema não casa o FTS nem tem cosseno alto → nao_encontrado.
    def _tem_sinal(idx: int) -> bool:
        return float(scores[idx]) >= threshold or idx in rank_lexico

    if not topo or not any(_tem_sinal(idx) for _rrf, idx in topo):
        return {"disponivel": False, "motivo": "nao_encontrado", "trechos": []}

    # títulos dos arquivos (JOIN arquivos.titulo) — um lookup por arquivo_id
    titulos: dict[int, str] = {}
    arq_ids = {rows[idx]["arquivo_id"] for _r, idx in topo
               if rows[idx]["arquivo_id"] is not None}
    for aid in arq_ids:
        a = con.execute(
            "SELECT titulo FROM arquivos WHERE id=?", (aid,)
        ).fetchone()
        if a:
            titulos[aid] = a["titulo"]

    trechos = []
    for _rrf, idx in topo:
        # só entram chunks com SINAL real (cosseno alto OU match léxico) — um
        # candidato que só veio "de carona" no top-k sem sinal não vira resposta
        # (mantém a honestidade do nao_encontrado por trecho).
        if not _tem_sinal(idx):
            continue
        score = float(scores[idx])
        no_vetor = idx in rank_vetor
        no_lexico = idx in rank_lexico
        fonte = ("ambos" if no_vetor and no_lexico
                 else "lexico" if no_lexico else "vetor")
        r = rows[idx]
        trechos.append({
            "texto": r["texto"],
            "arquivo_id": r["arquivo_id"],
            "arquivo_titulo": titulos.get(r["arquivo_id"]),
            "pagina": r["pagina"],
            "offset_inicio": r["offset_inicio"],
            "offset_fim": r["offset_fim"],
            "score": round(score, 4),  # cosseno (como na Fase 1)
            "fonte_rank": fonte,       # "vetor"|"lexico"|"ambos" (transparência)
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
