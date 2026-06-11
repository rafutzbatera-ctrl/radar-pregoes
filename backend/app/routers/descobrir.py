"""PNCP ao vivo — explorar a busca do PNCP sem persistir (CLAUDE.md §4.1).

O usuário pode navegar os ~37 mil editais nacionais ao vivo (a API de busca
aceita consulta sem termo) e importar para o radar local sob demanda. Tudo
passa pelo cliente PNCP compartilhado (1 req/s + cache 6h, princípio 6).
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .. import pncp
from ..deps import get_db
from ..services import descoberta
from .pregoes import _resumo_pregao

router = APIRouter(prefix="/descobrir", tags=["descobrir"])

TAMANHO = 50


def _adaptar(hit: dict, ja_no_radar: bool, pregao_id: int | None) -> dict:
    """Hit cru da busca do PNCP → cartão da UI (+ hit cru p/ reenviar no importar)."""
    return {
        "numero_controle": hit.get("numero_controle_pncp"),
        "titulo": hit.get("title"),
        "descricao": hit.get("description"),
        "orgao": hit.get("orgao_nome"),
        "municipio": hit.get("municipio_nome"),
        "uf": hit.get("uf"),
        "modalidade": hit.get("modalidade_licitacao_nome"),
        "situacao": hit.get("situacao_nome"),
        "data_fim_vigencia": hit.get("data_fim_vigencia"),
        "valor_global": hit.get("valor_global"),
        "cnpj": hit.get("orgao_cnpj"),
        "ano": hit.get("ano"),
        "seq": hit.get("numero_sequencial"),
        "ja_no_radar": ja_no_radar,
        "pregao_id": pregao_id,
        # JSON cru: o front guarda e devolve no /descobrir/importar (persistir_hit
        # espera os campos crus title/orgao_cnpj/ano/numero_sequencial…)
        "hit": hit,
    }


@router.get("")
def descobrir(
    q: str = "",
    ufs: str = "",
    status: str = "recebendo_proposta",
    pagina: int = Query(1, ge=1),
    con: sqlite3.Connection = Depends(get_db),
):
    """Consulta AO VIVO a busca do PNCP, sem persistir nada.

    `q` vazio = total nacional (não envia o param). `status` vazio = todos.
    """
    try:
        resp = pncp.cliente().buscar(
            q=q, ufs=ufs, status=status, pagina=pagina, tamanho=TAMANHO,
        )
    except RuntimeError as exc:  # PNCP fora do ar após os retries
        raise HTTPException(503, str(exc))

    itens = []
    for hit in resp.get("items", []):
        nc = hit.get("numero_controle_pncp")
        local = con.execute(
            "SELECT id FROM pregoes WHERE numero_controle=?", (nc,)
        ).fetchone() if nc else None
        itens.append(_adaptar(hit, local is not None, local["id"] if local else None))

    return {
        "total": resp.get("total", 0),
        "pagina": pagina,
        "tamanho": TAMANHO,
        "itens": itens,
    }


class ImportarIn(BaseModel):
    numero_controle: str
    hit: dict  # JSON cru do item da busca (o front guarda e devolve)


@router.post("/importar")
def importar(corpo: ImportarIn, con: sqlite3.Connection = Depends(get_db)):
    """Importa um pregão da busca ao vivo para o radar local (idempotente).

    Reaproveita persistir_hit (busca_id=None: pregão sem busca salva de origem).
    Retorna o pregão local no mesmo shape de GET /pregoes/{id}.
    """
    descoberta.persistir_hit(con, corpo.hit, busca_id=None)
    con.commit()
    p = con.execute(
        "SELECT * FROM pregoes WHERE numero_controle=?", (corpo.numero_controle,)
    ).fetchone()
    if p is None:
        # persistir_hit ignora hit sem numero_controle_pncp — nada a importar
        raise HTTPException(422, "Hit sem número de controle do PNCP — nada a importar")
    return _resumo_pregao(con, p)
