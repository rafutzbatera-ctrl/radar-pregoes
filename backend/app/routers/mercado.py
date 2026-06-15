"""Inteligência de mercado — ETL dos resultados de pregão (Dores #8/#9).

Persiste em resultados_itens cada item HOMOLOGADO (quem venceu, por quanto,
deságio real), denormalizado para agregação. Fonte: services/resultados.py.
"""
import sqlite3

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..deps import get_db
from ..services import resultados as svc

router = APIRouter(prefix="/mercado", tags=["mercado"])


class ColetarIn(BaseModel):
    pregao_ids: list[int] | None = None


@router.post("/coletar")
def coletar(corpo: ColetarIn | None = None,
            con: sqlite3.Connection = Depends(get_db)):
    """Coleta e persiste os resultados homologados (upsert idempotente).

    Body opcional `{pregao_ids: [int]}`; sem ele, varre TODOS os pregões
    (cap defensivo). LENTO: bate no PNCP item a item por pregão — é uma
    operação manual/sob demanda, não para o caminho interativo.
    Retorna {pregoes_processados, pregoes_homologados, itens_gravados}.
    """
    pregao_ids = corpo.pregao_ids if corpo else None
    return svc.coletar_resultados(con, pregao_ids=pregao_ids)
