import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_db

router = APIRouter(prefix="/config", tags=["config"])

CHAVES_VALIDAS = {
    "regime_tributario",       # simples | presumido
    "uf_origem",
    "margem_alvo",             # 0–0.95 — guia da simulação por item (P3)
    "veredito_vale_margem_min", "veredito_vale_cobertura_min",
    "veredito_vale_lucro_min", "veredito_nao_vale_margem_max",
    "veredito_nao_vale_lucro_max",
}


class ConfigPatch(BaseModel):
    regime_tributario: str | None = None
    uf_origem: str | None = None


@router.get("")
def ler(con: sqlite3.Connection = Depends(get_db)):
    return {ln["chave"]: ln["valor"]
            for ln in con.execute("SELECT chave, valor FROM config")}


@router.patch("")
def atualizar(corpo: dict, con: sqlite3.Connection = Depends(get_db)):
    if not corpo:
        raise HTTPException(400, "Nada para atualizar")
    for chave, valor in corpo.items():
        if chave not in CHAVES_VALIDAS:
            raise HTTPException(400, f"Chave inválida: {chave}")
        if chave == "regime_tributario" and valor not in ("simples", "presumido"):
            raise HTTPException(400, "regime_tributario deve ser simples|presumido")
        if chave == "margem_alvo":
            # aceita string numérica; faixa 0–0.95 (422 fora)
            try:
                m = float(valor)
            except (ValueError, TypeError):
                raise HTTPException(422, "margem_alvo deve ser número entre 0 e 0.95")
            if not (0 <= m <= 0.95):
                raise HTTPException(422, "margem_alvo deve estar entre 0 e 0.95")
        con.execute(
            "INSERT INTO config (chave, valor) VALUES (?,?) "
            "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
            (chave, str(valor)),
        )
    con.commit()
    return ler(con)
