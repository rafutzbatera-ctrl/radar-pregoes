import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_db

router = APIRouter(prefix="/catalogo", tags=["catalogo"])


class ProdutoIn(BaseModel):
    nome: str
    custo_unit: float
    codigo: str | None = None
    categoria: str | None = None
    ncm: str | None = None
    unidade: str = "UN"
    origem: str | None = None
    csosn: str | None = None
    cst: str | None = None
    aliq_icms: float | None = None
    aliq_ipi: float | None = None
    ativo: bool = True


class ProdutoPatch(BaseModel):
    nome: str | None = None
    custo_unit: float | None = None
    codigo: str | None = None
    categoria: str | None = None
    ncm: str | None = None
    unidade: str | None = None
    origem: str | None = None
    csosn: str | None = None
    cst: str | None = None
    aliq_icms: float | None = None
    aliq_ipi: float | None = None
    ativo: bool | None = None


@router.get("")
def listar(con: sqlite3.Connection = Depends(get_db)):
    return [dict(p) for p in con.execute(
        "SELECT * FROM catalogo_produtos ORDER BY nome"
    ).fetchall()]


@router.post("", status_code=201)
def criar(corpo: ProdutoIn, con: sqlite3.Connection = Depends(get_db)):
    campos = corpo.model_dump()
    campos["ativo"] = int(campos["ativo"])
    colunas = ", ".join(campos)
    marcas = ", ".join("?" for _ in campos)
    cur = con.execute(
        f"INSERT INTO catalogo_produtos ({colunas}) VALUES ({marcas})",
        list(campos.values()),
    )
    con.commit()
    return dict(con.execute(
        "SELECT * FROM catalogo_produtos WHERE id=?", (cur.lastrowid,)
    ).fetchone())


@router.patch("/{produto_id}")
def atualizar(produto_id: int, corpo: ProdutoPatch,
              con: sqlite3.Connection = Depends(get_db)):
    campos = corpo.model_dump(exclude_none=True)
    if not campos:
        raise HTTPException(400, "Nada para atualizar")
    if "ativo" in campos:
        campos["ativo"] = int(campos["ativo"])
    sets = ", ".join(f"{c}=?" for c in campos)
    cur = con.execute(
        f"UPDATE catalogo_produtos SET {sets} WHERE id=?",
        (*campos.values(), produto_id),
    )
    if not cur.rowcount:
        raise HTTPException(404, "Produto não encontrado")
    con.commit()
    return dict(con.execute(
        "SELECT * FROM catalogo_produtos WHERE id=?", (produto_id,)
    ).fetchone())
