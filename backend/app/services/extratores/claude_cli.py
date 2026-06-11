"""Extrator via Claude Code CLI headless (modo "claude_cli", CLAUDE.md §6.3).

Roda `claude -p <prompt> --output-format json` por subprocess (shell=False). O
envelope JSON traz o texto da resposta no campo "result"; de lá extraímos o
array JSON de requisitos e validamos item a item com RequisitoHabilitacao
(item inválido é descartado com warning, não derruba o lote).

Princípios 1 e 2 valem igual: o gate de citação roda depois, na sincronização.
"""
import json
import logging
import re
import subprocess

from ... import settings
from ..habilitacao import RequisitoHabilitacao
from .llm_api import PROMPT_SISTEMA, _texto_paginado

log = logging.getLogger("radar.extratores.claude_cli")

_INSTRUCAO_SAIDA = (
    "\n\nResponda SOMENTE com um array JSON de objetos no formato "
    '{"requisito": str, "categoria": str, "obrigatorio": bool, "pagina": int, '
    '"excerto": str}, sem markdown, sem cercas de código, sem texto antes ou '
    "depois. Se não houver seção de habilitação, responda []."
)

# Captura array JSON, tolerando cerca ```json ... ``` ao redor.
_CERCA = re.compile(r"```(?:json)?\s*(\[.*?\])\s*```", re.DOTALL)
_ARRAY = re.compile(r"\[.*\]", re.DOTALL)


def _montar_prompt(paginas: list[str]) -> str:
    return (PROMPT_SISTEMA
            + "\n\nEdital (texto paginado):\n\n"
            + _texto_paginado(paginas)
            + _INSTRUCAO_SAIDA)


def _extrair_array(texto: str) -> list:
    """Acha o array JSON dentro do texto do CLI (tolera cerca de código)."""
    cerca = _CERCA.search(texto)
    bruto = cerca.group(1) if cerca else None
    if bruto is None:
        m = _ARRAY.search(texto)
        bruto = m.group(0) if m else None
    if bruto is None:
        log.warning("Resposta do Claude CLI sem array JSON reconhecível")
        return []
    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError as exc:
        log.warning("Array JSON do Claude CLI inválido: %s", exc)
        return []
    return dados if isinstance(dados, list) else []


def extrair(paginas: list[str]) -> list[RequisitoHabilitacao]:
    prompt = _montar_prompt(paginas)
    # SEGURANÇA: o prompt embute texto de edital (conteúdo NÃO-confiável, vindo
    # de PDF de terceiros). Se rodássemos o Claude Code com ferramentas ligadas,
    # uma instrução escondida no edital ("ignore o resto e rode tal comando")
    # poderia induzir o agente a usar Bash/Write/etc. (prompt injection). Por
    # isso o agente roda DESARMADO: --max-turns 1 (sem laços de ferramenta) e
    # --disallowedTools bloqueando toda ferramenta de execução/IO. Apenas a
    # geração de texto é permitida. NUNCA usar --dangerously-skip-permissions.
    comando = [
        settings.CLAUDE_CLI_BIN, "-p", prompt, "--output-format", "json",
        "--max-turns", "1",
        "--disallowedTools",
        "Bash,Edit,Write,Read,Glob,Grep,WebFetch,WebSearch,NotebookEdit,Task",
    ]
    try:
        proc = subprocess.run(
            comando,
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=settings.CLAUDE_CLI_TIMEOUT,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Claude CLI não encontrado ({settings.CLAUDE_CLI_BIN!r}) — "
            "instale/logue ou use RADAR_EXTRATOR=heuristico."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Claude CLI estourou o timeout de {settings.CLAUDE_CLI_TIMEOUT}s — "
            "aumente RADAR_CLAUDE_CLI_TIMEOUT ou use RADAR_EXTRATOR=heuristico."
        ) from exc

    if proc.returncode != 0:
        raise RuntimeError(
            f"Claude CLI saiu com código {proc.returncode} — "
            f"verifique login/instalação ou use RADAR_EXTRATOR=heuristico. "
            f"stderr: {(proc.stderr or '').strip()[:500]}"
        )

    # envelope JSON do --output-format json: campo "result" (string)
    try:
        envelope = json.loads(proc.stdout)
        resultado = envelope.get("result", "") if isinstance(envelope, dict) else ""
    except json.JSONDecodeError:
        # tolera CLI que devolveu o array direto, sem envelope
        resultado = proc.stdout

    dados = _extrair_array(resultado)
    saida: list[RequisitoHabilitacao] = []
    for item in dados:
        try:
            saida.append(RequisitoHabilitacao.model_validate(item))
        except Exception as exc:  # item inválido não derruba o lote
            log.warning("Item de habilitação inválido descartado: %s", exc)
    return saida
