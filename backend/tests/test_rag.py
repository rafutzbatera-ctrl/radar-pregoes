"""RAG Fase 1 — chunking verbatim, gate de citação, recuperação extrativa e
endpoints. Tudo com embed FAKE determinístico (nunca o e5 real) e páginas
inline (nunca PDF/modelo real). Decisões do dono: threshold 0.855 (recalibrado
no eval M7 — gate semântico-primário), single-edital.
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


def test_chunkar_descarta_ruido_de_extracao_preserva_verbatim():
    """PDF escaneado: pymupdf4llm injeta placeholders de imagem e blobs hex de
    assinatura. Esses blocos NÃO viram chunk (achatavam o cosseno ~0.84 e
    enganavam o threshold), mas o verbatim do que sobra é preservado."""
    pagina = (
        "**==> picture [55 x 55] intentionally omitted <==**\n"
        "\n"
        "09F680D5C2028AC2B5C8A0CBA58D4E1F2A3B4C5D6E7F8\n"
        "\n"
        "2. DO PRAZO DE ENTREGA\n"
        "2.1 O prazo de entrega e de 30 (trinta) dias corridos apos a ordem.\n"
        "\n"
        "----- Start of picture text -----\n"
    )
    chunks = rag._chunkar([pagina])
    assert len(chunks) == 1, "só o bloco de texto real deveria virar chunk"
    ch = chunks[0]
    assert "prazo de entrega" in ch["texto"].lower()
    assert "intentionally omitted" not in ch["texto"]
    assert "09F680D5" not in ch["texto"]
    # verbatim intacto mesmo com o filtro de ruído
    assert ch["texto"] == pagina[ch["offset_inicio"]:ch["offset_fim"]]


def test_chunkar_pagina_longa_split_com_overlap_preserva_verbatim():
    """Caminho de maior risco do verbatim: página > RAG_CHUNK_MAX vira ≥2 chunks
    com overlap. Cada chunk continua sendo fatia EXATA da página, os offsets são
    monótonos e chunks consecutivos se sobrepõem (o início recua p/ a cauda do
    anterior). Cobre a regressão que o revisor apontou (sem teste do split)."""
    from app import settings

    # 8 cláusulas numeradas de ~220 chars → ~1.8k chars >> RAG_CHUNK_MAX (900)
    clausulas = [
        f"{i}. CLAUSULA {i} - " + ("texto da clausula numero %d " % i) * 8
        for i in range(1, 9)
    ]
    pagina = "\n\n".join(clausulas) + "\n"
    chunks = rag._chunkar([pagina])

    assert len(chunks) >= 2, "página longa deveria gerar múltiplos chunks"
    for ch in chunks:
        # INVARIANTE verbatim mesmo no split: texto == pagina[inicio:fim]
        assert ch["texto"] == pagina[ch["offset_inicio"]:ch["offset_fim"]]
        assert ch["pagina"] == 1
        assert 0 <= ch["offset_inicio"] < ch["offset_fim"] <= len(pagina)
        assert habilitacao.verificar_citacao(ch["texto"], [pagina]) is True
    # offsets de início crescentes e overlap entre chunks consecutivos
    for ant, prox in zip(chunks, chunks[1:]):
        assert prox["offset_inicio"] < prox["offset_fim"]
        assert prox["offset_inicio"] > ant["offset_inicio"]          # avança
        assert prox["offset_inicio"] < ant["offset_fim"]             # mas sobrepõe


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


def test_perguntar_dimensao_incompativel_pede_reindexar(con):
    """Modelo trocado sem reindexar: vetores armazenados (dim N) ≠ embed atual
    (dim M). Em vez de estourar 500 no matriz @ q, devolve gracioso
    {disponivel: False, motivo: 'reindexar'} (padrão honesto do RAG)."""
    pid = _criar_pregao(con)
    # indexa com o embed de dim 4 (EmbedFake)
    rag.indexar_chunks(con, pid, [(None, PAGINAS)], embed=EmbedFake())

    # consulta com um embed que devolve vetor de OUTRA dimensão (dim 6)
    def embed_outra_dim(textos):
        return [[0.0, 0.0, 0.0, 0.0, 0.0, 1.0] for _ in textos]

    r = rag.perguntar(con, pid, "qual o prazo de entrega?", embed=embed_outra_dim)
    assert r["disponivel"] is False
    assert r["motivo"] == "reindexar"
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


def test_endpoint_pergunta_muito_longa_422(client, con):
    pid = _criar_pregao(con)
    r = client.post(f"/pregoes/{pid}/rag/perguntar",
                    json={"pergunta": "a" * 2001})
    assert r.status_code == 422
    assert "2000" in r.json()["detail"]


def test_endpoint_pergunta_no_limite_nao_estoura(client, con):
    # pergunta de 2000 chars (no teto) passa pelo cap; sem indexar → 200 com
    # disponivel=False. perguntar() retorna ANTES de embedar quando não há
    # chunks, então o e5 real nunca é tocado (validação de entrada, não de
    # recuperação).
    pid = _criar_pregao(con)
    r = client.post(f"/pregoes/{pid}/rag/perguntar",
                    json={"pergunta": "a" * 2000})
    assert r.status_code == 200
    assert r.json()["disponivel"] is False


# --------- Fase 2: síntese opt-in em perguntar (sintetizador FAKE) ---------

def test_perguntar_sem_sintetizar_e_fase1_pura(con):
    """sintetizar=False (default) → resposta NÃO tem bloco 'sintese'."""
    pid = _criar_pregao(con)
    embed = EmbedFake()
    rag.indexar_chunks(con, pid, [(None, PAGINAS)], embed=embed)
    r = rag.perguntar(con, pid, "qual o prazo de entrega?", embed=embed)
    assert r["disponivel"] is True
    assert "sintese" not in r  # Fase 1 pura


def test_perguntar_com_sintese_fundamentada_anexa_e_mantem_trechos(con):
    """Fake fundamentado → sintese_disponivel True E os trechos seguem presentes
    (a prosa nunca substitui a fonte — princípio 1/4)."""
    pid = _criar_pregao(con)
    embed = EmbedFake()
    rag.indexar_chunks(con, pid, [(None, PAGINAS)], embed=embed)

    def fake(pergunta, trechos):
        assert trechos, "o sintetizador recebe os trechos da Fase 1"
        return {"sintese_disponivel": True, "resposta": "O prazo é 30 dias.",
                "trechos_citados": [1], "modo": "fake"}

    r = rag.perguntar(con, pid, "qual o prazo de entrega?", embed=embed,
                      sintetizar=True, sintetizador=fake)
    assert r["disponivel"] is True
    assert r["trechos"], "os trechos NUNCA somem"
    assert r["sintese"]["sintese_disponivel"] is True
    assert r["sintese"]["resposta"] == "O prazo é 30 dias."


def test_perguntar_com_sintese_nao_encontrado_mantem_trechos(con):
    """Fake NAO_ENCONTRADO → sintese_disponivel False, mas os trechos seguem."""
    pid = _criar_pregao(con)
    embed = EmbedFake()
    rag.indexar_chunks(con, pid, [(None, PAGINAS)], embed=embed)

    def fake(pergunta, trechos):
        return {"sintese_disponivel": False, "motivo": "nao_encontrado"}

    r = rag.perguntar(con, pid, "qual o prazo de entrega?", embed=embed,
                      sintetizar=True, sintetizador=fake)
    assert r["disponivel"] is True
    assert r["trechos"]
    assert r["sintese"]["sintese_disponivel"] is False
    assert r["sintese"]["motivo"] == "nao_encontrado"


def test_perguntar_sintetizar_sem_trechos_nao_chama_fake(con):
    """Sem trechos (fora do tema) → nem síntese: nada muda na Fase 1."""
    pid = _criar_pregao(con)
    embed = EmbedFake()
    rag.indexar_chunks(con, pid, [(None, PAGINAS)], embed=embed)
    chamou = {"n": 0}

    def fake(pergunta, trechos):
        chamou["n"] += 1
        return {"sintese_disponivel": True, "resposta": "x", "trechos_citados": [1]}

    r = rag.perguntar(con, pid, "qual a cor do papel timbrado?", embed=embed,
                      sintetizar=True, sintetizador=fake)
    assert r["disponivel"] is False
    assert "sintese" not in r
    assert chamou["n"] == 0  # não há trecho p/ sintetizar


def test_perguntar_modo_off_nao_sintetiza(con, monkeypatch):
    """RAG_SINTESE_MODO=off → mesmo com sintetizar=True, sem bloco 'sintese'."""
    from app import settings as st
    monkeypatch.setattr(st, "RAG_SINTESE_MODO", "off")
    pid = _criar_pregao(con)
    embed = EmbedFake()
    rag.indexar_chunks(con, pid, [(None, PAGINAS)], embed=embed)

    def fake(pergunta, trechos):
        raise AssertionError("não deveria sintetizar com modo off")

    r = rag.perguntar(con, pid, "qual o prazo de entrega?", embed=embed,
                      sintetizar=True, sintetizador=fake)
    assert "sintese" not in r


# --------- Fase 2: GATE DURO em rag_sintese (executor FAKE, nunca o CLI) ---------

from app.services import rag_sintese

# trechos mínimos no formato da Fase 1 (texto/pagina/arquivo_titulo)
_TRECHOS = [
    {"texto": "2.1 O prazo de entrega dos produtos é de 30 (trinta) dias corridos.",
     "pagina": 1, "arquivo_titulo": "Edital"},
    {"texto": "4.1 A garantia mínima dos equipamentos é de 12 (doze) meses.",
     "pagina": 2, "arquivo_titulo": "Edital"},
]


def _executor(payload: dict):
    """Fabrica um executor fake que devolve sempre o JSON do payload (string),
    como o campo 'result' do CLI faria. NUNCA chama o claude real."""
    import json as _json
    return lambda _prompt: _json.dumps(payload)


def test_gate_aprova_resposta_fundamentada():
    r = rag_sintese.sintetizar(
        "qual o prazo?", _TRECHOS, modo="claude_cli",
        _executor=_executor({"resposta": "O prazo é 30 dias corridos.",
                             "trechos_citados": [1], "encontrado": True}),
    )
    assert r["sintese_disponivel"] is True
    assert r["trechos_citados"] == [1]
    assert r["modo"] == "claude_cli"
    assert r["fonte"] == "IA local sobre os trechos do edital"


def test_gate_reprova_indice_fora_do_range():
    r = rag_sintese.sintetizar(
        "qual o prazo?", _TRECHOS, modo="claude_cli",
        _executor=_executor({"resposta": "Resposta qualquer.",
                             "trechos_citados": [3], "encontrado": True}),
    )
    assert r["sintese_disponivel"] is False
    assert r["motivo"] == "nao_fundamentado"


def test_gate_reprova_encontrado_false_vira_nao_encontrado():
    r = rag_sintese.sintetizar(
        "qual a cor?", _TRECHOS, modo="claude_cli",
        _executor=_executor({"resposta": "NAO_ENCONTRADO",
                             "trechos_citados": [], "encontrado": False}),
    )
    assert r["sintese_disponivel"] is False
    assert r["motivo"] == "nao_encontrado"


def test_gate_reprova_token_nao_encontrado_mesmo_com_encontrado_true():
    """Token sentinela na prosa vale como não-encontrado (defesa em profundidade)."""
    r = rag_sintese.sintetizar(
        "qual a cor?", _TRECHOS, modo="claude_cli",
        _executor=_executor({"resposta": "NAO_ENCONTRADO",
                             "trechos_citados": [1], "encontrado": True}),
    )
    assert r["sintese_disponivel"] is False
    assert r["motivo"] == "nao_encontrado"


def test_gate_reprova_sem_indices_citados():
    r = rag_sintese.sintetizar(
        "qual o prazo?", _TRECHOS, modo="claude_cli",
        _executor=_executor({"resposta": "O prazo é 30 dias.",
                             "trechos_citados": [], "encontrado": True}),
    )
    assert r["sintese_disponivel"] is False
    assert r["motivo"] == "nao_fundamentado"


def test_gate_reprova_json_ruim():
    r = rag_sintese.sintetizar(
        "qual o prazo?", _TRECHOS, modo="claude_cli",
        _executor=lambda _p: "isto não é json nenhum",
    )
    assert r["sintese_disponivel"] is False
    assert r["motivo"] == "erro_sintese"


def test_gate_tolera_json_em_cerca_de_codigo():
    """Como o extrator claude_cli, tolera ```json ... ``` ao redor do objeto."""
    bruto = '```json\n{"resposta":"O prazo é 30 dias.","trechos_citados":[1],"encontrado":true}\n```'
    r = rag_sintese.sintetizar("qual o prazo?", _TRECHOS, modo="claude_cli",
                               _executor=lambda _p: bruto)
    assert r["sintese_disponivel"] is True
    assert r["trechos_citados"] == [1]


def test_gate_reprova_aspas_literais_fabricadas():
    """Robustez: aspas literais na prosa que NÃO existem nos trechos citados →
    reprova (verbatim citation gate reusado)."""
    r = rag_sintese.sintetizar(
        "qual o prazo?", _TRECHOS, modo="claude_cli",
        _executor=_executor({
            "resposta": 'O edital diz "prazo de quinhentos dias úteis improrrogáveis".',
            "trechos_citados": [1], "encontrado": True}),
    )
    assert r["sintese_disponivel"] is False
    assert r["motivo"] == "nao_fundamentado"


def test_gate_aprova_aspas_literais_reais():
    """Aspas literais que EXISTEM no trecho citado passam o gate."""
    r = rag_sintese.sintetizar(
        "qual o prazo?", _TRECHOS, modo="claude_cli",
        _executor=_executor({
            "resposta": 'O prazo é de "30 (trinta) dias corridos", conforme a cláusula 2.1.',
            "trechos_citados": [1], "encontrado": True}),
    )
    assert r["sintese_disponivel"] is True


def test_sintese_modo_off_nao_executa():
    """modo off → erro_sintese sem nem montar/rodar executor."""
    def boom(_p):
        raise AssertionError("não deveria executar com modo off")
    r = rag_sintese.sintetizar("qual o prazo?", _TRECHOS, modo="off",
                               _executor=boom)
    assert r["sintese_disponivel"] is False
    assert r["motivo"] == "erro_sintese"


def test_sintese_sem_trechos_nao_fundamentado():
    r = rag_sintese.sintetizar("qual o prazo?", [], modo="claude_cli",
                               _executor=lambda _p: "{}")
    assert r["sintese_disponivel"] is False
    assert r["motivo"] == "nao_fundamentado"


def test_sintese_erro_cli_nao_estoura():
    """RuntimeError do executor (CLI ausente/timeout) vira erro_sintese, jamais
    estoura para o chamador — a Fase 1 extrativa segue valendo."""
    def explode(_p):
        raise RuntimeError("Claude CLI não encontrado")
    r = rag_sintese.sintetizar("qual o prazo?", _TRECHOS, modo="claude_cli",
                               _executor=explode)
    assert r["sintese_disponivel"] is False
    assert r["motivo"] == "erro_sintese"
    assert "Claude CLI" in r["detalhe"]


def test_sintese_modo_api_sem_executor_é_todo():
    """Sem executor injetado, modo 'api' degrada via RuntimeError → erro_sintese."""
    r = rag_sintese.sintetizar("qual o prazo?", _TRECHOS, modo="api")
    assert r["sintese_disponivel"] is False
    assert r["motivo"] == "erro_sintese"


# --------- Fase 2: endpoint com sintetizar=true (monkeypatch, sem CLI) ---------

def test_endpoint_perguntar_com_sintese(client, con, cliente_fake, monkeypatch):
    pid = _criar_pregao(con)
    monkeypatch.setattr(extracao, "extrair_paginas", lambda _p: PAGINAS)
    monkeypatch.setattr(matching, "embed_padrao", EmbedFake())
    import app.pncp as pncp_mod
    monkeypatch.setattr(pncp_mod, "cliente", lambda: cliente_fake)
    # síntese fake: nunca chama o claude real
    monkeypatch.setattr(
        rag, "_sintetizar_padrao",
        lambda pergunta, trechos: {"sintese_disponivel": True,
                                   "resposta": "O prazo é 30 dias.",
                                   "trechos_citados": [1], "modo": "fake",
                                   "fonte": "IA local sobre os trechos do edital"},
    )
    client.post(f"/pregoes/{pid}/rag/indexar")

    r = client.post(f"/pregoes/{pid}/rag/perguntar",
                    json={"pergunta": "qual o prazo de entrega?", "sintetizar": True})
    assert r.status_code == 200
    dados = r.json()
    assert dados["disponivel"] is True
    assert dados["trechos"], "os trechos seguem presentes"
    assert dados["sintese"]["sintese_disponivel"] is True
    assert dados["sintese"]["resposta"] == "O prazo é 30 dias."


def test_endpoint_perguntar_sem_sintese_default(client, con, cliente_fake, monkeypatch):
    """Sem sintetizar no body → Fase 1 pura (sem bloco 'sintese')."""
    pid = _criar_pregao(con)
    monkeypatch.setattr(extracao, "extrair_paginas", lambda _p: PAGINAS)
    monkeypatch.setattr(matching, "embed_padrao", EmbedFake())
    import app.pncp as pncp_mod
    monkeypatch.setattr(pncp_mod, "cliente", lambda: cliente_fake)
    client.post(f"/pregoes/{pid}/rag/indexar")

    r = client.post(f"/pregoes/{pid}/rag/perguntar",
                    json={"pergunta": "qual o prazo de entrega?"})
    assert r.status_code == 200
    assert "sintese" not in r.json()


# --------- Busca híbrida: BM25 (FTS5) + e5 fundidos por RRF ---------

# Cenário de RECALL controlado. O alvo (cláusula com "prazo de entrega") recebe
# cosseno fake LIGEIRAMENTE menor que vários decoys semanticamente próximos;
# sem hibridização ele cai FORA do top-k vetorial. O BM25 casa o termo exato e o
# RRF traz o alvo de volta ao topo. Embed fake (2D, ângulos controlados) — nunca
# o e5 real; o FTS5 é REAL (determinístico, sem modelo).
import math

# páginas: cada uma vira ≥1 chunk próprio (separadas por linha em branco). O
# ALVO ("prazo de entrega") fica entre decoys que NÃO contêm esse termo exato
# mas falam do mesmo assunto (logística/cronograma) — alto cosseno, zero match
# léxico no termo da pergunta.
_PG_ALVO = "2.1 O prazo de entrega dos produtos é de 30 (trinta) dias corridos.\n"
_PG_DECOY1 = "5.1 O cronograma de fornecimento segue o anexo logístico II.\n"
_PG_DECOY2 = "5.2 A logística de remessa observa o calendário do anexo III.\n"
_PG_DECOY3 = "5.3 O fornecimento programado consta no plano de remessas IV.\n"
_PAGINAS_RECALL = [_PG_ALVO, _PG_DECOY1, _PG_DECOY2, _PG_DECOY3]


class EmbedRecallFake:
    """Embed 2D determinístico que dá ao ALVO um cosseno < ao dos decoys.

    A pergunta é o vetor de referência (ângulo 0). Cada chunk recebe um ângulo:
    decoys bem próximos (cosseno ~0.97–0.99) e o alvo mais distante (~0.70).
    Assim, em top-k pequeno, o alvo fica de FORA na recuperação só-vetor — é o
    BM25 + RRF que o resgata.
    """

    def _ang(self, corpo: str) -> float:
        t = corpo.lower()
        if "prazo de entrega" in t:
            return math.radians(45)   # alvo: cosseno ~0.707 com a pergunta
        if "cronograma" in t:
            return math.radians(8)    # decoy: cosseno ~0.990
        if "logística" in t or "logistica" in t:
            return math.radians(10)   # decoy: ~0.985
        if "fornecimento programado" in t:
            return math.radians(12)   # decoy: ~0.978
        return math.radians(90)       # fora do tema: ortogonal

    def __call__(self, textos):
        out = []
        for t in textos:
            corpo = t.split(": ", 1)[-1]
            if corpo == "qual o prazo de entrega dos produtos?":
                ang = 0.0  # a pergunta é a referência
            else:
                ang = self._ang(corpo)
            out.append([math.cos(ang), math.sin(ang)])
        return out


def test_hibrido_recall_traz_alvo_que_so_vetor_perderia(con, monkeypatch):
    """RECALL: com k pequeno, a recuperação só-vetor deixaria o alvo de fora
    (decoys têm cosseno maior); a hibridização (BM25 casa 'prazo de entrega' +
    RRF) traz o alvo de volta ao topo."""
    pid = _criar_pregao(con)
    embed = EmbedRecallFake()
    rag.indexar_chunks(con, pid, [(None, _PAGINAS_RECALL)], embed=embed)
    pergunta = "qual o prazo de entrega dos produtos?"

    # baseline SÓ-VETOR: força a ausência do FTS → o alvo cai de fora do top-2.
    monkeypatch.setattr(rag, "_FTS_FORCE_OFF", True)
    so_vetor = rag.perguntar(con, pid, pergunta, k=2, embed=embed)
    textos_vetor = [t["texto"].lower() for t in so_vetor["trechos"]]
    assert not any("prazo de entrega" in x for x in textos_vetor), \
        "baseline: só-vetor (k=2) NÃO deveria trazer o alvo (decoys vencem)"

    # HÍBRIDO: reabilita o FTS (o indexar já o populou) e refaz a pergunta.
    monkeypatch.setattr(rag, "_FTS_FORCE_OFF", False)
    hibrido = rag.perguntar(con, pid, pergunta, k=2, embed=embed)
    assert hibrido["disponivel"] is True
    textos_hib = [t["texto"].lower() for t in hibrido["trechos"]]
    assert any("prazo de entrega" in x for x in textos_hib), \
        "híbrido: BM25 + RRF deveriam trazer o alvo ao top-k"
    # o alvo veio do ranking léxico (sozinho ou junto do vetor)
    alvo = next(t for t in hibrido["trechos"] if "prazo de entrega" in t["texto"].lower())
    assert alvo["fonte_rank"] in ("lexico", "ambos")
    # shape da Fase 1 preservado (frontend não quebra)
    assert "score" in alvo and "pagina" in alvo and "offset_inicio" in alvo


def test_hibrido_off_topic_continua_nao_encontrado(con):
    """Honestidade: pergunta fora do tema não casa o FTS (só conteúdo, sem
    stopwords) nem tem cosseno alto → nao_encontrado (não regride)."""
    pid = _criar_pregao(con)
    embed = EmbedFake()
    rag.indexar_chunks(con, pid, [(None, PAGINAS)], embed=embed)
    r = rag.perguntar(con, pid, "qual a cor do papel timbrado?", embed=embed)
    assert r["disponivel"] is False
    assert r["motivo"] == "nao_encontrado"
    assert r["trechos"] == []


def test_gate_semantico_rejeita_match_so_lexico_generico(con):
    """REGRESSÃO (achado do eval M7, MELHORIAS §2.0): um termo genérico
    compartilhado faz o FTS casar, mas SEM cosseno semântico ≥ threshold o gate
    NÃO abre. 'município' aparece na PÁGINA_1 (FTS casa), porém a pergunta é fora
    do tema semântico (EmbedFake → eixo _FORA, cosseno 0). Gate semântico-
    primário → nao_encontrado, apesar do match léxico (antes vazava)."""
    pid = _criar_pregao(con)
    embed = EmbedFake()
    rag.indexar_chunks(con, pid, [(None, PAGINAS)], embed=embed)
    r = rag.perguntar(con, pid, "qual o município responsável?", embed=embed)
    assert r["disponivel"] is False
    assert r["motivo"] == "nao_encontrado"
    assert r["trechos"] == []


def test_fts_populado_no_indexar_e_idempotente(con):
    """O FTS é populado no indexar e reindexar não duplica linhas (idempotente,
    espelha o DELETE de rag_chunks)."""
    pid = _criar_pregao(con)
    embed = EmbedFake()
    rag.indexar_chunks(con, pid, [(None, PAGINAS)], embed=embed)
    n_chunks = con.execute(
        "SELECT COUNT(*) c FROM rag_chunks WHERE pregao_id=?", (pid,)
    ).fetchone()["c"]
    n_fts1 = con.execute(
        "SELECT COUNT(*) c FROM rag_fts WHERE pregao_id=?", (pid,)
    ).fetchone()["c"]
    assert n_fts1 == n_chunks, "uma linha FTS por chunk"
    # cada linha FTS referencia um chunk_id real
    ids_chunks = {r["id"] for r in con.execute(
        "SELECT id FROM rag_chunks WHERE pregao_id=?", (pid,)).fetchall()}
    ids_fts = {r["chunk_id"] for r in con.execute(
        "SELECT chunk_id FROM rag_fts WHERE pregao_id=?", (pid,)).fetchall()}
    assert ids_fts == ids_chunks
    # reindexar não duplica
    rag.indexar_chunks(con, pid, [(None, PAGINAS)], embed=embed)
    n_fts2 = con.execute(
        "SELECT COUNT(*) c FROM rag_fts WHERE pregao_id=?", (pid,)
    ).fetchone()["c"]
    assert n_fts2 == n_fts1


def test_degradacao_sem_fts_funciona_so_vetor(con, monkeypatch):
    """Sem FTS (build sem o módulo, simulado forçando indisponível), perguntar
    ainda funciona em modo só-vetor — comportamento idêntico à Fase 1."""
    pid = _criar_pregao(con)
    embed = EmbedFake()
    # simula ambiente SEM FTS5: _fts_disponivel devolve False, o indexar não
    # popula o FTS e perguntar cai no caminho só-vetor.
    monkeypatch.setattr(rag, "_FTS_FORCE_OFF", True)
    rag.indexar_chunks(con, pid, [(None, PAGINAS)], embed=embed)
    # sem FTS5, nenhuma tabela rag_fts foi populada (e nem precisa existir)
    r = rag.perguntar(con, pid, "qual o prazo de entrega?", embed=embed)
    assert r["disponivel"] is True
    assert any("prazo de entrega" in t["texto"].lower() for t in r["trechos"])
    # todos os trechos vieram só do vetor (sem léxico disponível)
    assert all(t["fonte_rank"] == "vetor" for t in r["trechos"])


def test_sanitizar_match_descarta_stopwords_e_termos_curtos(con):
    """O MATCH usa só termos de CONTEÚDO (sem stopwords/1-char). Cada termo vem
    entre aspas (string FTS5), o que neutraliza pontuação como sintaxe."""
    assert rag._sanitizar_match("qual o prazo de entrega?") == '"prazo" OR "entrega"'
    # só stopwords / 1-char → vazio (gate cai no critério semântico)
    assert rag._sanitizar_match("qual o de a o e?") == ""
    # pergunta com aspas/operadores não estoura o FTS5 (termos entre aspas) e
    # ainda casa o conteúdo — exercita o MATCH de verdade contra o índice.
    pid = _criar_pregao(con)
    rag.indexar_chunks(con, pid, [(None, PAGINAS)], embed=EmbedFake())
    ids = rag._buscar_fts(con, pid, 'qual a "garantia" AND OR mínima?')
    assert ids, "deveria casar o chunk de garantia sem quebrar a sintaxe"


# --------- helpers ---------

def _criar_pregao(con) -> int:
    cur = con.execute(
        """INSERT INTO pregoes (cnpj, ano, seq, numero_controle, titulo)
           VALUES ('01613770000172', 2026, 67, 'NC-RAG-1', 'Pregão RAG teste')"""
    )
    con.commit()
    return cur.lastrowid
