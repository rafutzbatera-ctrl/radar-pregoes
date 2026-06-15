"""Matching itens ↔ catálogo via embeddings locais (CLAUDE.md §3 e §6.2).

Modelo intfloat/multilingual-e5-small com prefixos "query:" (item do edital)
e "passage:" (produto do catálogo); similaridade de cosseno; threshold 0.90
(conservador, P3) para SUGERIR. O usuário sempre confirma na UI antes de o
item entrar na conta (human-in-the-loop) — aqui nunca se grava
match_confirmado=1. Produtos já RECUSADOS pelo usuário para um item não voltam
como sugestão (recusa memorizada em itens_pregao.produtos_recusados).
"""
import json
import logging
import sqlite3
import threading

from .. import settings

log = logging.getLogger("radar.matching")


def _recusados(valor) -> set[int]:
    """Parse tolerante de produtos_recusados (NULL/JSON inválido → vazio)."""
    if not valor:
        return set()
    try:
        dados = json.loads(valor)
    except (ValueError, TypeError):
        return set()
    if not isinstance(dados, list):
        return set()
    return {int(x) for x in dados if isinstance(x, (int, float))}

_modelo = None
_lock = threading.Lock()


def _carregar_modelo():
    """Carrega o e5 uma única vez (download na primeira execução)."""
    global _modelo
    with _lock:
        if _modelo is None:
            from sentence_transformers import SentenceTransformer
            log.info("Carregando modelo %s…", settings.MATCH_MODELO)
            _modelo = SentenceTransformer(settings.MATCH_MODELO)
    return _modelo


def embed_padrao(textos: list[str]):
    """Embeddings reais, normalizados (cosseno = produto interno)."""
    modelo = _carregar_modelo()
    return modelo.encode(textos, normalize_embeddings=True)


def sugerir_matches(con: sqlite3.Connection, pregao_id: int,
                    embed=embed_padrao, threshold: float | None = None) -> int:
    """Sugere o melhor produto para cada item ainda sem decisão do usuário.

    `embed` é injetável para teste; produção usa o e5 real.
    Retorna quantas sugestões foram gravadas.
    """
    threshold = threshold if threshold is not None else settings.MATCH_THRESHOLD

    produtos = con.execute(
        "SELECT id, nome FROM catalogo_produtos WHERE ativo=1"
    ).fetchall()
    # itens sem produto e sem confirmação (não sobrescreve decisão do usuário)
    itens = con.execute(
        """SELECT id, descricao, produtos_recusados FROM itens_pregao
           WHERE pregao_id=? AND produto_id IS NULL AND match_confirmado=0""",
        (pregao_id,),
    ).fetchall()
    if not produtos or not itens:
        return 0

    import numpy as np

    # embed pode devolver listas Python (testes) ou np.ndarray (e5 real) →
    # asarray normaliza para a matmul. Linhas = itens, colunas = produtos.
    vet_itens = np.asarray(embed(["query: " + (i["descricao"] or "") for i in itens]),
                           dtype=float)
    vet_prod = np.asarray(embed(["passage: " + p["nome"] for p in produtos]),
                          dtype=float)
    # matriz de scores (n_itens × n_produtos) — mesmo cosseno do _dot, em bloco
    scores = vet_itens @ vet_prod.T
    prod_ids = [p["id"] for p in produtos]

    sugeridos = 0
    for i, item in enumerate(itens):
        recusados = _recusados(item["produtos_recusados"])  # recusa memorizada
        linha = scores[i].copy()
        # mascara produtos recusados ANTES do argmax (não re-sugere recusado);
        # -inf garante que nunca vencem mesmo se todos os demais forem baixos.
        for j, pid in enumerate(prod_ids):
            if pid in recusados:
                linha[j] = -np.inf
        j = int(np.argmax(linha))
        melhor_score = float(linha[j])
        # all-refused (ou nenhuma coluna válida) → -inf, abaixo do threshold;
        # também respeita o piso. Idêntico ao loop antigo (melhor_prod=None ou
        # melhor_score<threshold → nada gravado).
        if melhor_score >= threshold:
            con.execute(
                """UPDATE itens_pregao
                   SET produto_id=?, match_score=?, match_confirmado=0
                   WHERE id=?""",
                (prod_ids[j], round(melhor_score, 4), item["id"]),
            )
            sugeridos += 1
    con.commit()
    return sugeridos


def _dot(a, b) -> float:
    try:  # numpy arrays
        return float(a @ b)
    except TypeError:  # listas puras (testes)
        return sum(x * y for x, y in zip(a, b))
