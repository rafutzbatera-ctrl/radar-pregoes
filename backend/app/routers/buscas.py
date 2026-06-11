import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_db
from ..services import descoberta

router = APIRouter(prefix="/buscas", tags=["buscas"])


class BuscaIn(BaseModel):
    nome: str
    termos: str                       # "áudio, microfone, caixa de som"
    ufs: str = ""                     # "SP" ou "SP,RJ"; vazio = todas
    status: str = "recebendo_proposta"
    ativo: bool = True


class BuscaPatch(BaseModel):
    nome: str | None = None
    termos: str | None = None
    ufs: str | None = None
    status: str | None = None
    ativo: bool | None = None


@router.get("")
def listar(con: sqlite3.Connection = Depends(get_db)):
    buscas = con.execute(
        "SELECT * FROM buscas_salvas ORDER BY criado_em DESC"
    ).fetchall()
    saida = []
    for b in buscas:
        novos = con.execute(
            "SELECT COUNT(*) c FROM pregoes WHERE busca_id=? AND novo=1", (b["id"],)
        ).fetchone()["c"]
        saida.append({**dict(b), "novos": novos})
    return saida


@router.post("", status_code=201)
def criar(corpo: BuscaIn, con: sqlite3.Connection = Depends(get_db)):
    cur = con.execute(
        "INSERT INTO buscas_salvas (nome, termos, ufs, status, ativo) VALUES (?,?,?,?,?)",
        (corpo.nome, corpo.termos, corpo.ufs, corpo.status, int(corpo.ativo)),
    )
    con.commit()
    return dict(con.execute(
        "SELECT * FROM buscas_salvas WHERE id=?", (cur.lastrowid,)
    ).fetchone())


@router.patch("/{busca_id}")
def atualizar(busca_id: int, corpo: BuscaPatch,
              con: sqlite3.Connection = Depends(get_db)):
    campos = corpo.model_dump(exclude_none=True)
    if not campos:
        raise HTTPException(400, "Nada para atualizar")
    sets = ", ".join(f"{c}=?" for c in campos)
    valores = [int(v) if isinstance(v, bool) else v for v in campos.values()]
    cur = con.execute(
        f"UPDATE buscas_salvas SET {sets} WHERE id=?", (*valores, busca_id)
    )
    if not cur.rowcount:
        raise HTTPException(404, "Busca não encontrada")
    con.commit()
    return dict(con.execute(
        "SELECT * FROM buscas_salvas WHERE id=?", (busca_id,)
    ).fetchone())


@router.post("/{busca_id}/rodar")
def rodar(busca_id: int, con: sqlite3.Connection = Depends(get_db)):
    try:
        # busca manual ignora cache para trazer o que há de mais novo
        return descoberta.rodar_busca(con, busca_id, usar_cache=False)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
