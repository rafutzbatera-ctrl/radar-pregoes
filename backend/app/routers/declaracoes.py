"""Minutas de declarações de habilitação do licitante (RAG Fase 3).

Declaração é TEXTO-PADRÃO DO LICITANTE (Lei 14.133/CF/LC 123), não extração do
edital — o gate de citação NÃO se aplica. O render é substituição de string
pura, SEM LLM/API. Campo de empresa faltante vira lacuna visível e `completo`
fica false (princípio 1: nunca chutar). Toda minuta sai com aviso fixo.

GET /declaracoes                  -> metadados dos templates (catálogo).
GET /pregoes/{id}/declaracoes     -> sugeridas + renderizadas p/ o pregão.

Follow-up (NÃO implementado neste commit): export PDF
`GET /pregoes/{id}/declaracoes/{template_id}.pdf` reusando fpdf2/_l1 de
services/relatorio.py.
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_db
from ..services import declaracoes as svc

router = APIRouter(tags=["declaracoes"])


@router.get("/declaracoes")
def listar_templates():
    """Catálogo de templates de declaração (metadados, sem render)."""
    return {"templates": svc.metadados_templates(), "aviso": svc.AVISO}


@router.get("/pregoes/{pregao_id}/declaracoes")
def declaracoes_do_pregao(pregao_id: int,
                          con: sqlite3.Connection = Depends(get_db)):
    """Declarações sugeridas para o pregão, já renderizadas com os dados da
    empresa. 404 se o pregão não existe."""
    if con.execute("SELECT 1 FROM pregoes WHERE id=?", (pregao_id,)).fetchone() is None:
        raise HTTPException(404, "Pregão não encontrado")
    return {"declaracoes": svc.declaracoes_do_pregao(con, pregao_id),
            "aviso": svc.AVISO}
