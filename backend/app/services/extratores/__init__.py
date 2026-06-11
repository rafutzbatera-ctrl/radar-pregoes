"""Extratores plugáveis de requisitos de habilitação (CLAUDE.md §6.3).

Três modos, todos devolvendo `list[RequisitoHabilitacao]`:
- "heuristico": regras locais, sem IA (padrão — não precisa de chave).
- "api": Anthropic API via instructor.
- "claude_cli": Claude Code CLI headless via subprocess.

O dispatcher escolhe pelo parâmetro `modo` ou, na ausência dele, por
`settings.EXTRATOR_HABILITACAO`. Modo desconhecido → ValueError claro.
"""
import logging

from ... import settings
from ..habilitacao import RequisitoHabilitacao

log = logging.getLogger("radar.extratores")

MODOS = ("heuristico", "api", "claude_cli")


def extrair(paginas: list[str], modo: str | None = None) -> list[RequisitoHabilitacao]:
    modo = modo or settings.EXTRATOR_HABILITACAO
    if modo == "heuristico":
        from . import heuristico
        return heuristico.extrair(paginas)
    if modo == "api":
        from . import llm_api
        return llm_api.extrair(paginas)
    if modo == "claude_cli":
        from . import claude_cli
        return claude_cli.extrair(paginas)
    raise ValueError(
        f"Modo de extração inválido: {modo!r}. "
        f"Use um de {MODOS} (config RADAR_EXTRATOR)."
    )
