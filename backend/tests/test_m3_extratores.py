"""M3 — dispatcher de extratores e o modo claude_cli (subprocess monkeypatchado).

Cobre: escolha de modo explícito vs settings; modo inválido → ValueError;
parsing do envelope JSON do CLI (com e sem cerca ```json```); CLI ausente →
RuntimeError acionável; item inválido descartado sem exceção."""
import json
import subprocess
import types

import pytest

from app import settings
from app.services import extratores
from app.services.extratores import claude_cli
from app.services.habilitacao import RequisitoHabilitacao

PAGINAS = ["9. DA HABILITAÇÃO\n9.1 Apresentar certidão negativa de débitos federais."]


# ---------- dispatcher ----------

def test_dispatcher_modo_explicito(monkeypatch):
    chamado = {}
    def fake(paginas):
        chamado["ok"] = paginas
        return []
    import app.services.extratores.heuristico as h
    monkeypatch.setattr(h, "extrair", fake)
    extratores.extrair(PAGINAS, modo="heuristico")
    assert chamado["ok"] == PAGINAS


def test_dispatcher_respeita_settings(monkeypatch):
    monkeypatch.setattr(settings, "EXTRATOR_HABILITACAO", "heuristico")
    marca = {}
    import app.services.extratores.heuristico as h
    monkeypatch.setattr(h, "extrair", lambda paginas: marca.setdefault("via", "settings") or [])
    extratores.extrair(PAGINAS)  # sem modo → usa settings
    assert marca["via"] == "settings"


def test_dispatcher_modo_invalido():
    with pytest.raises(ValueError) as exc:
        extratores.extrair(PAGINAS, modo="banana")
    assert "banana" in str(exc.value)


# ---------- claude_cli ----------

_ARRAY_VALIDO = [
    {"requisito": "Certidão negativa de débitos federais (RFB/PGFN)",
     "categoria": "fiscal", "obrigatorio": True, "pagina": 1,
     "excerto": "Apresentar certidão negativa de débitos federais."},
]


def _proc(stdout, returncode=0, stderr=""):
    return types.SimpleNamespace(stdout=stdout, returncode=returncode, stderr=stderr)


def test_claude_cli_envelope_json_valido(monkeypatch):
    envelope = json.dumps({"result": json.dumps(_ARRAY_VALIDO)})
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(envelope))
    reqs = claude_cli.extrair(PAGINAS)
    assert len(reqs) == 1
    assert isinstance(reqs[0], RequisitoHabilitacao)
    assert reqs[0].categoria == "fiscal"


def test_claude_cli_array_dentro_de_cerca(monkeypatch):
    resultado_com_cerca = "Aqui está:\n```json\n" + json.dumps(_ARRAY_VALIDO) + "\n```\n"
    envelope = json.dumps({"result": resultado_com_cerca})
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(envelope))
    reqs = claude_cli.extrair(PAGINAS)
    assert len(reqs) == 1
    assert reqs[0].requisito.startswith("Certidão negativa de débitos federais")


def test_claude_cli_nao_encontrado(monkeypatch):
    def raise_fnf(*a, **k):
        raise FileNotFoundError("claude")
    monkeypatch.setattr(subprocess, "run", raise_fnf)
    with pytest.raises(RuntimeError) as exc:
        claude_cli.extrair(PAGINAS)
    assert "RADAR_EXTRATOR=heuristico" in str(exc.value)


def test_claude_cli_exit_nao_zero(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc("", returncode=2, stderr="login required"))
    with pytest.raises(RuntimeError) as exc:
        claude_cli.extrair(PAGINAS)
    assert "RADAR_EXTRATOR=heuristico" in str(exc.value)


def test_claude_cli_argv_desarmado(monkeypatch):
    """SEGURANÇA: o CLI roda sem ferramentas (--max-turns 1 + --disallowedTools).

    Texto de edital é conteúdo não-confiável; o agente tem que ficar desarmado
    para não cair em prompt injection (Bash/Write/etc. precisam estar bloqueados).
    """
    capturado = {}
    def fake_run(comando, *a, **k):
        capturado["comando"] = comando
        return _proc(json.dumps({"result": json.dumps(_ARRAY_VALIDO)}))
    monkeypatch.setattr(subprocess, "run", fake_run)
    claude_cli.extrair(PAGINAS)
    comando = capturado["comando"]
    assert "--max-turns" in comando
    assert "--disallowedTools" in comando
    # a lista de bloqueio é o argumento logo após --disallowedTools
    bloqueados = comando[comando.index("--disallowedTools") + 1]
    assert "Bash" in bloqueados
    # nunca pular permissões
    assert "--dangerously-skip-permissions" not in comando


def test_claude_cli_timeout_vira_runtimeerror(monkeypatch):
    def raise_timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=600)
    monkeypatch.setattr(subprocess, "run", raise_timeout)
    with pytest.raises(RuntimeError) as exc:
        claude_cli.extrair(PAGINAS)
    assert "timeout" in str(exc.value).lower()


def test_claude_cli_item_invalido_descartado(monkeypatch):
    array = [
        _ARRAY_VALIDO[0],
        {"requisito": "X", "categoria": "categoria_inexistente",  # inválido p/ Literal
         "obrigatorio": True, "pagina": 1, "excerto": "..."},
        {"foo": "bar"},  # faltam campos
    ]
    envelope = json.dumps({"result": json.dumps(array)})
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _proc(envelope))
    reqs = claude_cli.extrair(PAGINAS)  # não explode
    assert len(reqs) == 1  # só o item válido sobrevive
    assert reqs[0].categoria == "fiscal"
