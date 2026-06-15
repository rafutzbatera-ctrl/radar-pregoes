"""Inteligência de mercado — ETL dos resultados de pregão (Dores #8/#9).

Persiste em resultados_itens cada item HOMOLOGADO (quem venceu, por quanto,
deságio real), denormalizado para agregação. Fonte: services/resultados.py.
"""
import sqlite3

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..deps import get_db
from ..services import mercado as mkt
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


@router.get("/precos")
def precos(q: str | None = Query(default=None),
           ncm: str | None = Query(default=None),
           con: sqlite3.Connection = Depends(get_db)):
    """Histórico de preços homologados (#8) sobre `resultados_itens`.

    Params (opcionais): `q` (termo, casa por palavras na descrição) e `ncm`
    (exato). A AMOSTRA reflete só os editais JÁ COLETADOS pelo usuário (sob
    demanda via POST /mercado/coletar) — NÃO é base nacional; o campo
    `amostra` (N) vem sempre exposto, e sem dados resumo é None.
    Retorna {amostra, resumo:{preco_unit_min,preco_unit_mediana,
    preco_unit_max,desagio_medio_pct}, itens:[...]}.
    """
    return mkt.historico_precos(con, termo=q, ncm=ncm)


@router.get("/concorrentes")
def concorrentes(uf: str | None = Query(default=None),
                 q: str | None = Query(default=None),
                 con: sqlite3.Connection = Depends(get_db)):
    """Quem vence (#9) — agrega `resultados_itens` por vencedor.

    Params (opcionais): `uf` (UF do edital) e `q` (termo na descrição). A
    AMOSTRA reflete só os editais JÁ COLETADOS pelo usuário (sob demanda via
    POST /mercado/coletar) — NÃO é base nacional; `amostra_itens` (N) vem
    sempre exposto, e sem dados a lista é vazia.
    Retorna {amostra_itens, concorrentes:[{cnpj,nome,porte,n_vitorias,
    desagio_medio_pct,valor_total_homologado,n_orgaos,ufs}]}.
    """
    return mkt.concorrentes(con, uf=uf, termo=q)
