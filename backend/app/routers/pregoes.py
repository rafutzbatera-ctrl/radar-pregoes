import csv
import io
import json
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import pncp
from ..deps import get_db
from ..services import (analise, capag, fiscal, historico, relatorio,
                        sincronizacao)

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
                      THEN 1 ELSE 0 END) sugeridos,
                  SUM(valor_total) valor_itens
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
    # valor derivado: Σ valor_total dos itens (oficial do PNCP) — usado pela UI
    # quando o valor_global da busca vem nulo, sempre rotulado "Σ dos itens"
    d["valor_itens"] = contagens["valor_itens"]
    d["cobertura"] = (d["itens_confirmados"] / d["itens_total"]) if d["itens_total"] else 0
    d["habilitacao_total"] = hab["total"] or 0
    d["habilitacao_pendentes"] = hab["pendentes"] or 0
    d["habilitacao_nao_verificadas"] = hab["nao_verificadas"] or 0
    d["arquivos"] = [dict(a) for a in arquivos]
    d["sincronizado"] = bool(d.get("sincronizado_em"))
    return d


def _montar_resumo(p: sqlite3.Row, contagens, hab, arquivos: list) -> dict:
    """Monta o resumo de UM pregão a partir de contagens/arquivos JÁ buscados.

    É exatamente a parte "de montagem" do _resumo_pregao (mesmas chaves e
    valores), só que sem as 3 queries por pregão — a listagem injeta os mapas
    pré-agregados (GROUP BY). `contagens` e `hab` podem ser None (pregão sem
    itens/habilitação), tratados como zeros — idêntico ao COUNT(*)=0 do SQL.
    `arquivos` é a lista (possivelmente vazia) de dicts já prontos.
    """
    d = dict(p)
    json_busca = d.pop("json_busca", None)
    d["json_busca"] = json.loads(json_busca) if json_busca else None
    itens_total = (contagens["total"] if contagens else 0) or 0
    confirmados = (contagens["confirmados"] if contagens else 0) or 0
    sugeridos = (contagens["sugeridos"] if contagens else 0) or 0
    valor_itens = contagens["valor_itens"] if contagens else None
    d["itens_total"] = itens_total
    d["itens_confirmados"] = confirmados
    d["itens_sugeridos"] = sugeridos
    d["valor_itens"] = valor_itens
    d["cobertura"] = (confirmados / itens_total) if itens_total else 0
    d["habilitacao_total"] = (hab["total"] if hab else 0) or 0
    d["habilitacao_pendentes"] = (hab["pendentes"] if hab else 0) or 0
    d["habilitacao_nao_verificadas"] = (hab["nao_verificadas"] if hab else 0) or 0
    d["arquivos"] = arquivos
    d["sincronizado"] = bool(d.get("sincronizado_em"))
    return d


@router.get("")
def listar(novos: bool | None = None, uf: str | None = None,
           salvos: bool | None = None,
           valor_min: float | None = None, valor_max: float | None = None,
           ordem: Literal["recente", "potencial", "valor", "prazo"] = "recente",
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
    # ordem base recente = descoberto_em DESC (vem do SQL); as demais reordenam
    # em Python sobre os resumos (listas pequenas, valor efetivo já computado).
    sql += " ORDER BY descoberto_em DESC"
    pregoes = con.execute(sql, params).fetchall()

    # Pré-agregação (evita N+1): em vez de 3 SELECTs por pregão, montamos 3
    # mapas com GROUP BY restritos aos ids desta listagem. Total de queries:
    # 1 (pregões) + 3 (itens/habilitação/arquivos) = 4, independe de N.
    ids = [p["id"] for p in pregoes]
    cont_map: dict = {}
    hab_map: dict = {}
    arq_map: dict = {}
    if ids:
        ph = ",".join("?" for _ in ids)
        for row in con.execute(
            f"""SELECT pregao_id,
                       COUNT(*) total,
                       SUM(match_confirmado) confirmados,
                       SUM(CASE WHEN produto_id IS NOT NULL AND match_confirmado=0
                           THEN 1 ELSE 0 END) sugeridos,
                       SUM(valor_total) valor_itens
                FROM itens_pregao WHERE pregao_id IN ({ph})
                GROUP BY pregao_id""", ids).fetchall():
            cont_map[row["pregao_id"]] = row
        for row in con.execute(
            f"""SELECT pregao_id,
                       COUNT(*) total,
                       SUM(CASE WHEN status_usuario!='ok' THEN 1 ELSE 0 END) pendentes,
                       SUM(CASE WHEN verificada=0 THEN 1 ELSE 0 END) nao_verificadas
                FROM habilitacao WHERE pregao_id IN ({ph})
                GROUP BY pregao_id""", ids).fetchall():
            hab_map[row["pregao_id"]] = row
        for a in con.execute(
            f"""SELECT id, titulo, tipo, url, caminho_local, baixado_em, pregao_id
                FROM arquivos WHERE pregao_id IN ({ph})
                ORDER BY id""", ids).fetchall():
            ad = dict(a)
            pid = ad.pop("pregao_id")
            arq_map.setdefault(pid, []).append(ad)

    itens = []
    for p in pregoes:
        d = _montar_resumo(p, cont_map.get(p["id"]), hab_map.get(p["id"]),
                           arq_map.get(p["id"], []))
        # valor efetivo para filtro/ordenação (valor_global ▸ Σ itens)
        ve = d["valor_global"] if d.get("valor_global") is not None else d.get("valor_itens")
        # faixa de valor inclusive; pregão sem valor efetivo só passa se não há
        # piso/teto exigido (não inventa valor — princípio 1).
        if valor_min is not None and (ve is None or ve < valor_min):
            continue
        if valor_max is not None and (ve is None or ve > valor_max):
            continue
        d["_ve"] = ve
        itens.append(d)

    if ordem == "potencial":
        # receita_aderente desc, NULL/0 no fim
        itens.sort(key=lambda d: (d.get("receita_aderente") or 0), reverse=True)
    elif ordem == "valor":
        # valor efetivo desc, NULL no fim
        itens.sort(key=lambda d: (d.get("_ve") is None, -(d.get("_ve") or 0)))
    elif ordem == "prazo":
        # data_fim_vigencia asc, NULL no fim
        itens.sort(key=lambda d: (d.get("data_fim_vigencia") is None,
                                  d.get("data_fim_vigencia") or ""))
    # "recente": mantém a ordem do SQL (descoberto_em DESC)

    for d in itens:
        d.pop("_ve", None)
    return itens


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


@router.post("/{pregao_id}/sincronizar-itens")
def sincronizar_itens(pregao_id: int, con: sqlite3.Connection = Depends(get_db)):
    """Sincronização leve (itens + matching + análise), sem PDF/habilitação.

    Roda automaticamente quando a UI abre um pregão sem itens — os itens vêm
    da API pública do PNCP, nunca de extração de PDF.
    """
    try:
        return sincronizacao.sincronizar_itens(con, pregao_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


def _itens_calculados(con: sqlite3.Connection, pregao_id: int) -> list[dict]:
    """Itens do pregão com a conta montada (custo efetivo, preço esperado,
    margem, lucro, simulação e pisos). Fonte ÚNICA reusada por GET /itens, pelo
    export (CSV/XLSX) e pelo relatório PDF — a planilha/PDF levam a MESMA conta
    da tabela, não um recálculo paralelo."""
    # margem alvo da config (P3) — só guia a SIMULAÇÃO/pisos, nunca o veredito
    cfg = con.execute(
        "SELECT valor FROM config WHERE chave='margem_alvo'").fetchone()
    try:
        margem_alvo = float(cfg["valor"]) if cfg else 0.20
    except (ValueError, TypeError):
        margem_alvo = 0.20
    # deságio esperado da config (P4) — base do preço esperado; default 0 = teto
    desagio = analise.desagio_da_config(con)
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
        # material/serviço do PNCP (§4.2; coluna v8). SELECT i.* já o traz, mas
        # garantimos a chave para itens pré-v8 (None) — o export lê esta chave.
        d["material_ou_servico"] = (
            ln["material_ou_servico"]
            if "material_ou_servico" in ln.keys() else None
        )
        custo_ef, fonte = analise.custo_efetivo_row(ln)
        d["custo_efetivo"] = custo_ef
        d["fonte_custo"] = fonte
        # P4: preço esperado de disputa (lance ▸ teto×(1−deságio) ▸ teto). O
        # teto oficial (valor_unit_estimado) continua exposto cru — nunca some.
        preco, fonte_preco = analise.preco_esperado_row(ln, desagio)
        d["preco_esperado"] = preco
        d["fonte_preco"] = fonte_preco
        # conta por item com o custo EFETIVO (manual ▸ catálogo) sobre o PREÇO
        # ESPERADO (não o teto). Sigiloso sem lance fica sem preço → sem conta.
        conta = analise.margem_lucro_item(preco, custo_ef, ln["qtd"])
        d["margem"] = conta["margem"]
        d["lucro"] = conta["lucro"]
        # simulação por margem alvo: só quando NÃO há custo efetivo e existe
        # preço esperado. Base = preço esperado (P4). Sempre rotulada
        # "simulação" na UI; jamais entra na conta/veredito.
        if custo_ef is None and preco is not None and preco > 0:
            custo_max = preco * (1 - margem_alvo)
            d["simulacao_custo_max"] = custo_max
            d["simulacao_lucro"] = (preco - custo_max) * (ln["qtd"] or 0)
        else:
            d["simulacao_custo_max"] = None
            d["simulacao_lucro"] = None
        # pisos de lance (P4) — derivações do custo do usuário, guia de disputa.
        # Só com custo efetivo; NÃO entram em veredito/agregados. lance mínimo
        # mantendo a margem alvo = custo ÷ (1 − margem_alvo); empate = custo.
        if custo_ef is not None:
            d["lance_minimo_alvo"] = (custo_ef / (1 - margem_alvo)
                                      if margem_alvo < 1 else None)
            d["empate"] = custo_ef
        else:
            d["lance_minimo_alvo"] = None
            d["empate"] = None
        saida.append(d)
    return saida


@router.get("/{pregao_id}/itens")
def itens(pregao_id: int, con: sqlite3.Connection = Depends(get_db)):
    if con.execute("SELECT 1 FROM pregoes WHERE id=?", (pregao_id,)).fetchone() is None:
        raise HTTPException(404, "Pregão não encontrado")
    return _itens_calculados(con, pregao_id)


# colunas do export (Recurso 2): cabeçalho legível + extrator do item calculado.
# A planilha leva os dados CRUS do PNCP + a NOSSA conta (custo/preço/margem/lucro).
_EXPORT_COLUNAS: list[tuple[str, str]] = [
    ("número", "numero"),
    ("descrição", "descricao"),
    ("qtd", "qtd"),
    ("unidade", "unidade"),
    ("valor_unit_estimado", "valor_unit_estimado"),
    ("valor_total", "valor_total"),
    ("material_ou_servico", "material_ou_servico"),  # None → "" em _valor_export
    ("beneficio", "beneficio"),
    ("criterio", "criterio"),
    ("ncm", "ncm_pncp"),
    ("custo_efetivo", "custo_efetivo"),
    ("preco_esperado", "preco_esperado"),
    ("margem_pct", "margem_pct"),
    ("lucro", "lucro"),
]


def _valor_export(d: dict, chave: str):
    """Extrai o valor de uma coluna do export a partir do item calculado.
    Sigiloso esconde os valores oficiais; margem_pct = margem×100 (2 casas)."""
    sig = d.get("sigiloso")
    if chave == "material_ou_servico":
        # material/serviço do PNCP (§4.2, coluna v8 persistida na sync). Itens
        # pré-v8 não têm o dado → vazio (honesto, sem backfill). Mantém o
        # mesmo None→"" do export anterior (saída idêntica).
        return d.get("material_ou_servico") or ""
    if chave in ("valor_unit_estimado", "valor_total") and sig:
        return "sigiloso"
    if chave == "margem_pct":
        m = d.get("margem")
        return round(m * 100, 2) if m is not None else None
    return d.get(chave)


@router.get("/{pregao_id}/itens/export")
def exportar_itens(pregao_id: int, formato: str = "csv",
                   con: sqlite3.Connection = Depends(get_db)):
    """Exporta os itens do pregão em CSV ou XLSX (Recurso 2).

    Reusa _itens_calculados — a planilha leva os dados crus do PNCP MAIS a nossa
    conta (custo efetivo, preço esperado, margem, lucro). formato inválido → 422.
    """
    p = con.execute("SELECT cnpj, ano, seq FROM pregoes WHERE id=?",
                    (pregao_id,)).fetchone()
    if p is None:
        raise HTTPException(404, "Pregão não encontrado")
    if formato not in ("csv", "xlsx"):
        raise HTTPException(422, "formato deve ser 'csv' ou 'xlsx'")

    itens_calc = _itens_calculados(con, pregao_id)
    base = f"itens_{p['cnpj']}_{p['ano']}_{p['seq']}"
    cabecalho = [c[0] for c in _EXPORT_COLUNAS]

    if formato == "csv":
        buf = io.StringIO()
        # ; é o separador que o Excel-pt-BR abre direto; utf-8-sig dá o BOM
        w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
        w.writerow(cabecalho)
        for d in itens_calc:
            w.writerow([_valor_export(d, chave) for _rot, chave in _EXPORT_COLUNAS])
        dados = buf.getvalue().encode("utf-8-sig")
        return StreamingResponse(
            io.BytesIO(dados), media_type="text/csv; charset=utf-8",
            headers={"content-disposition": f'attachment; filename="{base}.csv"'},
        )

    # xlsx via openpyxl (dependência já presente do Stream A)
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Itens"
    ws.append(cabecalho)
    for d in itens_calc:
        ws.append([_valor_export(d, chave) for _rot, chave in _EXPORT_COLUNAS])
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return StreamingResponse(
        bio,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"content-disposition": f'attachment; filename="{base}.xlsx"'},
    )


@router.get("/{pregao_id}/historico")
def historico_pregao(pregao_id: int, con: sqlite3.Connection = Depends(get_db)):
    """Histórico do pregão (PNCP) — só os MARCOS, sem o ruído de sync (Recurso 4a).

    Lazy: chama o PNCP ao vivo (pista interativa, cache 6h) e filtra o ruído de
    sincronização automática num helper testável. Vazio → {"eventos": []}.
    """
    p = con.execute("SELECT cnpj, ano, seq FROM pregoes WHERE id=?",
                    (pregao_id,)).fetchone()
    if p is None:
        raise HTTPException(404, "Pregão não encontrado")
    try:
        cru = pncp.cliente().historico(p["cnpj"], p["ano"], p["seq"])
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    return {"eventos": historico.filtrar_eventos(cru)}


@router.get("/{pregao_id}/relatorio.pdf")
def relatorio_pregao(pregao_id: int, con: sqlite3.Connection = Depends(get_db)):
    """Relatório PDF do pregão (Recurso 3): cabeçalho, descrição, veredito +
    números, CAPAG, tabela de itens e os 2 avisos fixos §9. StreamingResponse."""
    p = con.execute("SELECT * FROM pregoes WHERE id=?", (pregao_id,)).fetchone()
    if p is None:
        raise HTTPException(404, "Pregão não encontrado")
    agregados = _resumo_pregao(con, p)
    itens_calc = _itens_calculados(con, pregao_id)
    # FIX honestidade: o PDF exibe a regra do veredito (cobertura COST-BASED),
    # mas _resumo_pregao traz cobertura MATCH-based (itens_confirmados/total).
    # Recalculamos cost-based a partir dos itens já calculados — MESMA definição
    # de analise.analisar_pregao — para o número do PDF casar com o hero/veredito.
    agregados = {**agregados,
                 "cobertura": analise.cobertura_cost_based(itens_calc)}
    esfera = p["esfera"] if "esfera" in p.keys() else None
    capag_dados = capag.capag_do_pregao(con, p["cnpj"], p["uf"], p["municipio"], esfera)
    pdf_bytes = relatorio.montar_pdf(p, itens_calc, capag_dados, agregados)
    base = f"relatorio_{p['cnpj']}_{p['ano']}_{p['seq']}"
    return StreamingResponse(
        io.BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"content-disposition": f'attachment; filename="{base}.pdf"'},
    )


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


@router.get("/{pregao_id}/capag")
def capag_pregao(pregao_id: int, con: sqlite3.Connection = Depends(get_db)):
    """CAPAG do ente comprador (risco de pagamento) — Tesouro/SICONFI.

    Lazy: só lê as tabelas populadas por scripts/seed_capag.py (nunca baixa no
    request). Federal/sem dado → {disponivel: False, motivo} — nunca chuta nota.
    """
    p = con.execute(
        "SELECT * FROM pregoes WHERE id=?", (pregao_id,)
    ).fetchone()
    if p is None:
        raise HTTPException(404, "Pregão não encontrado")
    # esfera do órgão (v7): decide a CAPAG (esfera-aware). Tolera banco antigo
    # sem a coluna (a migração v7 a garante, mas keys() protege em testes/fixtures).
    esfera = p["esfera"] if "esfera" in p.keys() else None
    return capag.capag_do_pregao(con, p["cnpj"], p["uf"], p["municipio"], esfera)


@router.get("/{pregao_id}/habilitacao")
def habilitacao(pregao_id: int, con: sqlite3.Connection = Depends(get_db)):
    if con.execute("SELECT 1 FROM pregoes WHERE id=?", (pregao_id,)).fetchone() is None:
        raise HTTPException(404, "Pregão não encontrado")
    linhas = con.execute(
        "SELECT * FROM habilitacao WHERE pregao_id=? ORDER BY categoria, id",
        (pregao_id,),
    ).fetchall()
    return [dict(ln) for ln in linhas]
