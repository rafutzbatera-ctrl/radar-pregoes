"""PNCP ao vivo — explorar a busca do PNCP sem persistir (CLAUDE.md §4.1).

O usuário pode navegar os ~37 mil editais nacionais ao vivo (a API de busca
aceita consulta sem termo) e importar para o radar local sob demanda. Tudo
passa pelo cliente PNCP compartilhado (1 req/s + cache 6h, princípio 6).
"""
import sqlite3
import unicodedata
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .. import pncp
from ..deps import get_db
from ..services import descoberta
from .pregoes import _resumo_pregao

router = APIRouter(prefix="/descobrir", tags=["descobrir"])

# a busca do PNCP devolve no máx. 10 itens/página independente de tamanhoPagina
TAMANHO = 50
MAX_TERMOS = 5
MODALIDADES_VALIDAS = {str(i) for i in range(1, 14)}  # ids 1..13 (CLAUDE.md §4.1)
ESFERAS_VALIDAS = {"F", "E", "M", "D"}


def _normalizar(texto: str) -> str:
    """Caixa baixa + acentos removidos (para casar exclusão sem depender de acento)."""
    semacento = "".join(
        c for c in unicodedata.normalize("NFD", texto or "")
        if unicodedata.category(c) != "Mn"
    )
    return semacento.lower()


def _validar_modalidades(modalidades: str) -> str:
    if not modalidades:
        return ""
    ids = [m.strip() for m in modalidades.split(",") if m.strip()]
    for m in ids:
        if m not in MODALIDADES_VALIDAS:
            raise HTTPException(422, f"modalidade inválida: {m!r} (use ids 1-13)")
    return ",".join(ids)


def _validar_esferas(esferas: str) -> str:
    if not esferas:
        return ""
    letras = [e.strip().upper() for e in esferas.split(",") if e.strip()]
    for e in letras:
        if e not in ESFERAS_VALIDAS:
            raise HTTPException(422, f"esfera inválida: {e!r} (use F, E, M ou D)")
    return ",".join(letras)


def _adaptar(hit: dict, ja_no_radar: bool, pregao_id: int | None) -> dict:
    """Hit cru da busca do PNCP → cartão da UI (+ hit cru p/ reenviar no importar)."""
    return {
        "numero_controle": hit.get("numero_controle_pncp"),
        "titulo": hit.get("title"),
        "descricao": hit.get("description"),
        "orgao": hit.get("orgao_nome"),
        "municipio": hit.get("municipio_nome"),
        "uf": hit.get("uf"),
        "modalidade": hit.get("modalidade_licitacao_nome"),
        "situacao": hit.get("situacao_nome"),
        "data_fim_vigencia": hit.get("data_fim_vigencia"),
        "valor_global": hit.get("valor_global"),
        "cnpj": hit.get("orgao_cnpj"),
        "ano": hit.get("ano"),
        "seq": hit.get("numero_sequencial"),
        "ja_no_radar": ja_no_radar,
        "pregao_id": pregao_id,
        # JSON cru: o front guarda e devolve no /descobrir/importar (persistir_hit
        # espera os campos crus title/orgao_cnpj/ano/numero_sequencial…)
        "hit": hit,
    }


@router.get("")
def descobrir(
    q: list[str] = Query(default=[]),
    excluir: list[str] = Query(default=[]),
    ufs: str = "",
    status: Literal["recebendo_proposta", "encerradas", "todos"] = "recebendo_proposta",
    tipos_documento: Literal["edital", "ata", "contrato"] = "edital",
    ordenacao: Literal["-data", "data", "relevancia"] = "-data",
    modalidades: str = "",
    esferas: str = "",
    pagina: int = Query(1, ge=1),
    con: sqlite3.Connection = Depends(get_db),
):
    """Consulta AO VIVO a busca do PNCP, sem persistir nada.

    - `q` é REPETÍVEL (`?q=microfone&q=caixa de som`): cada termo vira UMA
      consulta (mesma `pagina`); o resultado é mesclado com dedup por
      `numero_controle` intercalando round-robin (não enviesa para o 1º termo).
      Sem `q` → uma consulta única (total nacional). Máx. 5 termos (422 acima).
    - `excluir` (repetível, máx. 5): descarta hits cujo `title+description+orgao`
      contenha qualquer termo (normalizado: caixa baixa + acentos removidos).
    - `status`: só recebendo_proposta|encerradas filtram; todos = sem filtro.
    - `total_exato`: true ⇔ ≤1 termo E sem exclusão (caso contrário a soma dos
      totais por termo pode ter sobreposição; a UI deve sinalizar "até N").
    """
    if len(q) > MAX_TERMOS:
        raise HTTPException(422, f"máx. {MAX_TERMOS} termos de busca")
    if len(excluir) > MAX_TERMOS:
        raise HTTPException(422, f"máx. {MAX_TERMOS} termos de exclusão")
    modalidades = _validar_modalidades(modalidades)
    esferas = _validar_esferas(esferas)

    termos = [t for t in (s.strip() for s in q) if t] or [""]
    excl = [_normalizar(t) for t in excluir if t.strip()]

    def _consultar(termo: str) -> dict:
        try:
            return pncp.cliente().buscar(
                q=termo, ufs=ufs, status=status, pagina=pagina, tamanho=TAMANHO,
                tipos_documento=tipos_documento, ordenacao=ordenacao,
                modalidades=modalidades, esferas=esferas,
            )
        except RuntimeError as exc:  # PNCP fora do ar após os retries
            raise HTTPException(503, str(exc))

    # uma consulta por termo; guarda os hits e o total de cada uma
    respostas = [_consultar(termo) for termo in termos]
    total = sum(r.get("total", 0) for r in respostas)

    # merge round-robin com dedup por numero_controle (intercala os termos)
    listas = [list(r.get("items", [])) for r in respostas]
    hits_ordem: list[dict] = []
    vistos: set = set()
    for col in range(max((len(l) for l in listas), default=0)):
        for lst in listas:
            if col >= len(lst):
                continue
            hit = lst[col]
            nc = hit.get("numero_controle_pncp")
            chave = nc if nc is not None else id(hit)
            if chave in vistos:
                continue
            vistos.add(chave)
            hits_ordem.append(hit)

    itens = []
    for hit in hits_ordem:
        if excl:
            palheiro = _normalizar(" ".join(filter(None, (
                hit.get("title"), hit.get("description"), hit.get("orgao_nome"),
            ))))
            if any(termo in palheiro for termo in excl):
                continue
        nc = hit.get("numero_controle_pncp")
        local = con.execute(
            "SELECT id FROM pregoes WHERE numero_controle=?", (nc,)
        ).fetchone() if nc else None
        itens.append(_adaptar(hit, local is not None, local["id"] if local else None))

    return {
        "total": total,
        "total_exato": len(termos) <= 1 and not excl,
        "pagina": pagina,
        "tamanho": TAMANHO,
        "itens": itens,
    }


class ImportarIn(BaseModel):
    numero_controle: str
    hit: dict  # JSON cru do item da busca (o front guarda e devolve)


@router.post("/importar")
def importar(corpo: ImportarIn, con: sqlite3.Connection = Depends(get_db)):
    """Importa um pregão da busca ao vivo para o radar local (idempotente).

    Reaproveita persistir_hit (busca_id=None: pregão sem busca salva de origem).
    Retorna o pregão local no mesmo shape de GET /pregoes/{id}.
    """
    descoberta.persistir_hit(con, corpo.hit, busca_id=None)
    con.commit()
    p = con.execute(
        "SELECT * FROM pregoes WHERE numero_controle=?", (corpo.numero_controle,)
    ).fetchone()
    if p is None:
        # persistir_hit ignora hit sem numero_controle_pncp — nada a importar
        raise HTTPException(422, "Hit sem número de controle do PNCP — nada a importar")
    return _resumo_pregao(con, p)
