import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_db
from ..services import analise

router = APIRouter(prefix="/itens", tags=["itens"])


class MatchIn(BaseModel):
    produto_id: int | None    # null = recusar/limpar match
    confirmado: bool = False


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
        con.execute(
            "UPDATE itens_pregao SET produto_id=NULL, match_score=NULL, match_confirmado=0 WHERE id=?",
            (item_id,),
        )
    con.commit()
    agregados = analise.analisar_pregao(con, item["pregao_id"])
    atualizado = dict(con.execute(
        "SELECT * FROM itens_pregao WHERE id=?", (item_id,)
    ).fetchone())
    return {"item": atualizado, "pregao": agregados}
