"""Avaliação sob demanda no modo PNCP ao vivo (P6) — EM MEMÓRIA, nada persiste.

O usuário navega os ~37 mil editais nacionais ao vivo (router descobrir.py) e
pode pedir o valor real (Σ itens) + o potencial aderente (itens do seu ramo)
SEM importar nada para o radar local. Tudo roda em memória:

- itens vêm do cliente PNCP compartilhado (cache 6h → re-avaliações grátis,
  1 req/s, princípio 6); falha de um alvo não derruba o lote;
- preço esperado por item segue a MESMA regra do P4 no modo ao vivo (sem lance):
  sigiloso → None; senão `valorUnitarioEstimado × (1 − deságio_da_config)`
  (deságio 0 → teto). O valor do edital é TETO (princípio 1);
- aderência = melhor cosseno do item contra o catálogo ativo ≥ MATCH_THRESHOLD
  (mesmo e5/threshold do matching persistido, mas aqui NADA grava no banco);
- `receita_aderente` = Σ preço_esperado × quantidade dos itens aderentes —
  o potencial exibido (× margem_alvo) é montado no front, sempre rotulado "sim".
"""
import sqlite3

from .. import settings
from . import analise, matching

MAX_ALVOS = 40


def _preco_esperado_cru(it: dict, desagio: float) -> float | None:
    """Preço esperado de um item CRU da API do PNCP (sem lance no modo ao vivo).

    Mesma regra do P4 (analise.preco_esperado_row) adaptada ao shape cru:
    sigiloso → None; teto inválido → None; senão teto×(1−deságio) (deságio 0 → teto).
    """
    if it.get("orcamentoSigiloso"):
        return None
    teto = it.get("valorUnitarioEstimado")
    if teto is None or teto <= 0:
        return None
    if desagio and desagio > 0:
        return teto * (1 - desagio)
    return teto


def avaliar_alvos(con: sqlite3.Connection, alvos: list[dict],
                  cliente=None, embed=None) -> dict:
    """Avalia uma lista de alvos da busca ao vivo SEM persistir nada.

    `alvos`: dicts com `cnpj`, `ano`, `seq`, `numero_controle`.
    `cliente` e `embed` injetáveis para teste (produção: cliente PNCP
    compartilhado + e5 real). Catálogo vazio → aderentes 0/receita null e o
    `embed` NUNCA é chamado.

    Retorna `{"avaliados": {nc: {...}}, "erros": {nc: msg}}`. Cada alvo que
    falha entra em `erros` e não derruba os demais.
    """
    if cliente is None:
        from .. import pncp
        cliente = pncp.cliente()
    if embed is None:
        embed = matching.embed_padrao

    desagio = analise.desagio_da_config(con)

    # embeds do catálogo calculados UMA vez por request (fora do loop de alvos).
    # Catálogo vazio → pula matching inteiro (nunca chama embed).
    produtos = con.execute(
        "SELECT id, nome FROM catalogo_produtos WHERE ativo=1"
    ).fetchall()
    vet_prod = (embed(["passage: " + p["nome"] for p in produtos])
                if produtos else None)

    avaliados: dict = {}
    erros: dict = {}

    for alvo in alvos:
        nc = alvo.get("numero_controle")
        try:
            itens = cliente.itens(alvo["cnpj"], int(alvo["ano"]), int(alvo["seq"]))
        except Exception as exc:  # falha de um alvo não derruba o lote
            erros[nc] = str(exc)
            continue

        valor_itens = None
        for it in itens:
            vt = it.get("valorTotal")
            if vt is not None:
                valor_itens = (valor_itens or 0.0) + vt

        itens_aderentes = 0
        receita_aderente = 0.0
        if vet_prod is not None and itens:
            vet_itens = embed(["query: " + (it.get("descricao") or "") for it in itens])
            for i, it in enumerate(itens):
                melhor = max(
                    (matching._dot(vet_itens[i], vet_prod[j]) for j in range(len(produtos))),
                    default=-1.0,
                )
                if melhor < settings.MATCH_THRESHOLD:
                    continue
                preco = _preco_esperado_cru(it, desagio)
                if preco is None or preco <= 0:
                    continue
                itens_aderentes += 1
                receita_aderente += preco * (it.get("quantidade") or 0)

        avaliados[nc] = {
            "valor_itens": valor_itens,
            "itens_total": len(itens),
            "itens_aderentes": itens_aderentes,
            "receita_aderente": receita_aderente if itens_aderentes else None,
        }

    return {"avaliados": avaliados, "erros": erros}
