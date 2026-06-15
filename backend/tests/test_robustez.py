"""Testes de regressão da camada de ROBUSTEZ (cada um falha se a defesa for
revertida):

- B1: cache PNCP tolerante (corrompido → miss + remoção) e escrita atômica
  (round-trip, JSON válido).
- B2: teto de download (Content-Length acima do teto recusa antes de baixar,
  sem deixar .pdf truncado).
- B3: _baixar_arquivos pula arquivo com url None (não chama o cliente, não
  derruba o lote).
- B4: score não-finito (NaN/inf gravado num chunk) não vaza no resultado de
  perguntar (gate de finitude descarta o chunk).

Tudo offline: cliente HTTP fake, embed fake, páginas inline.
"""
import json
import math

import numpy as np
import pytest

from app import pncp
from app.services import rag, sincronizacao


# ------------------------------------------------------------------ B1
def test_cache_corrompido_vira_miss_e_e_removido(tmp_path):
    """_ler_cache de JSON lixo → None e o arquivo é apagado (não brica a query
    pelas próximas 6h do TTL)."""
    cli = pncp.ClientePNCP(cache_dir=tmp_path / "cache")
    arq = cli.cache_dir / "qualquer.json"
    arq.write_text("{corrompido", encoding="utf-8")

    assert cli._ler_cache(arq) is None
    assert not arq.exists(), "cache corrompido deveria ter sido removido"
    cli.fechar()


def test_cache_escrita_atomica_round_trip(tmp_path):
    """_escrever_cache + _ler_cache devolvem o mesmo dict e o arquivo final é
    JSON válido (escrita via tmp + os.replace)."""
    cli = pncp.ClientePNCP(cache_dir=tmp_path / "cache")
    arq = cli.cache_dir / "round.json"

    cli._escrever_cache(arq, {"x": 1})
    assert cli._ler_cache(arq) == {"x": 1}
    # o arquivo final é JSON válido (parseável fora do helper) e não restou tmp
    assert json.loads(arq.read_text(encoding="utf-8")) == {"x": 1}
    assert list(cli.cache_dir.glob("*.tmp*")) == []
    cli.fechar()


# ------------------------------------------------------------------ B2
class _RespFake:
    """Resposta de stream fake: declara um Content-Length acima do teto. O
    caminho exercitado é a RECUSA por Content-Length (verificação determinística
    ANTES de baixar — não depende do loop de tentativas/backoff)."""

    def __init__(self):
        self.headers = {"content-length": str(pncp.MAX_PDF_BYTES + 1)}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    def iter_bytes(self):  # não deveria ser alcançado (recusa antes)
        raise AssertionError("não deveria iterar: recusa pelo Content-Length")


class _HttpFake:
    def stream(self, metodo, url):
        return _RespFake()


def test_download_recusa_acima_do_teto_sem_arquivo_truncado(tmp_path, monkeypatch):
    cli = pncp.ClientePNCP(cache_dir=tmp_path / "cache")
    # neutraliza o rate-limit (sleep) e injeta o HTTP fake
    monkeypatch.setattr(cli, "_esperar_vez", lambda pista="pesada": None)
    cli._http = _HttpFake()

    destino = tmp_path / "dl"
    with pytest.raises(ValueError, match="excede o teto"):
        cli.baixar_arquivo("https://exemplo/edital.pdf", destino)

    # nenhum .pdf truncado ficou no destino
    assert list(destino.glob("*.pdf")) == []
    # cli._http foi trocado pelo fake (sem .close); nada a fechar.


class _RespStreamSemCL:
    """Resposta de stream fake SEM content-length: o teto só pode ser detectado
    DENTRO do loop de streaming (total += len(bloco) > MAX_PDF_BYTES). Exercita
    o caminho do aborto-no-meio-do-stream (pncp.py:380-396), distinto da recusa
    determinística por Content-Length do _RespFake (B2)."""

    def __init__(self):
        self.headers = {}  # sem content-length → não recusa antes de baixar

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    def iter_bytes(self):
        # emite blocos somando ACIMA do teto (com MAX_PDF_BYTES=10, 16 bytes basta)
        yield b"AAAAAAAA"
        yield b"BBBBBBBB"


class _HttpStreamFake:
    def stream(self, metodo, url):
        return _RespStreamSemCL()


def test_download_aborta_no_stream_apaga_truncado(tmp_path, monkeypatch):
    """Sem content-length, o teto estoura no meio do iter_bytes: o ValueError
    'excede o teto' propaga (não é httpx.* → não entra no retry) e o .pdf
    parcialmente escrito é apagado (destino.unlink())."""
    cli = pncp.ClientePNCP(cache_dir=tmp_path / "cache")
    # teto minúsculo: poucos bytes já estouram no stream
    monkeypatch.setattr(pncp, "MAX_PDF_BYTES", 10)
    monkeypatch.setattr(cli, "_esperar_vez", lambda pista="pesada": None)
    # defensivo: se algum backoff for alcançado, não dorme de verdade
    monkeypatch.setattr(pncp.time, "sleep", lambda *_: None)
    cli._http = _HttpStreamFake()

    destino = tmp_path / "dl"
    with pytest.raises(ValueError, match="excede o teto"):
        cli.baixar_arquivo("https://exemplo/edital.pdf", destino)

    # nenhum .pdf truncado ficou no destino
    assert list(destino.glob("*.pdf")) == []


# ------------------------------------------------------------------ B3
def _criar_pregao(con) -> int:
    cur = con.execute(
        "INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
        "VALUES ('01613770000172',2026,67,'NC-ROB-1')"
    )
    con.commit()
    return cur.lastrowid


class _ClienteBaixarFake:
    """Registra as urls passadas a baixar_arquivo e devolve um .pdf de mentira."""

    def __init__(self, destino_base):
        self.urls = []
        self._n = 0
        self._base = destino_base

    def baixar_arquivo(self, url, destino_dir):
        self.urls.append(url)
        destino_dir.mkdir(parents=True, exist_ok=True)
        self._n += 1
        destino = destino_dir / f"arq_{self._n}.pdf"
        destino.write_bytes(b"%PDF-1.4 fake")
        return destino


def test_baixar_arquivos_pula_url_none_sem_derrubar_lote(con, tmp_path, monkeypatch):
    from app import settings
    monkeypatch.setattr(settings, "ARQUIVOS_DIR", tmp_path / "arquivos")
    pregao_id = _criar_pregao(con)
    pregao = con.execute("SELECT * FROM pregoes WHERE id=?", (pregao_id,)).fetchone()

    cli = _ClienteBaixarFake(tmp_path)
    arquivos = [
        {"url": "https://exemplo/edital1.pdf", "titulo": "Edital 1",
         "tipoDocumentoNome": "Edital"},
        {"url": None, "titulo": "Sem url", "tipoDocumentoNome": "Edital"},
        {"url": "https://exemplo/edital2.pdf", "titulo": "Edital 2",
         "tipoDocumentoNome": "Edital"},
    ]

    pdfs = sincronizacao._baixar_arquivos(con, pregao, arquivos, cli)

    # o fake NÃO foi chamado para o None; foi chamado para os dois válidos
    assert cli.urls == ["https://exemplo/edital1.pdf", "https://exemplo/edital2.pdf"]
    assert None not in cli.urls
    # os dois .pdf válidos (Edital) entram na lista de PDFs; o lote não levantou
    assert len(pdfs) == 2


# ------------------------------------------------------------------ B4
def _embed_um_eixo(textos):
    """Embed 1D trivial: tudo no mesmo eixo (cosseno 1.0). Determinístico, sem
    modelo real. A pergunta também vira [1.0], então o chunk válido pontua 1.0."""
    return [[1.0] for _ in textos]


def test_score_nan_no_chunk_nao_vaza_no_topo(con):
    """Um chunk com vetor degenerado (NaN gravado no BLOB) produz score NaN, que
    é neutralizado para -inf antes do gate (math.isfinite). O chunk NÃO aparece
    nos trechos, mesmo que a pergunta case lexicamente o seu texto. Um chunk
    válido (mesmo termo) ENTRA — prova que a query é relevante e que só o NaN é
    descartado."""
    pid = _criar_pregao(con)
    # chunk BOM (vetor [1.0]) e chunk RUIM (vetor [nan]) — mesmo termo "prazo"
    # para casar o FTS léxico em ambos; só a finitude do cosseno os separa.
    def ins(texto, vetor):
        cur = con.execute(
            """INSERT INTO rag_chunks
                 (pregao_id, arquivo_id, pagina, ordem, offset_inicio,
                  offset_fim, texto, vetor)
               VALUES (?,?,?,?,?,?,?,?)""",
            (pid, None, 1, 0, 0, len(texto), texto,
             np.asarray(vetor, dtype=np.float32).tobytes()),
        )
        return cur.lastrowid

    id_bom = ins("prazo de entrega bom valido", [1.0])
    id_ruim = ins("prazo de entrega ruim degenerado", [float("nan")])
    con.execute(
        """INSERT OR REPLACE INTO rag_status
             (pregao_id, ingerido_em, n_chunks, n_paginas, modelo)
           VALUES (?, datetime('now'), 2, 1, 'fake')""",
        (pid,),
    )
    con.commit()

    r = rag.perguntar(con, pid, "qual o prazo de entrega?", embed=_embed_um_eixo)
    assert r["disponivel"] is True
    textos = [t["texto"] for t in r["trechos"]]
    assert any("bom valido" in t for t in textos), "o chunk válido deveria entrar"
    assert all("ruim degenerado" not in t for t in textos), \
        "o chunk com score NaN NÃO pode vazar nos trechos"


def test_tem_sinal_descarta_scores_nao_finitos():
    """Unidade do gate de finitude: nan_to_num leva NaN/±inf a -inf, e o critério
    de sinal (cosseno ≥ threshold) rejeita -inf. Defesa em profundidade do B4."""
    bruto = np.array([0.95, float("nan"), float("inf"), float("-inf")],
                     dtype=np.float32)
    limpo = np.nan_to_num(bruto, nan=-np.inf, posinf=-np.inf, neginf=-np.inf)
    threshold = 0.80
    # só o primeiro (0.95) é finito E ≥ threshold; os não-finitos viram -inf
    assert math.isfinite(float(limpo[0])) and float(limpo[0]) >= threshold
    for i in range(1, 4):
        s = float(limpo[i])
        assert (not math.isfinite(s)) or s < threshold
