"""POST /pregoes/{id}/sincronizar — itens + arquivos + habilitação (CLAUDE.md §7).

Etapas (cada uma é melhor-esforço; falha de uma não derruba as outras,
mas é reportada no resultado):
1. Itens do PNCP (4.2) → upsert sem sobrescrever decisões de match do usuário.
2. Arquivos (4.3) → download para data/arquivos/{cnpj}_{ano}_{seq}/.
3. Habilitação: extrai texto dos PDFs tipo "Edital", roda o extrator plugável
   (heurístico local por padrão; ou API/CLI) + gate de citação.
4. Sugestões de matching (e5).
5. Recalcula análise/veredito.
"""
import logging
import sqlite3
from pathlib import Path

from .. import pncp, settings
from . import analise, extracao, habilitacao, matching

log = logging.getLogger("radar.sincronizacao")


def sincronizar(con: sqlite3.Connection, pregao_id: int,
                cliente: pncp.ClientePNCP | None = None,
                com_habilitacao: bool = True, embed=None) -> dict:
    cliente = cliente or pncp.cliente()
    pregao = con.execute("SELECT * FROM pregoes WHERE id=?", (pregao_id,)).fetchone()
    if pregao is None:
        raise ValueError(f"Pregão {pregao_id} não existe")

    resultado: dict = {"pregao_id": pregao_id, "erros": []}

    # 1) itens
    try:
        itens = cliente.itens(pregao["cnpj"], pregao["ano"], pregao["seq"])
        resultado["itens"] = _persistir_itens(con, pregao_id, itens)
    except Exception as exc:
        log.exception("Falha ao sincronizar itens do pregão %s", pregao_id)
        resultado["erros"].append(f"itens: {exc}")

    # 2) arquivos
    pdfs_edital: list[Path] = []
    try:
        arquivos = cliente.arquivos(pregao["cnpj"], pregao["ano"], pregao["seq"])
        pdfs_edital = _baixar_arquivos(con, pregao, arquivos, cliente)
        resultado["arquivos"] = len(arquivos)
    except Exception as exc:
        log.exception("Falha ao sincronizar arquivos do pregão %s", pregao_id)
        resultado["erros"].append(f"arquivos: {exc}")

    # 3) habilitação (extrator plugável + gate) — roda com qualquer modo
    if com_habilitacao and pdfs_edital:
        try:
            paginas: list[str] = []
            for pdf in pdfs_edital:
                paginas.extend(extracao.extrair_paginas(pdf))
            requisitos = habilitacao.extrair_requisitos(paginas)
            verificados = habilitacao.aplicar_gate(requisitos, paginas)
            resultado["habilitacao"] = habilitacao.persistir(con, pregao_id, verificados)
            resultado["habilitacao_nao_verificadas"] = sum(
                1 for r in verificados if not r["verificada"]
            )
        except Exception as exc:
            log.exception("Falha na extração de habilitação do pregão %s", pregao_id)
            resultado["erros"].append(f"habilitacao: {exc}")

    # 4) matching
    try:
        kwargs = {"embed": embed} if embed else {}
        resultado["matches_sugeridos"] = matching.sugerir_matches(con, pregao_id, **kwargs)
    except Exception as exc:
        log.exception("Falha no matching do pregão %s", pregao_id)
        resultado["erros"].append(f"matching: {exc}")

    # 5) análise
    resultado["analise"] = analise.analisar_pregao(con, pregao_id)

    con.execute(
        "UPDATE pregoes SET sincronizado_em=datetime('now') WHERE id=?", (pregao_id,)
    )
    con.commit()
    return resultado


def sincronizar_itens(con: sqlite3.Connection, pregao_id: int,
                      cliente: pncp.ClientePNCP | None = None,
                      embed=None) -> dict:
    """Sincronização LEVE: só itens (API 4.2) + matching + análise.

    Sem download de arquivos nem extração de habilitação — é o que roda
    automaticamente ao abrir um pregão (1-2 requisições, cache 6h).
    """
    cliente = cliente or pncp.cliente()
    pregao = con.execute("SELECT * FROM pregoes WHERE id=?", (pregao_id,)).fetchone()
    if pregao is None:
        raise ValueError(f"Pregão {pregao_id} não existe")

    resultado: dict = {"pregao_id": pregao_id, "erros": []}
    try:
        itens = cliente.itens(pregao["cnpj"], pregao["ano"], pregao["seq"])
        resultado["itens"] = _persistir_itens(con, pregao_id, itens)
    except Exception as exc:
        log.exception("Falha ao sincronizar itens do pregão %s", pregao_id)
        resultado["erros"].append(f"itens: {exc}")
    try:
        kwargs = {"embed": embed} if embed else {}
        resultado["matches_sugeridos"] = matching.sugerir_matches(con, pregao_id, **kwargs)
    except Exception as exc:
        log.exception("Falha no matching do pregão %s", pregao_id)
        resultado["erros"].append(f"matching: {exc}")
    resultado["analise"] = analise.analisar_pregao(con, pregao_id)
    return resultado


def _persistir_itens(con: sqlite3.Connection, pregao_id: int, itens: list) -> int:
    persistidos = 0
    for it in itens:
        # numero (numeroItem) é INTEGER NOT NULL + parte do UNIQUE(pregao_id,
        # numero). Se o PNCP omitir numeroItem (None), o INSERT levantaria
        # IntegrityError e — como o commit é só no fim — abortaria a persistência
        # do LOTE INTEIRO (pregão ficaria sem itens). Pular o item defeituoso e
        # seguir é melhor-esforço: registra e não derruba os demais.
        if it.get("numeroItem") is None:
            log.warning("Pregão %s: item sem numeroItem ignorado (%r)",
                        pregao_id, it.get("descricao"))
            continue
        con.execute(
            """INSERT INTO itens_pregao
                 (pregao_id, numero, descricao, qtd, unidade, valor_unit_estimado,
                  valor_total, beneficio, criterio, ncm_pncp, info_complementar,
                  sigiloso, material_ou_servico)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(pregao_id, numero) DO UPDATE SET
                 descricao=excluded.descricao, qtd=excluded.qtd,
                 unidade=excluded.unidade,
                 valor_unit_estimado=excluded.valor_unit_estimado,
                 valor_total=excluded.valor_total, beneficio=excluded.beneficio,
                 criterio=excluded.criterio, ncm_pncp=excluded.ncm_pncp,
                 info_complementar=excluded.info_complementar,
                 sigiloso=excluded.sigiloso,
                 material_ou_servico=excluded.material_ou_servico""",
            (
                pregao_id, it.get("numeroItem"), it.get("descricao"),
                it.get("quantidade"), it.get("unidadeMedida"),
                # orçamento sigiloso → valores podem vir nulos; exibir "sigiloso"
                it.get("valorUnitarioEstimado"), it.get("valorTotal"),
                it.get("tipoBeneficioNome"), it.get("criterioJulgamentoNome"),
                it.get("ncmNbsCodigo"), it.get("informacaoComplementar"),
                int(bool(it.get("orcamentoSigiloso"))),
                # §4.2 materialOuServicoNome ("Material" | "Serviço"); tolera ausência
                it.get("materialOuServicoNome"),
            ),
        )
        persistidos += 1
    con.commit()
    return persistidos


def _baixar_arquivos(con: sqlite3.Connection, pregao: sqlite3.Row,
                     arquivos: list, cliente: pncp.ClientePNCP) -> list[Path]:
    """Baixa cada arquivo (se ainda não baixado) e retorna os PDFs tipo Edital/TR."""
    destino_dir = settings.ARQUIVOS_DIR / f"{pregao['cnpj']}_{pregao['ano']}_{pregao['seq']}"
    pdfs: list[Path] = []
    for arq in arquivos:
        url = arq.get("url")
        existente = con.execute(
            "SELECT caminho_local FROM arquivos WHERE pregao_id=? AND url=?",
            (pregao["id"], url),
        ).fetchone()
        if existente and existente["caminho_local"] and Path(existente["caminho_local"]).exists():
            caminho = Path(existente["caminho_local"])
        else:
            caminho = cliente.baixar_arquivo(url, destino_dir)
            con.execute(
                """INSERT INTO arquivos (pregao_id, titulo, tipo, url, caminho_local, baixado_em)
                   VALUES (?,?,?,?,?,datetime('now'))
                   ON CONFLICT(pregao_id, url) DO UPDATE SET
                     caminho_local=excluded.caminho_local, baixado_em=excluded.baixado_em""",
                (pregao["id"], arq.get("titulo"), arq.get("tipoDocumentoNome"),
                 url, str(caminho)),
            )
        tipo = (arq.get("tipoDocumentoNome") or "").lower()
        if caminho.suffix.lower() == ".pdf" and ("edital" in tipo or "termo" in tipo):
            pdfs.append(caminho)
    con.commit()
    return pdfs
