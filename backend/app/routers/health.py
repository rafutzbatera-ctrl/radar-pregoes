"""Healthcheck simples para liveness/readiness.

GET /health faz um SELECT 1 rápido na conexão; se o banco responder, db:"ok";
se a query falhar (db indisponível/corrompido), db:"erro" — sempre 200 para o
endpoint ser usável como ping leve sem disparar alerta de HTTP.
"""
import sqlite3

from fastapi import APIRouter, Depends

from ..deps import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(con: sqlite3.Connection = Depends(get_db)):
    try:
        con.execute("SELECT 1").fetchone()
        db_ok = "ok"
    except Exception:
        db_ok = "erro"
    return {"status": "ok", "db": db_ok}
