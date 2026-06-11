import json
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import get_db
from ..services import analise
from ..services.matching import _recusados

router = APIRouter(prefix="/itens", tags=["itens"])


class MatchIn(BaseModel):
    produto_id: int | None    # null = recusar/limpar match
    confirmado: bool = False


class CustoManualIn(BaseModel):
    # null limpa o override (volta ao catálogo se houver match); ge=0 → 422 negativo
    custo_manual: float | None = Field(default=None, ge=0)


def _retorno(con: sqlite3.Connection, item_id: int, pregao_id: int) -> dict:
    agregados = analise.analisar_pregao(con, pregao_id)
    atualizado = dict(con.execute(
        "SELECT * FROM itens_pregao WHERE id=?", (item_id,)
    ).fetchone())
    return {"item": atualizado, "pregao": agregados}


@router.post("/{item_id}/match")
def definir_match(item_id: int, corpo: MatchIn,
                  con: sqlite3.Connection = Depends(get_db)):
    item = con.execute("SELECT * FROM itens_pregao WHERE id=?", (item_id,)).fetchone()
    if item is None:
        raise HTTPException(404, "Item não encontrado")
    if corpo.produto_id is not None:
        produto = con.execute(
            "SELECT 1 FROM catalogo_produtos WHERE id=?", (corpo.produto_id,)
        ).fetchone()
        if produto is None:
            raise HTTPException(404, "Produto não encontrado no catálogo")
        # troca manual de produto invalida o score da sugestão automática
        score = item["match_score"] if corpo.produto_id == item["produto_id"] else None
        con.execute(
            "UPDATE itens_pregao SET produto_id=?, match_score=?, match_confirmado=? WHERE id=?",
            (corpo.produto_id, score, int(corpo.confirmado), item_id),
        )
    else:
        # recusa memorizada: o produto recusado (o atual do item, se houver) não
        # volta como sugestão (P3). Guarda a lista deduplicada em produtos_recusados.
        recusados = _recusados(item["produtos_recusados"])
        if item["produto_id"] is not None:
            recusados.add(int(item["produto_id"]))
        con.execute(
            "UPDATE itens_pregao SET produto_id=NULL, match_score=NULL, "
            "match_confirmado=0, produtos_recusados=? WHERE id=?",
            (json.dumps(sorted(recusados)) if recusados else None, item_id),
        )
    con.commit()
    return _retorno(con, item_id, item["pregao_id"])


@router.patch("/{item_id}")
def definir_custo(item_id: int, corpo: CustoManualIn,
                  con: sqlite3.Connection = Depends(get_db)):
    """Custo manual por item (override local do pregão, P3). null limpa o
    override → volta a valer o custo do catálogo se houver match confirmado.
    Recalcula a análise e retorna {item, pregao} como o endpoint de match."""
    item = con.execute("SELECT pregao_id FROM itens_pregao WHERE id=?",
                       (item_id,)).fetchone()
    if item is None:
        raise HTTPException(404, "Item não encontrado")
    con.execute("UPDATE itens_pregao SET custo_manual=? WHERE id=?",
                (corpo.custo_manual, item_id))
    con.commit()
    return _retorno(con, item_id, item["pregao_id"])
