"""Cadastro da EMPRESA do licitante (RAG Fase 3 — minutas de declarações).

Tabela de LINHA ÚNICA (id=1): os dados do próprio fornecedor que preenchem os
templates de declaração de habilitação. NÃO é dado de edital — é texto-padrão
do licitante, então o gate de citação NÃO se aplica aqui. Cadastro incremental:
todo campo é nullable e, quando vazio, vira lacuna VISÍVEL na minuta
(princípio 1: nunca chutar). Por isso esta tabela NÃO usa `config` (allowlist
rígida de parâmetros do sistema), tem schema próprio.

GET /empresa  -> a linha 1 ou, se ainda não existe, objeto com campos null.
PUT /empresa  -> upsert da linha 1 (cadastro parcial: só os campos enviados).
"""
import re
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_db

router = APIRouter(prefix="/empresa", tags=["empresa"])

# colunas editáveis da empresa (ordem usada no SELECT/render)
CAMPOS = (
    "razao_social", "cnpj", "endereco",
    "representante_nome", "representante_cpf", "representante_cargo",
    "porte",
)

PORTES_VALIDOS = {"me_epp", "normal"}


class EmpresaIn(BaseModel):
    # PUT parcial: só os campos enviados são atualizados (exclude_unset abaixo).
    razao_social: str | None = None
    cnpj: str | None = None
    endereco: str | None = None
    representante_nome: str | None = None
    representante_cpf: str | None = None
    representante_cargo: str | None = None
    porte: str | None = None           # 'me_epp' | 'normal' | None


def _normalizar_doc(valor: str) -> str:
    """Remove tudo que não é dígito de CNPJ/CPF (validação leve — não exige
    preenchimento; só normaliza o que veio). Mantém vazio como vazio."""
    return re.sub(r"\D", "", valor or "")


def _linha(con: sqlite3.Connection):
    return con.execute("SELECT * FROM empresa WHERE id=1").fetchone()


def _vazia() -> dict:
    """Objeto com todos os campos null — resposta do GET quando não há cadastro."""
    return {"id": 1, **{c: None for c in CAMPOS}, "atualizado_em": None}


@router.get("")
def ler(con: sqlite3.Connection = Depends(get_db)):
    """Retorna a empresa (linha 1) ou um objeto com campos null se ainda não
    cadastrada — nunca inventa dado (princípio 1)."""
    ln = _linha(con)
    return dict(ln) if ln else _vazia()


@router.put("")
def salvar(corpo: EmpresaIn, con: sqlite3.Connection = Depends(get_db)):
    """Upsert da linha 1. Cadastro incremental: PUT parcial atualiza só os
    campos enviados; campos não enviados ficam como estão."""
    campos = corpo.model_dump(exclude_unset=True)

    # porte: aceita só {'me_epp','normal'} ou None (limpa). Qualquer outro -> 422.
    if "porte" in campos:
        p = campos["porte"]
        p = (p or "").strip() or None
        if p is not None and p not in PORTES_VALIDOS:
            raise HTTPException(422, "porte deve ser 'me_epp', 'normal' ou null")
        campos["porte"] = p

    # CNPJ/CPF: validação LEVE — não exige; só normaliza p/ dígitos (aceita
    # máscara na entrada). Vazio vira None (lacuna na minuta, princípio 1).
    for k in ("cnpj", "representante_cpf"):
        if k in campos:
            campos[k] = _normalizar_doc(campos[k]) or None

    # demais campos de texto: trim, vazio -> None.
    for k in ("razao_social", "endereco", "representante_nome",
              "representante_cargo"):
        if k in campos:
            campos[k] = (campos[k] or "").strip() or None

    existe = _linha(con) is not None
    if not existe:
        # garante a linha 1; campos não enviados ficam NULL.
        con.execute("INSERT INTO empresa(id) VALUES (1)")
    if campos:
        sets = ", ".join(f"{c}=?" for c in campos)
        con.execute(
            f"UPDATE empresa SET {sets}, atualizado_em=datetime('now') WHERE id=1",
            (*campos.values(),),
        )
    else:
        con.execute("UPDATE empresa SET atualizado_em=datetime('now') WHERE id=1")
    con.commit()
    return dict(_linha(con))
