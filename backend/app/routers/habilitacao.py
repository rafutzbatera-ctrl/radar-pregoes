import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_db

router = APIRouter(prefix="/habilitacao", tags=["habilitacao"])


class HabilPatch(BaseModel):
    status_usuario: Literal["ok", "pendente", "nao_tenho"]


@router.patch("/{habil_id}")
def atualizar(habil_id: int, corpo: HabilPatch,
              con: sqlite3.Connection = Depends(get_db)):
    cur = con.execute(
        "UPDATE habilitacao SET status_usuario=? WHERE id=?",
        (corpo.status_usuario, habil_id),
    )
    if not cur.rowcount:
        raise HTTPException(404, "Requisito não encontrado")
    con.commit()
    return dict(con.execute(
        "SELECT * FROM habilitacao WHERE id=?", (habil_id,)
    ).fetchone())
