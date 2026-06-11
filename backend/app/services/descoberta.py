"""Descoberta de pregões via buscas salvas (CLAUDE.md §6.1).

Roda cada termo da busca na API de busca do PNCP, deduplica por
numero_controle_pncp e insere novos pregões com flag "novo".
O JSON cru do hit é persistido (fonte oficial — princípio 3).
"""
import json
import logging
import sqlite3

from .. import pncp

log = logging.getLogger("radar.descoberta")


def rodar_busca(con: sqlite3.Connection, busca_id: int,
                cliente: pncp.ClientePNCP | None = None,
                usar_cache: bool = True) -> dict:
    cliente = cliente or pncp.cliente()
    busca = con.execute(
        "SELECT * FROM buscas_salvas WHERE id=?", (busca_id,)
    ).fetchone()
    if busca is None:
        raise ValueError(f"Busca {busca_id} não existe")

    termos = [t.strip() for t in busca["termos"].split(",") if t.strip()]
    novos = 0
    vistos = 0
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
                novos += _persistir_hit(con, hit, busca_id)
            # uma página de 50 por termo é suficiente para monitoramento 2x/dia;
            # ordenação -data garante que os mais novos vêm primeiro
            break

    con.execute(
        "UPDATE buscas_salvas SET ultima_exec=datetime('now') WHERE id=?",
        (busca_id,),
    )
    con.commit()
    log.info("Busca %s: %s hits, %s novos", busca["nome"], vistos, novos)
    return {"busca_id": busca_id, "hits": vistos, "novos": novos}


def rodar_todas_ativas(con: sqlite3.Connection,
                       cliente: pncp.ClientePNCP | None = None) -> list[dict]:
    buscas = con.execute("SELECT id FROM buscas_salvas WHERE ativo=1").fetchall()
    return [rodar_busca(con, b["id"], cliente) for b in buscas]


def _persistir_hit(con: sqlite3.Connection, hit: dict, busca_id: int) -> int:
    """Insere o pregão se for novo (dedup por numero_controle_pncp). Retorna 1 se inseriu."""
    numero_controle = hit.get("numero_controle_pncp")
    if not numero_controle:
        return 0
    cnpj = hit.get("orgao_cnpj")
    ano = int(hit.get("ano") or 0)
    seq = int(hit.get("numero_sequencial") or 0)
    cur = con.execute(
        """INSERT INTO pregoes
             (cnpj, ano, seq, numero_controle, titulo, descricao, orgao, unidade,
              municipio, uf, modalidade, situacao, data_inicio_vigencia,
              data_fim_vigencia, valor_global, json_busca, link_pncp, busca_id, novo)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
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
        ),
    )
    return 1 if cur.rowcount else 0
