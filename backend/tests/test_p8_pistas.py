"""P8 — fila em DUAS PISTAS no ClientePNCP (CLAUDE.md §2 princípio 6 atualizado).

Pista interativa (0,3s): buscar/consulta/detalhe/arquivos.
Pista pesada (1,0s): itens/baixar_arquivo.
As pistas têm lock + último_ts próprios → a interativa NÃO espera atrás da pesada.

Relógio FAKE controlável: cada `time.sleep(s)` avança o `time.monotonic()` fake
em `s`. Assim conseguimos medir, de forma determinística, quanto cada pista fez
o cliente esperar — sem dormir de verdade e sem depender do relógio do sistema.
Os testes existentes monkeypatcham `time.sleep` para no-op; aqui instalamos um
relógio próprio coerente (sleep + monotonic andam juntos).
"""
import time

import httpx

from app import pncp


class RelogioFake:
    """sleep(s) e monotonic() compartilham o mesmo tempo simulado."""

    def __init__(self):
        self.agora = 1000.0  # base arbitrária > 0
        self.dormidas = []   # histórico de quanto cada sleep pediu

    def monotonic(self):
        return self.agora

    def sleep(self, s):
        # negativos/zero não andam (espelha time.sleep real)
        if s and s > 0:
            self.agora += s
        self.dormidas.append(s)

    def avancar(self, s):
        """Avança o relógio sem passar pelo sleep (simula tempo de rede/IO)."""
        self.agora += s


def _instalar_relogio(monkeypatch):
    rel = RelogioFake()
    monkeypatch.setattr(time, "monotonic", rel.monotonic)
    monkeypatch.setattr(time, "sleep", rel.sleep)
    return rel


def _cliente(tmp_path, handler):
    cli = pncp.ClientePNCP(cache_dir=tmp_path)
    cli._http = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": "teste"},
    )
    return cli


def _handler_ok(json_resp):
    def handler(request):
        return httpx.Response(200, json=json_resp)
    return handler


def test_pista_interativa_espera_03s_entre_chamadas(tmp_path, monkeypatch):
    """Duas chamadas seguidas na pista interativa esperam ~0,3s entre si."""
    rel = _instalar_relogio(monkeypatch)
    cli = _cliente(tmp_path, _handler_ok({"items": [], "total": 0}))

    cli.buscar("a", usar_cache=False)   # primeira: não espera (último_ts era 0)
    t0 = rel.agora
    cli.buscar("b", usar_cache=False)   # segunda: deve esperar o intervalo da pista
    esperou = rel.agora - t0

    assert abs(esperou - pncp._INTERVALO_INTERATIVA) < 1e-6
    assert abs(esperou - 0.3) < 1e-6


def test_pista_pesada_espera_10s_entre_chamadas(tmp_path, monkeypatch):
    """Duas chamadas seguidas na pista pesada esperam ~1,0s entre si.

    `itens` pagina internamente: com 100 itens no lote ele busca a 2ª página,
    então a 2ª requisição da MESMA pista pesada espera o intervalo.
    """
    rel = _instalar_relogio(monkeypatch)
    # lote cheio (100) força a 2ª página → 2 requisições na pista pesada
    lote_cheio = [{"numeroItem": i} for i in range(100)]
    estado = {"n": 0}

    def handler(request):
        estado["n"] += 1
        # 1ª página cheia (dispara 2ª); 2ª página vazia (encerra)
        corpo = lote_cheio if estado["n"] == 1 else []
        return httpx.Response(200, json=corpo)

    cli = _cliente(tmp_path, handler)

    t0 = rel.agora
    cli.itens("123", 2026, 1, usar_cache=False)
    esperou_total = rel.agora - t0

    # 1ª req não espera; 2ª espera 1,0s → total ≈ 1,0s
    assert estado["n"] == 2
    assert abs(esperou_total - pncp._INTERVALO_PESADA) < 1e-6
    assert abs(esperou_total - 1.0) < 1e-6


def test_interativa_nao_espera_atras_da_pesada(tmp_path, monkeypatch):
    """Locks independentes: a interativa não soma o intervalo da pesada.

    Simulamos a pesada RECÉM-OCUPADA (último_ts = agora). Se as pistas
    partilhassem o relógio, a interativa dormiria ~1,0s; com pistas separadas,
    ela só respeita o próprio intervalo (e aqui, sendo a 1ª da pista interativa,
    nem espera).
    """
    rel = _instalar_relogio(monkeypatch)
    cli = _cliente(tmp_path, _handler_ok({"items": [], "total": 0}))

    # pesada acabou de rodar (como se um lote de itens tivesse disparado agora)
    cli._pistas["pesada"]["ultima"] = rel.agora

    t0 = rel.agora
    cli.buscar("a", usar_cache=False)   # interativa, primeira da pista
    esperou = rel.agora - t0

    # NÃO somou o 1,0s da pesada (locks/relógios separados)
    assert esperou == 0.0
    assert esperou < pncp._INTERVALO_PESADA


def test_pesada_nao_espera_atras_da_interativa(tmp_path, monkeypatch):
    """Simétrico: a pesada não herda o relógio da interativa recém-usada."""
    rel = _instalar_relogio(monkeypatch)
    cli = _cliente(tmp_path, _handler_ok([]))   # itens vazios → 1 requisição

    cli._pistas["interativa"]["ultima"] = rel.agora  # interativa recém-ocupada

    t0 = rel.agora
    cli.itens("123", 2026, 1, usar_cache=False)
    esperou = rel.agora - t0

    assert esperou == 0.0  # pesada não esperou o tempo da interativa


def test_arquivos_usa_pista_interativa(tmp_path, monkeypatch):
    """`arquivos` (metadados) corre na pista interativa: 2ª chamada espera só 0,3s."""
    rel = _instalar_relogio(monkeypatch)
    cli = _cliente(tmp_path, _handler_ok([{"titulo": "Edital"}]))

    cli.arquivos("123", 2026, 1, usar_cache=False)
    t0 = rel.agora
    cli.arquivos("123", 2026, 2, usar_cache=False)
    esperou = rel.agora - t0

    assert abs(esperou - pncp._INTERVALO_INTERATIVA) < 1e-6
