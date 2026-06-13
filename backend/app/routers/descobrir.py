"""PNCP ao vivo — explorar o PNCP sem persistir (CLAUDE.md §4.1 e §4.4).

O usuário pode navegar os ~37 mil editais nacionais ao vivo e importar para o
radar local sob demanda. Tudo passa pelo cliente PNCP compartilhado (1 req/s +
cache 6h, princípio 6). Duas fontes:

- BUSCA textual (§4.1): quando há palavra-chave (ou tipo/status fora do padrão).
  O valor (valor_global) vem null nesse endpoint.
- CONSULTA em massa (§4.4): quando o usuário navega SEM palavra-chave em
  editais recebendo proposta — TODO registro já traz `valorTotalEstimado`, então
  os valores oficiais aparecem embutidos em todos os cartões instantaneamente.
"""
import sqlite3
import unicodedata
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .. import pncp
from ..deps import get_db
from ..services import avaliacao, classificador, descoberta
from .pregoes import _resumo_pregao

router = APIRouter(prefix="/descobrir", tags=["descobrir"])

# a busca do PNCP devolve no máx. 10 itens/página independente de tamanhoPagina
TAMANHO = 50
MAX_TERMOS = 5
MAX_ALVOS = avaliacao.MAX_ALVOS  # avaliação sob demanda: máx. alvos por chamada (P6)
MODALIDADES_VALIDAS = {str(i) for i in range(1, 14)}  # ids 1..13 (CLAUDE.md §4.1)
ESFERAS_VALIDAS = {"F", "E", "M", "D"}
# janela do bulk: contratações com proposta encerrando até hoje+N dias (AAAAMMDD).
# Horizonte AMPLO (verificado 12/06/2026): 90d devolvia 28.698; 25 anos devolve
# 37.895 ≈ tudo que está recebendo proposta (paridade com o total do PNCP) —
# credenciamentos e concorrências grandes encerram a anos de distância.
DIAS_JANELA_BULK = 365 * 25
# o server-side da consulta aceita 1 modalidade e 1 UF por request; acima destes
# limites a fan-out fica cara demais → deixamos o filtro p/ o client (UI já tem)
MAX_MODALIDADES_BULK = 5
MAX_UFS_BULK = 4
# a BUSCA TEXTUAL também só aceita UM valor por filtro: modalidades/ufs/esferas
# em csv retornam total=0 EM SILÊNCIO (verificado 12/06/2026) → fan-out de
# 1 chamada por valor (produto cartesiano com os termos), somando os totais
MAX_MODALIDADES_BUSCA = 5   # cobre o "só compra de bens" (4,5,6,7,8)
MAX_UFS_BUSCA = 4           # mesmo teto do bulk
MAX_ESFERAS_BUSCA = 3       # as 4 = todas = sem filtro
MAX_CHAMADAS_BUSCA = 25     # teto de chamadas por página (5 termos × 5 modalidades)
# "só compra de bens" (so_bens): o ruído de serviço/concessão dentro das
# modalidades de compra é ~78% (corpus rotulado). A API de Consulta (§4.4) TRAVA
# tamanhoPagina em 50 (60+ → HTTP 400, verificado 13/06/2026 — NÃO subir), então
# não há bump de página; quem compensa o afinamento é o fan-out por modalidade
# (5 modalidades de compra × 50 = 250 brutos/página → ~55 sobrevivem ao filtro).


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


def _amparo_texto(amparo) -> str | None:
    """amparoLegal pode ser objeto {nome, descricao} ou string — extrai o texto."""
    if not amparo:
        return None
    if isinstance(amparo, str):
        return amparo
    if isinstance(amparo, dict):
        return amparo.get("descricao") or amparo.get("nome")
    return None


def _mapear_consulta(reg: dict) -> dict:
    """Registro da API de Consulta (§4.4) → MESMO shape de hit da busca (§4.1).

    O `hit` resultante alimenta tanto `_adaptar` (cartão da UI) quanto
    `persistir_hit` no importar — sem mudanças nesses dois. Por isso usa as
    chaves crus da busca textual (title/orgao_cnpj/ano/numero_sequencial…).
    O valor (`valor_global`) vem de `valorTotalEstimado`, sempre preenchido.
    """
    orgao = reg.get("orgaoEntidade") or {}
    unidade = reg.get("unidadeOrgao") or {}
    tipo_nome = reg.get("tipoInstrumentoConvocatorioNome") or "Edital"
    numero = reg.get("numeroCompra")
    ano = reg.get("anoCompra")
    title = f"{tipo_nome} nº {numero}/{ano}" if numero else f"{tipo_nome} {ano or ''}".strip()
    return {
        "title": title,
        "description": reg.get("objetoCompra"),
        "orgao_cnpj": orgao.get("cnpj"),
        "orgao_nome": orgao.get("razaoSocial"),
        "ano": ano,
        "numero_sequencial": reg.get("sequencialCompra"),
        "numero_controle_pncp": reg.get("numeroControlePNCP"),
        "municipio_nome": unidade.get("municipioNome"),
        "uf": unidade.get("ufSigla"),
        "modalidade_licitacao_nome": reg.get("modalidadeNome"),
        "situacao_nome": reg.get("situacaoCompraNome"),
        "data_fim_vigencia": reg.get("dataEncerramentoProposta"),
        "data_publicacao_pncp": reg.get("dataPublicacaoPncp"),
        "valor_global": reg.get("valorTotalEstimado"),
        "unidade_nome": unidade.get("nomeUnidade"),
        "fundamentacao_legal": _amparo_texto(reg.get("amparoLegal")),
    }


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
    so_bens: bool = False,
    pagina: int = Query(1, ge=1),
    con: sqlite3.Connection = Depends(get_db),
):
    """Consulta AO VIVO o PNCP, sem persistir nada. Duas fontes (campo `fonte`):

    - `"consulta"` (EM MASSA, §4.4): quando NÃO há palavra-chave, `status` é
      `recebendo_proposta` e `tipos_documento` é `edital`. TODO registro já traz
      `valorTotalEstimado` → os valores oficiais aparecem embutidos em todos os
      cartões instantaneamente. Fan-out 1 chamada por modalidade × UF (limites
      server-side: 5 modalidades, 4 UFs; acima disso o filtro fica no client).
    - `"busca"` (TEXTUAL, §4.1): demais casos (com `q`, ou status/tipo fora do
      padrão acima). O valor (`valor_global`) vem null nesse endpoint.

    - `q` é REPETÍVEL (`?q=microfone&q=caixa de som`): cada termo vira UMA
      consulta (mesma `pagina`); o resultado é mesclado com dedup por
      `numero_controle` intercalando round-robin (não enviesa para o 1º termo).
      Sem `q` → fonte em massa (acima). Máx. 5 termos (422 acima).
    - `excluir` (repetível, máx. 5): descarta hits cujo `title+description+orgao`
      contenha qualquer termo (normalizado: caixa baixa + acentos removidos);
      aplica-se às duas fontes como pós-filtro (aí `total_exato=false`).
    - `status`: só recebendo_proposta|encerradas filtram; todos = sem filtro.
    - `so_bens`: pós-filtra os hits (as DUAS fontes) por
      `classificador.e_compra_de_bens(title + " " + description)` — derruba
      serviço/concessão que vazam dentro das modalidades de compra
      (credenciamento, prestação de serviços, SRP de serviço, concessão de uso
      etc.). NÃO substitui a restrição de modalidades que o front já manda; é
      complementar. Filtrando, `total_exato=false`. O afinamento (~78% de
      ruído) é compensado pelo fan-out por modalidade de compra, não por
      página maior (a API de Consulta trava tamanhoPagina em 50).
    - `total_exato`: true ⇔ uma única consulta E sem exclusão E sem so_bens
      (caso contrário a soma dos totais pode ter sobreposição ou o pós-filtro
      reduzir; a UI sinaliza "até N").
    """
    if len(q) > MAX_TERMOS:
        raise HTTPException(422, f"máx. {MAX_TERMOS} termos de busca")
    if len(excluir) > MAX_TERMOS:
        raise HTTPException(422, f"máx. {MAX_TERMOS} termos de exclusão")
    modalidades = _validar_modalidades(modalidades)
    esferas = _validar_esferas(esferas)

    termos = [t for t in (s.strip() for s in q) if t] or [""]
    excl = [_normalizar(t) for t in excluir if t.strip()]
    tem_q = any(t for t in termos)

    # FONTE EM MASSA (§4.4): navegação SEM palavra-chave, editais recebendo
    # proposta. Aqui o valor oficial vem embutido em cada registro.
    usar_bulk = (
        not tem_q
        and status == "recebendo_proposta"
        and tipos_documento == "edital"
    )

    if usar_bulk:
        hits_ordem, total, total_exato, fonte = _hits_bulk(
            modalidades, ufs, pagina, so_bens,
        )
    else:
        hits_ordem, total, total_exato, fonte = _hits_busca(
            termos, ufs, status, tipos_documento, ordenacao,
            modalidades, esferas, pagina,
        )

    itens = []
    for hit in hits_ordem:
        if excl:
            palheiro = _normalizar(" ".join(filter(None, (
                hit.get("title"), hit.get("description"), hit.get("orgao_nome"),
            ))))
            if any(termo in palheiro for termo in excl):
                continue
        # so_bens: pós-filtro aquisição-aware sobre o texto do objeto (título +
        # descrição). Vale para as DUAS fontes (bulk e textual).
        if so_bens:
            objeto = " ".join(filter(None, (hit.get("title"), hit.get("description"))))
            if not classificador.e_compra_de_bens(objeto):
                continue
        nc = hit.get("numero_controle_pncp")
        local = con.execute(
            "SELECT id FROM pregoes WHERE numero_controle=?", (nc,)
        ).fetchone() if nc else None
        itens.append(_adaptar(hit, local is not None, local["id"] if local else None))

    return {
        # exclusão ou so_bens → o total bruto superestima (pós-filtro client-side)
        "total": total,
        "total_exato": total_exato and not excl and not so_bens,
        "pagina": pagina,
        "tamanho": TAMANHO,
        "fonte": fonte,
        "itens": itens,
    }


def _merge_round_robin(listas: list[list[dict]]) -> list[dict]:
    """Intercala N listas com dedup por numero_controle (não enviesa p/ a 1ª)."""
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
    return hits_ordem


def _eixo_busca(csv_valores: str, maximo: int) -> tuple[list[str], bool]:
    """Valores de um filtro p/ fan-out. Acima do teto → sem filtro server-side."""
    vals = [v for v in csv_valores.split(",") if v] if csv_valores else []
    if len(vals) > maximo:
        return [""], True
    return (vals or [""]), False


def _hits_busca(termos, ufs, status, tipos_documento, ordenacao,
                modalidades, esferas, pagina):
    """Fonte textual (§4.1): fan-out 1 chamada por termo × modalidade × UF × esfera.

    A busca do PNCP aceita só UM valor por filtro — csv (ex. modalidades=6,8)
    retorna total=0 em silêncio (verificado 12/06/2026). Cada chamada vai com
    valor único; os totais somam EXATO entre combos (eixos disjuntos: cada
    pregão tem uma única modalidade/UF/esfera; só termos sobrepõem). Acima dos
    tetos por eixo, ou do teto de chamadas por página, o filtro do eixo é
    descartado (esferas → UFs; modalidades ficam — carregam o "só compra de
    bens") e o total vira "até N" (total_exato=False).
    """
    mods, desc_m = _eixo_busca(modalidades, MAX_MODALIDADES_BUSCA)
    sigs, desc_u = _eixo_busca(ufs, MAX_UFS_BUSCA)
    esfs, desc_e = _eixo_busca(esferas, MAX_ESFERAS_BUSCA)
    descartou = desc_m or desc_u or desc_e

    if len(termos) * len(mods) * len(sigs) * len(esfs) > MAX_CHAMADAS_BUSCA and len(esfs) > 1:
        esfs, descartou = [""], True
    if len(termos) * len(mods) * len(sigs) * len(esfs) > MAX_CHAMADAS_BUSCA and len(sigs) > 1:
        sigs, descartou = [""], True

    def _consultar(termo: str, mod: str, uf: str, esf: str) -> dict:
        try:
            return pncp.cliente().buscar(
                q=termo, ufs=uf, status=status, pagina=pagina, tamanho=TAMANHO,
                tipos_documento=tipos_documento, ordenacao=ordenacao,
                modalidades=mod, esferas=esf,
            )
        except RuntimeError as exc:  # PNCP fora do ar após os retries
            raise HTTPException(503, str(exc))

    combos = [(t, m, u, e)
              for t in termos for m in mods for u in sigs for e in esfs]
    respostas = [_consultar(*combo) for combo in combos]
    total = sum(r.get("total", 0) for r in respostas)
    hits = _merge_round_robin([list(r.get("items", [])) for r in respostas])
    # exato ⇔ ≤1 termo (termos sobrepõem) E nenhum filtro descartado
    return hits, total, len(termos) <= 1 and not descartou, "busca"


def _hits_bulk(modalidades: str, ufs: str, pagina: int, so_bens: bool = False):
    """Fonte em massa (§4.4): valor oficial embutido em cada registro.

    Fan-out controlado: 1 chamada por modalidade × UF selecionada. Acima dos
    limites server-side (5 modalidades, 4 UFs) ignoramos o filtro e deixamos o
    pós-filtro para o client (a UI já filtra por modalidade/UF localmente).

    `so_bens`: o pós-filtro aquisição-aware corta ~78% (ruído); a página fica em
    TAMANHO (50, teto da API de Consulta) e quem compensa o afinamento é o
    fan-out por modalidade de compra (5 × 50 = 250 brutos/página).
    """
    data_final = (date.today() + timedelta(days=DIAS_JANELA_BULK)).strftime("%Y%m%d")
    tamanho = TAMANHO

    mods = [m for m in modalidades.split(",") if m] if modalidades else []
    if len(mods) > MAX_MODALIDADES_BULK:
        mods = []          # muitas → filtra no client
    siglas = [u.strip() for u in ufs.split(",") if u.strip()] if ufs else []
    if len(siglas) > MAX_UFS_BULK:
        siglas = []        # muitas → filtra no client

    # produto cartesiano modalidade × uf; vazio em qualquer eixo = sem o param
    combos = [(m, u) for m in (mods or [""]) for u in (siglas or [""])]

    def _consultar(mod: str, uf: str) -> dict:
        try:
            return pncp.cliente().consulta_propostas(
                data_final=data_final, modalidade=mod, uf=uf,
                pagina=pagina, tamanho=tamanho,
            )
        except RuntimeError as exc:  # PNCP fora do ar após os retries
            raise HTTPException(503, str(exc))

    respostas = [_consultar(m, u) for (m, u) in combos]
    total = sum(r.get("totalRegistros", 0) for r in respostas)
    listas = [
        [_mapear_consulta(reg) for reg in (r.get("data") or [])]
        for r in respostas
    ]
    hits = _merge_round_robin(listas)
    # exato ⇔ uma única combinação (somar totais de combos sobrepõe)
    return hits, total, len(combos) <= 1, "consulta"


class AlvoAvaliacao(BaseModel):
    cnpj: str
    ano: int
    seq: int
    numero_controle: str


class AvaliarIn(BaseModel):
    alvos: list[AlvoAvaliacao]


@router.post("/avaliar")
def avaliar(corpo: AvaliarIn, con: sqlite3.Connection = Depends(get_db)):
    """Avalia editais da busca ao vivo SEM persistir (valor real + potencial aderente).

    Para cada alvo busca os itens no PNCP (cache 6h → re-avaliações grátis,
    1 req/s) e devolve em memória: Σ valorTotal, total de itens, itens do ramo
    do usuário (match ≥ threshold contra o catálogo) e a receita aderente
    (Σ preço esperado × qtd). Nada toca o banco. Máx. 40 alvos por chamada;
    falha de um alvo entra em `erros` sem derrubar o lote.

    Custo: 40 alvos × N páginas de itens a 1 req/s pode levar minutos (decisão
    do dono); o front avisa o usuário antes de disparar.
    """
    if not corpo.alvos:
        raise HTTPException(422, "envie ao menos um alvo para avaliar")
    if len(corpo.alvos) > MAX_ALVOS:
        raise HTTPException(422, f"máx. {MAX_ALVOS} alvos por avaliação")
    alvos = [a.model_dump() for a in corpo.alvos]
    return avaliacao.avaliar_alvos(con, alvos)


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
