"""RAG Fase 1 — chunking verbatim, gate de citação, recuperação extrativa e
endpoints. Tudo com embed FAKE determinístico (nunca o e5 real) e páginas
inline (nunca PDF/modelo real). Decisões do dono: threshold 0.80, single-edital.
"""
import numpy as np
import pytest

from app.services import extracao, habilitacao, matching, rag

# --------- páginas inline (texto cru com cláusulas numeradas) ---------

PAGINA_1 = (
    "EDITAL DE PREGÃO ELETRÔNICO Nº 27/2026\n"
    "Aquisição de palanques de áudio para o município.\n"
    "\n"
    "1. DO OBJETO\n"
    "1.1 O objeto é a aquisição de equipamentos de áudio e vídeo.\n"
    "\n"
    "2. DO PRAZO DE ENTREGA\n"
    "2.1 O prazo de entrega dos produtos é de 30 (trinta) dias corridos.\n"
)
PAGINA_2 = (
    "3. DA HABILITAÇÃO\n"
    "3.1 Certidão negativa de débitos federais é exigida.\n"
    "\n"
    "4. DA GARANTIA\n"
    "4.1 A garantia mínima dos equipamentos é de 12 (doze) meses.\n"
)
PAGINAS = [PAGINA_1, PAGINA_2]


# --------- embed fake determinístico, content-aware ---------

# eixos temáticos (vetores ortogonais normalizados). O embed fake escolhe o eixo
# por palavra-chave presente no texto; assim a pergunta sobre "prazo de entrega"
# casa SÓ o chunk que fala de prazo de entrega (cosseno 1.0) e fica ortogonal aos
# demais (cosseno 0.0). Tudo passa por numpy (matriz @ q) como na produção.
_EIXOS = {
    "prazo": [1.0, 0.0, 0.0, 0.0],
    "habilitacao": [0.0, 1.0, 0.0, 0.0],
    "garantia": [0.0, 0.0, 1.0, 0.0],
    "objeto": [0.0, 0.0, 0.0, 1.0],
}
_FORA = [0.0, 0.0, 0.0, 0.0]  # tema desconhecido → ortogonal a tudo


def _eixo(texto: str):
    t = texto.lower()
    if "prazo de entrega" in t or "prazo" in t:
        return _EIXOS["prazo"]
    if "habilita" in t or "certidão" in t or "débitos" in t:
        return _EIXOS["habilitacao"]
    if "garantia" in t:
        return _EIXOS["garantia"]
    if "objeto" in t or "aquisição" in t:
        return _EIXOS["objeto"]
    return list(_FORA)


class EmbedFake:
    """Devolve vetores normalizados por eixo temático (prefixo e5 ignorado)."""

    def __init__(self):
        self.chamadas = 0

    def __call__(self, textos):
        self.chamadas += 1
        out = []
        for t in textos:
            # remove o prefixo e5 ("query: "/"passage: ") antes de classificar
            corpo = t.split(": ", 1)[-1]
            out.append(_eixo(corpo))
        return out


# --------- chunking preserva página/offset verbatim ---------

def test_chunkar_offsets_verbatim_e_pagina_1based():
    chunks = rag._chunkar(PAGINAS)
    assert chunks, "deveria produzir chunks"
    for ch in chunks:
        pagina_str = PAGINAS[ch["pagina"] - 1]
        # INVARIANTE central: texto == pagina[inicio:fim] EXATO (verbatim)
        assert ch["texto"] == pagina_str[ch["offset_inicio"]:ch["offset_fim"]]
        assert 1 <= ch["pagina"] <= len(PAGINAS)
    # ordem crescente dentro de cada página
    for pag in {c["pagina"] for c in chunks}:
        ordens = [c["ordem"] for c in chunks if c["pagina"] == pag]
        assert ordens == sorted(ordens)
        assert ordens[0] == 0


def test_chunk_citacao_aponta_trecho_real():
    """Defesa em profundidade: cada chunk passa o gate de citação (princípio 2)."""
    chunks = rag._chunkar(PAGINAS)
    for ch in chunks:
        assert habilitacao.verificar_citacao(ch["texto"], PAGINAS) is True


# --------- recuperação extrativa ---------

def test_indexar_e_perguntar_recupera_chunk_no_topo(con):
    pid = _criar_pregao(con)
    embed = EmbedFake()
    res = rag.indexar_chunks(con, pid, [(None, PAGINAS)], embed=embed)
    assert res["n_chunks"] > 0
    assert res["n_paginas"] == 2

    r = rag.perguntar(con, pid, "qual o prazo de entrega?", embed=embed)
    assert r["disponivel"] is True
    assert r["trechos"], "esperava trechos"
    topo = r["trechos"][0]
    assert "prazo de entrega" in topo["texto"].lower()
    assert topo["score"] >= 0.80
    assert topo["pagina"] == 1


def test_perguntar_fora_do_tema_nao_encontrado(con):
    pid = _criar_pregao(con)
    embed = EmbedFake()
    rag.indexar_chunks(con, pid, [(None, PAGINAS)], embed=embed)
    # pergunta sem palavra-chave conhecida → vetor fora (ortogonal) → score 0
    r = rag.perguntar(con, pid, "qual a cor do papel timbrado?", embed=embed)
    assert r["disponivel"] is False
    assert r["motivo"] == "nao_encontrado"
    assert r["trechos"] == []


def test_perguntar_sem_indexar_nao_indexado(con):
    pid = _criar_pregao(con)
    r = rag.perguntar(con, pid, "qual o prazo?", embed=EmbedFake())
    assert r["disponivel"] is False
    assert r["motivo"] == "nao_indexado"
    assert r["trechos"] == []


def test_indexar_idempotente_substitui(con):
    pid = _criar_pregao(con)
    embed = EmbedFake()
    rag.indexar_chunks(con, pid, [(None, PAGINAS)], embed=embed)
    n1 = con.execute(
        "SELECT COUNT(*) c FROM rag_chunks WHERE pregao_id=?", (pid,)
    ).fetchone()["c"]
    rag.indexar_chunks(con, pid, [(None, PAGINAS)], embed=embed)
    n2 = con.execute(
        "SELECT COUNT(*) c FROM rag_chunks WHERE pregao_id=?", (pid,)
    ).fetchone()["c"]
    assert n1 == n2  # reindexar não duplica
    st = con.execute(
        "SELECT n_chunks, n_paginas, modelo FROM rag_status WHERE pregao_id=?",
        (pid,),
    ).fetchone()
    assert st["n_chunks"] == n1
    assert st["n_paginas"] == 2


def test_blob_round_trip_float32(con):
    """O vetor sai como BLOB float32 e volta idêntico (np.frombuffer)."""
    pid = _criar_pregao(con)
    rag.indexar_chunks(con, pid, [(None, PAGINAS)], embed=EmbedFake())
    rows, matriz = rag._carregar_matriz(con, pid)
    assert matriz is not None
    assert matriz.dtype == np.float32
    assert matriz.shape[0] == len(rows)
    # cada vetor recarregado bate com o eixo temático do texto do chunk
    for i, r in enumerate(rows):
        esperado = np.asarray(_eixo(r["texto"]), dtype=np.float32)
        assert np.allclose(matriz[i], esperado)


# --------- endpoints ---------

def test_endpoint_indexar_status_perguntar(client, con, cliente_fake, monkeypatch):
    pid = _criar_pregao(con)
    # nunca PDF/modelo real: extração devolve páginas inline; embed é fake
    monkeypatch.setattr(extracao, "extrair_paginas", lambda _p: PAGINAS)
    monkeypatch.setattr(matching, "embed_padrao", EmbedFake())
    import app.pncp as pncp_mod
    monkeypatch.setattr(pncp_mod, "cliente", lambda: cliente_fake)

    r = client.post(f"/pregoes/{pid}/rag/indexar")
    assert r.status_code == 200
    assert r.json()["n_chunks"] > 0

    s = client.get(f"/pregoes/{pid}/rag/status")
    assert s.status_code == 200
    assert s.json()["indexado"] is True
    assert s.json()["n_paginas"] == 2

    r2 = client.post(f"/pregoes/{pid}/rag/perguntar",
                     json={"pergunta": "qual o prazo de entrega?"})
    assert r2.status_code == 200
    dados = r2.json()
    assert dados["disponivel"] is True
    assert dados["trechos"]
    assert "prazo de entrega" in dados["trechos"][0]["texto"].lower()


def test_endpoint_perguntar_fora_do_tema(client, con, cliente_fake, monkeypatch):
    pid = _criar_pregao(con)
    monkeypatch.setattr(extracao, "extrair_paginas", lambda _p: PAGINAS)
    monkeypatch.setattr(matching, "embed_padrao", EmbedFake())
    import app.pncp as pncp_mod
    monkeypatch.setattr(pncp_mod, "cliente", lambda: cliente_fake)
    client.post(f"/pregoes/{pid}/rag/indexar")

    r = client.post(f"/pregoes/{pid}/rag/perguntar",
                    json={"pergunta": "qual a cor do papel timbrado?"})
    assert r.status_code == 200
    assert r.json()["disponivel"] is False


def test_endpoint_status_nao_indexado(client, con):
    pid = _criar_pregao(con)
    s = client.get(f"/pregoes/{pid}/rag/status")
    assert s.status_code == 200
    assert s.json()["indexado"] is False


def test_endpoint_pregao_inexistente_404(client, con):
    # ingerir checa o pregão ANTES de tocar o cliente PNCP → 404 sem rede
    r0 = client.post("/pregoes/99999/rag/indexar")
    assert r0.status_code == 404
    r = client.post("/pregoes/99999/rag/perguntar", json={"pergunta": "x"})
    assert r.status_code == 404
    s = client.get("/pregoes/99999/rag/status")
    assert s.status_code == 404


def test_endpoint_pergunta_vazia_422(client, con):
    pid = _criar_pregao(con)
    r = client.post(f"/pregoes/{pid}/rag/perguntar", json={"pergunta": "   "})
    assert r.status_code == 422


# --------- helpers ---------

def _criar_pregao(con) -> int:
    cur = con.execute(
        """INSERT INTO pregoes (cnpj, ano, seq, numero_controle, titulo)
           VALUES ('01613770000172', 2026, 67, 'NC-RAG-1', 'Pregão RAG teste')"""
    )
    con.commit()
    return cur.lastrowid
