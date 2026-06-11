import json
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_db

router = APIRouter(prefix="/habilitacao", tags=["habilitacao"])

_CHECKLIST_BASE = Path(__file__).resolve().parent.parent / "dados" / "checklist_base.json"

AVISO_BASE = ("Base geral (Lei 14.133 e editais reais) — NÃO foi extraída deste "
              "edital. Confirme no PDF oficial antes de usar.")


@lru_cache(maxsize=1)
def _carregar_base() -> list[dict]:
    return json.loads(_CHECKLIST_BASE.read_text(encoding="utf-8"))


class HabilPatch(BaseModel):
    status_usuario: Literal["ok", "pendente", "nao_tenho"]


@router.get("/base")
def base():
    """Checklist de referência geral — o que editais costumam pedir.

    PRINCÍPIO 1 (CLAUDE.md): NÃO é extração de edital específico. Referência
    geral, com fonte declarada e aviso fixo.
    """
    return {"itens": _carregar_base(), "aviso": AVISO_BASE}


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
