import json
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import pncp
from ..deps import get_db
from ..services import analise, fiscal, sincronizacao

router = APIRouter(prefix="/pregoes", tags=["pregoes"])


class PregaoPatch(BaseModel):
    salvo: bool | None = None
    novo: bool | None = None
    # pipeline de disputa (P2); null em status_pipeline = sai do funil
    status_pipeline: Literal["cotacao", "habilitacao", "disputando",
                             "ganho", "perdido", "suspenso"] | None = None
    data_disputa: str | None = None
    valor_final: float | None = None


def _resumo_pregao(con: sqlite3.Connection, p: sqlite3.Row) -> dict:
    contagens = con.execute(
        """SELECT COUNT(*) total,
                  SUM(match_confirmado) confirmados,
                  SUM(CASE WHEN produto_id IS NOT NULL AND match_confirmado=0
                      THEN 1 ELSE 0 END) sugeridos
           FROM itens_pregao WHERE pregao_id=?""", (p["id"],)
    ).fetchone()
    hab = con.execute(
        """SELECT COUNT(*) total,
                  SUM(CASE WHEN status_usuario!='ok' THEN 1 ELSE 0 END) pendentes,
                  SUM(CASE WHEN verificada=0 THEN 1 ELSE 0 END) nao_verificadas
           FROM habilitacao WHERE pregao_id=?""", (p["id"],)
    ).fetchone()
    arquivos = con.execute(
        "SELECT id, titulo, tipo, url, caminho_local, baixado_em FROM arquivos WHERE pregao_id=?",
        (p["id"],),
    ).fetchall()
    d = dict(p)
    json_busca = d.pop("json_busca", None)
    d["json_busca"] = json.loads(json_busca) if json_busca else None
    d["itens_total"] = contagens["total"] or 0
    d["itens_confirmados"] = contagens["confirmados"] or 0
    d["itens_sugeridos"] = contagens["sugeridos"] or 0
    d["cobertura"] = (d["itens_confirmados"] / d["itens_total"]) if d["itens_total"] else 0
    d["habilitacao_total"] = hab["total"] or 0
    d["habilitacao_pendentes"] = hab["pendentes"] or 0
    d["habilitacao_nao_verificadas"] = hab["nao_verificadas"] or 0
    d["arquivos"] = [dict(a) for a in arquivos]
    d["sincronizado"] = bool(d.get("sincronizado_em"))
    return d


@router.get("")
def listar(novos: bool | None = None, uf: str | None = None,
           salvos: bool | None = None,
           con: sqlite3.Connection = Depends(get_db)):
    sql = "SELECT * FROM pregoes WHERE 1=1"
    params: list = []
    if novos is not None:
        sql += " AND novo=?"
        params.append(int(novos))
    if salvos is not None:
        sql += " AND salvo=?"
        params.append(int(salvos))
    if uf:
        sql += " AND uf=?"
        params.append(uf.upper())
    sql += " ORDER BY descoberto_em DESC"
    return [_resumo_pregao(con, p) for p in con.execute(sql, params).fetchall()]


@router.get("/{pregao_id}")
def detalhe(pregao_id: int, con: sqlite3.Connection = Depends(get_db)):
    p = con.execute("SELECT * FROM pregoes WHERE id=?", (pregao_id,)).fetchone()
    if p is None:
        raise HTTPException(404, "Pregão não encontrado")
    return _resumo_pregao(con, p)


@router.patch("/{pregao_id}")
def atualizar(pregao_id: int, corpo: PregaoPatch,
              con: sqlite3.Connection = Depends(get_db)):
    # exclude_unset: distingue "não enviado" de "enviado como null" —
    # null limpa o campo (ex.: tirar do funil), ausente não toca
    campos = corpo.model_dump(exclude_unset=True)
    if not campos:
        raise HTTPException(400, "Nada para atualizar")
    sets = ", ".join(f"{c}=?" for c in campos)
    valores = [int(v) if isinstance(v, bool) else v for v in campos.values()]
    cur = con.execute(
        f"UPDATE pregoes SET {sets} WHERE id=?", (*valores, pregao_id)
    )
    if not cur.rowcount:
        raise HTTPException(404, "Pregão não encontrado")
    # entrada no funil: salvar pregão ainda sem status → cotacao
    if campos.get("salvo") is True:
        con.execute(
            "UPDATE pregoes SET status_pipeline='cotacao' "
            "WHERE id=? AND status_pipeline IS NULL", (pregao_id,)
        )
    con.commit()
    return detalhe(pregao_id, con)


@router.post("/{pregao_id}/sincronizar")
def sincronizar(pregao_id: int, con: sqlite3.Connection = Depends(get_db)):
    try:
        return sincronizacao.sincronizar(con, pregao_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.get("/{pregao_id}/itens")
def itens(pregao_id: int, con: sqlite3.Connection = Depends(get_db)):
    if con.execute("SELECT 1 FROM pregoes WHERE id=?", (pregao_id,)).fetchone() is None:
        raise HTTPException(404, "Pregão não encontrado")
    linhas = con.execute(
        """SELECT i.*, p.nome produto_nome, p.codigo produto_codigo,
                  p.custo_unit, p.ncm produto_ncm, p.unidade produto_unidade
           FROM itens_pregao i
           LEFT JOIN catalogo_produtos p ON p.id = i.produto_id
           WHERE i.pregao_id=? ORDER BY i.numero""",
        (pregao_id,),
    ).fetchall()
    saida = []
    for ln in linhas:
        d = dict(ln)
        conta = analise.margem_lucro_item(
            None if ln["sigiloso"] else ln["valor_unit_estimado"],
            ln["custo_unit"], ln["qtd"],
        )
        # prévia: a conta por item aparece mesmo sem confirmação (pill "prévia"
        # na UI), mas só itens confirmados entram nos agregados
        d["margem"] = conta["margem"]
        d["lucro"] = conta["lucro"]
        saida.append(d)
    return saida


@router.get("/{pregao_id}/arquivos")
def arquivos_pregao(pregao_id: int, con: sqlite3.Connection = Depends(get_db)):
    """Arquivos do edital com link direto para o binário oficial no PNCP.

    Se o pregão ainda não foi sincronizado, consulta só os METADADOS na API
    (sem download) — o PDF oficial fica a um clique mesmo sem sincronizar.
    """
    p = con.execute("SELECT * FROM pregoes WHERE id=?", (pregao_id,)).fetchone()
    if p is None:
        raise HTTPException(404, "Pregão não encontrado")
    linhas = con.execute(
        "SELECT titulo, tipo, url, caminho_local FROM arquivos WHERE pregao_id=?",
        (pregao_id,),
    ).fetchall()
    if linhas:
        return [dict(ln) for ln in linhas]
    try:
        lista = pncp.cliente().arquivos(p["cnpj"], p["ano"], p["seq"])
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    return [{"titulo": a.get("titulo"), "tipo": a.get("tipoDocumentoNome"),
             "url": a.get("url"), "caminho_local": None} for a in lista]


@router.get("/{pregao_id}/fiscal")
def fiscal_pregao(pregao_id: int, con: sqlite3.Connection = Depends(get_db)):
    if con.execute("SELECT 1 FROM pregoes WHERE id=?", (pregao_id,)).fetchone() is None:
        raise HTTPException(404, "Pregão não encontrado")
    return fiscal.fiscal_do_pregao(con, pregao_id)


@router.get("/{pregao_id}/habilitacao")
def habilitacao(pregao_id: int, con: sqlite3.Connection = Depends(get_db)):
    if con.execute("SELECT 1 FROM pregoes WHERE id=?", (pregao_id,)).fetchone() is None:
        raise HTTPException(404, "Pregão não encontrado")
    linhas = con.execute(
        "SELECT * FROM habilitacao WHERE pregao_id=? ORDER BY categoria, id",
        (pregao_id,),
    ).fetchall()
    return [dict(ln) for ln in linhas]
