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


class ItemPatchIn(BaseModel):
    # custo_manual (P3): null limpa o override (volta ao catálogo se houver
    # match). lance_previsto (P4): preço esperado de disputa por item; null
    # limpa. Ambos ge=0 → 422 se negativo. exclude_unset no handler distingue
    # "não enviado" de "enviado como null" — só toca os campos presentes.
    custo_manual: float | None = Field(default=None, ge=0)
    lance_previsto: float | None = Field(default=None, ge=0)


def _retorno(con: sqlite3.Connection, item_id: int, pregao_id: int) -> dict:
    agregados = analise.analisar_pregao(con, pregao_id)
    linha = con.execute(
        "SELECT * FROM itens_pregao WHERE id=?", (item_id,)
    ).fetchone()
    # guarda contra None: se o item sumiu entre o UPDATE e este SELECT (janela
    # mínima, single-user), dict(None) estouraria TypeError -> 500. Devolve 404.
    if linha is None:
        raise HTTPException(404, "Item não encontrado")
    return {"item": dict(linha), "pregao": agregados}


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
def definir_item(item_id: int, corpo: ItemPatchIn,
                 con: sqlite3.Connection = Depends(get_db)):
    """Edita custo manual (P3) e/ou lance previsto (P4) do item — overrides
    locais do pregão. null em qualquer campo limpa o override (custo volta ao
    catálogo se houver match; lance volta ao deságio/teto). Só os campos
    presentes no corpo são tocados. Recalcula a análise e retorna {item,
    pregao} como o endpoint de match."""
    item = con.execute("SELECT pregao_id FROM itens_pregao WHERE id=?",
                       (item_id,)).fetchone()
    if item is None:
        raise HTTPException(404, "Item não encontrado")
    campos = corpo.model_dump(exclude_unset=True)
    if campos:
        sets = ", ".join(f"{c}=?" for c in campos)
        con.execute(f"UPDATE itens_pregao SET {sets} WHERE id=?",
                    (*campos.values(), item_id))
        con.commit()
    return _retorno(con, item_id, item["pregao_id"])
