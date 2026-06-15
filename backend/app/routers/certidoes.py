"""Minhas certidões — CRUD + alertas de vencimento (CLAUDE.md, item #13).

O fornecedor guarda suas certidões/documentos de habilitação (CND federal, FGTS,
trabalhista etc.) com data de validade; o sistema avisa quando estão vencidas ou
perto de vencer. O `status`/`dias_restantes` é CALCULADO a partir de hoje em
services/certidoes.py (nunca persistido). validade NULL = sem validade.
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_db
from ..services import certidoes as svc

router = APIRouter(prefix="/certidoes", tags=["certidoes"])


class CertidaoIn(BaseModel):
    nome: str
    orgao_emissor: str | None = None
    validade: str | None = None        # ISO 'YYYY-MM-DD' ou None = sem validade
    observacao: str | None = None


class CertidaoPatch(BaseModel):
    nome: str | None = None
    orgao_emissor: str | None = None
    validade: str | None = None
    observacao: str | None = None


def _linha(con: sqlite3.Connection, cid: int):
    return con.execute("SELECT * FROM certidoes WHERE id=?", (cid,)).fetchone()


def _listar_enriquecidas(con: sqlite3.Connection):
    linhas = [svc.enriquecer(dict(r))
              for r in con.execute("SELECT * FROM certidoes").fetchall()]
    linhas.sort(key=svc.ordem_urgencia)
    return linhas


@router.get("")
def listar(con: sqlite3.Connection = Depends(get_db)):
    """Lista ordenada por urgência (vencida/vence_em_breve primeiro)."""
    return _listar_enriquecidas(con)


@router.get("/alertas")
def alertas(con: sqlite3.Connection = Depends(get_db)):
    """Só as vencidas + vence_em_breve (badge/dashboard). `total` para o contador."""
    urgentes = [c for c in _listar_enriquecidas(con) if svc.eh_alerta(c)]
    return {"total": len(urgentes), "certidoes": urgentes}


@router.post("", status_code=201)
def criar(corpo: CertidaoIn, con: sqlite3.Connection = Depends(get_db)):
    nome = (corpo.nome or "").strip()
    if not nome:
        raise HTTPException(422, "nome é obrigatório")
    # validade, se enviada (não-vazia), tem de ser data ISO válida — senão 422.
    validade = (corpo.validade or "").strip() or None
    if validade is not None and not svc.validade_valida(validade):
        raise HTTPException(422, "validade deve ser data ISO YYYY-MM-DD")
    cur = con.execute(
        "INSERT INTO certidoes (nome, orgao_emissor, validade, observacao) "
        "VALUES (?,?,?,?)",
        (nome, (corpo.orgao_emissor or "").strip() or None, validade,
         (corpo.observacao or "").strip() or None),
    )
    con.commit()
    return svc.enriquecer(dict(_linha(con, cur.lastrowid)))


@router.patch("/{certidao_id}")
def atualizar(certidao_id: int, corpo: CertidaoPatch,
              con: sqlite3.Connection = Depends(get_db)):
    if _linha(con, certidao_id) is None:
        raise HTTPException(404, "Certidão não encontrada")
    campos = corpo.model_dump(exclude_unset=True)
    if not campos:
        raise HTTPException(400, "Nada para atualizar")
    if "nome" in campos:
        nome = (campos["nome"] or "").strip()
        if not nome:
            raise HTTPException(422, "nome não pode ser vazio")
        campos["nome"] = nome
    if "validade" in campos:
        # None/'' limpa a validade (volta a sem_validade); senão valida ISO.
        v = (campos["validade"] or "").strip() or None
        if v is not None and not svc.validade_valida(v):
            raise HTTPException(422, "validade deve ser data ISO YYYY-MM-DD")
        campos["validade"] = v
    for k in ("orgao_emissor", "observacao"):
        if k in campos:
            campos[k] = (campos[k] or "").strip() or None
    sets = ", ".join(f"{c}=?" for c in campos)
    con.execute(
        f"UPDATE certidoes SET {sets}, atualizado_em=datetime('now') WHERE id=?",
        (*campos.values(), certidao_id),
    )
    con.commit()
    return svc.enriquecer(dict(_linha(con, certidao_id)))


@router.delete("/{certidao_id}", status_code=204)
def remover(certidao_id: int, con: sqlite3.Connection = Depends(get_db)):
    cur = con.execute("DELETE FROM certidoes WHERE id=?", (certidao_id,))
    if not cur.rowcount:
        raise HTTPException(404, "Certidão não encontrada")
    con.commit()
    return None
