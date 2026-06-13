"""Descoberta de pregões via buscas salvas (CLAUDE.md §6.1).

Roda cada termo da busca na API de busca do PNCP, deduplica por
numero_controle_pncp e insere novos pregões com flag "novo".
O JSON cru do hit é persistido (fonte oficial — princípio 3).
"""
import json
import logging
import sqlite3

from .. import pncp
from . import sincronizacao

log = logging.getLogger("radar.descoberta")


def rodar_busca(con: sqlite3.Connection, busca_id: int,
                cliente: pncp.ClientePNCP | None = None,
                usar_cache: bool = True,
                enriquecer: bool = True, embed=None) -> dict:
    cliente = cliente or pncp.cliente()
    busca = con.execute(
        "SELECT * FROM buscas_salvas WHERE id=?", (busca_id,)
    ).fetchone()
    if busca is None:
        raise ValueError(f"Busca {busca_id} não existe")

    termos = [t.strip() for t in busca["termos"].split(",") if t.strip()]
    novos = 0
    vistos = 0
    ids_novos: list[int] = []   # ids dos pregões inseridos nesta rodada (P5)
    for termo in termos:
        pagina = 1
        while True:
            resp = cliente.buscar(
                q=termo, ufs=busca["ufs"] or "",
                status=busca["status"] or "", pagina=pagina,
                usar_cache=usar_cache,
            )
            hits = resp.get("items", [])
            for hit in hits:
                vistos += 1
                pid = persistir_hit(con, hit, busca_id)
                if pid is not None:
                    novos += 1
                    ids_novos.append(pid)
            # uma página de 50 por termo é suficiente para monitoramento 2x/dia;
            # ordenação -data garante que os mais novos vêm primeiro
            break

    con.execute(
        "UPDATE buscas_salvas SET ultima_exec=datetime('now') WHERE id=?",
        (busca_id,),
    )
    con.commit()

    # P5 — enriquecimento na descoberta: já puxa itens + matching + análise dos
    # pregões NOVOS desta rodada e dos pregões DESTA busca ainda sem itens. Cada
    # um é melhor-esforço (falha de um não derruba a rodada). Decisão do dono:
    # busca manual fica ~30-60s mais lenta (1 req/s), aceito.
    enriquecidos = 0
    if enriquecer:
        alvos = list(ids_novos)
        # pendentes: sem itens OU sem análise de aderência (enriquecidos antes
        # da v5: receita_aderente NULL) — estes só re-analisam; os itens já
        # baixados vêm do cache de 6h, custo marginal ~zero
        pendentes = con.execute(
            """SELECT p.id FROM pregoes p
               WHERE p.busca_id=?
                 AND (NOT EXISTS (SELECT 1 FROM itens_pregao i
                                  WHERE i.pregao_id=p.id)
                      OR p.receita_aderente IS NULL)""",
            (busca_id,),
        ).fetchall()
        for ln in pendentes:
            if ln["id"] not in alvos:
                alvos.append(ln["id"])
        for pid in alvos:
            try:
                res = sincronizacao.sincronizar_itens(con, pid, cliente, embed=embed)
                # sincronizar_itens é melhor-esforço interno: erros de itens vão
                # para res["erros"] sem levantar. Só conta como enriquecido o
                # pregão que puxou itens sem erro (o resto fica para a próxima
                # rodada / abertura manual).
                if not res.get("erros"):
                    enriquecidos += 1
            except Exception:
                log.exception("Falha ao enriquecer pregão %s na descoberta", pid)

    log.info("Busca %s: %s hits, %s novos, %s enriquecidos",
             busca["nome"], vistos, novos, enriquecidos)
    return {"busca_id": busca_id, "hits": vistos, "novos": novos,
            "enriquecidos": enriquecidos}


def rodar_todas_ativas(con: sqlite3.Connection,
                       cliente: pncp.ClientePNCP | None = None,
                       enriquecer: bool = True, embed=None) -> list[dict]:
    buscas = con.execute("SELECT id FROM buscas_salvas WHERE ativo=1").fetchall()
    return [rodar_busca(con, b["id"], cliente, enriquecer=enriquecer, embed=embed)
            for b in buscas]


def persistir_hit(con: sqlite3.Connection, hit: dict,
                  busca_id: int | None) -> int | None:
    """Insere o pregão se for novo (dedup por numero_controle_pncp).

    Retorna o id do pregão inserido, ou None se já existia (ON CONFLICT DO
    NOTHING) ou se o hit não tinha numero_controle. `busca_id` pode ser None
    (importação manual via /descobrir — pregão sem busca salva de origem; a
    coluna pregoes.busca_id permite NULL).
    """
    numero_controle = hit.get("numero_controle_pncp")
    if not numero_controle:
        return None
    cnpj = hit.get("orgao_cnpj")
    ano = int(hit.get("ano") or 0)
    seq = int(hit.get("numero_sequencial") or 0)
    cur = con.execute(
        """INSERT INTO pregoes
             (cnpj, ano, seq, numero_controle, titulo, descricao, orgao, unidade,
              municipio, uf, modalidade, situacao, data_inicio_vigencia,
              data_fim_vigencia, valor_global, json_busca, link_pncp, busca_id,
              esfera, novo)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
           ON CONFLICT(numero_controle) DO NOTHING""",
        (
            cnpj, ano, seq, numero_controle,
            hit.get("title"), hit.get("description"),
            hit.get("orgao_nome"), hit.get("unidade_nome"),
            hit.get("municipio_nome"), hit.get("uf"),
            hit.get("modalidade_licitacao_nome"), hit.get("situacao_nome"),
            hit.get("data_inicio_vigencia"), hit.get("data_fim_vigencia"),
            hit.get("valor_global"),
            json.dumps(hit, ensure_ascii=False),
            pncp.link_pncp(cnpj, ano, seq),
            busca_id,
            # esfera do órgão (§4.4 orgaoEntidade.esferaId): None na busca §4.1
            # ou em hits pré-v7 — não quebra (coluna aceita NULL).
            hit.get("esfera_orgao"),
        ),
    )
    return cur.lastrowid if cur.rowcount else None
