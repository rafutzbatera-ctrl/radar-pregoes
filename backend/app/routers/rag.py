"""Endpoints do RAG leve extrativo (Fase 1) — Q&A sobre os documentos de UM
edital por vez (CLAUDE.md princípios 1 e 2).

Ingestão sob demanda (endpoint explícito, decisão do dono): a UI dispara o
/indexar quando o usuário quer perguntar; /status diz se já foi indexado;
/perguntar devolve os trechos verbatim do edital (nunca síntese/LLM). Tudo
isolado por pregao_id.
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_db
from ..services import rag

router = APIRouter(prefix="/pregoes", tags=["rag"])


class PerguntaRAG(BaseModel):
    pergunta: str
    k: int | None = None


@router.post("/{pregao_id}/rag/indexar")
def indexar(pregao_id: int, con: sqlite3.Connection = Depends(get_db)):
    """Ingere os PDFs do edital e indexa os chunks. 404 se o pregão não existe.

    Sem arquivos → {n_chunks:0, n_paginas:0, motivo:"sem_arquivos"} (honesto).
    """
    try:
        return rag.ingerir(con, pregao_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.get("/{pregao_id}/rag/status")
def status(pregao_id: int, con: sqlite3.Connection = Depends(get_db)):
    """Status de ingestão do pregão. Não indexado → {indexado: False}."""
    if con.execute("SELECT 1 FROM pregoes WHERE id=?", (pregao_id,)).fetchone() is None:
        raise HTTPException(404, "Pregão não encontrado")
    st = con.execute(
        "SELECT ingerido_em, n_chunks, n_paginas, modelo FROM rag_status WHERE pregao_id=?",
        (pregao_id,),
    ).fetchone()
    if st is None:
        return {"indexado": False}
    return {"indexado": True, **dict(st)}


@router.post("/{pregao_id}/rag/perguntar")
def perguntar(pregao_id: int, corpo: PerguntaRAG,
              con: sqlite3.Connection = Depends(get_db)):
    """Recuperação extrativa: trechos do edital mais próximos da pergunta.

    404 se o pregão não existe; 422 se a pergunta for vazia. Os trechos SÃO a
    resposta (verbatim, com página + offsets) — nunca há síntese/LLM.
    """
    if con.execute("SELECT 1 FROM pregoes WHERE id=?", (pregao_id,)).fetchone() is None:
        raise HTTPException(404, "Pregão não encontrado")
    if not corpo.pergunta or not corpo.pergunta.strip():
        raise HTTPException(422, "pergunta vazia")
    return rag.perguntar(con, pregao_id, corpo.pergunta, k=corpo.k)
