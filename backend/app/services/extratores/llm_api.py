"""Extrator via Anthropic API + instructor (saída Pydantic validada).

Modo "api" (CLAUDE.md §3/§6.3). Precisa de ANTHROPIC_API_KEY no .env; é o único
modo que depende da chave. Mesmo comportamento do código que vivia em
habilitacao.py — apenas movido para cá com a separação dos extratores.
"""
import logging

from ... import settings
from ..habilitacao import RequisitoHabilitacao

log = logging.getLogger("radar.extratores.llm_api")


PROMPT_SISTEMA = """Você extrai requisitos de habilitação de editais de licitação \
(Lei 14.133/2021) para um fornecedor que disputa pregões.

REGRAS INEGOCIÁVEIS:
1. Extraia SOMENTE o que está escrito no texto fornecido. Nunca complete com \
conhecimento próprio sobre o que editais "costumam" exigir.
2. O campo `excerto` deve ser um trecho LITERAL copiado do texto, sem parafrasear, \
sem corrigir ortografia, sem completar frases. Curto (1 a 3 frases) e suficiente \
para comprovar a exigência.
3. `pagina` é o número da página marcado no texto como [página N].
4. Se o edital não tiver seção de habilitação ou documentos exigidos, retorne lista \
VAZIA — isso é permitido e correto.
5. Categorias: juridica (atos constitutivos, declarações societárias), fiscal \
(certidões de regularidade fiscal/trabalhista/FGTS), tecnica (atestados de \
capacidade), economico_financeira (balanço, certidão de falência), proposta \
(validade, forma de apresentação) e outros."""


def _texto_paginado(paginas: list[str]) -> str:
    return "\n\n".join(
        f"[página {n}]\n{conteudo}" for n, conteudo in enumerate(paginas, start=1)
    )


def extrair(paginas: list[str], modelo: str | None = None) -> list[RequisitoHabilitacao]:
    """Chama o LLM via instructor (saída Pydantic validada)."""
    import anthropic
    import instructor

    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY ausente no .env — necessária no modo 'api'. "
            "Use RADAR_EXTRATOR=heuristico para extração local sem IA."
        )

    cliente = instructor.from_anthropic(
        anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    )
    return cliente.messages.create(
        model=modelo or settings.LLM_MODEL,
        max_tokens=8192,
        system=PROMPT_SISTEMA,
        messages=[{
            "role": "user",
            "content": ("Extraia os requisitos de habilitação deste edital:\n\n"
                        + _texto_paginado(paginas)),
        }],
        response_model=list[RequisitoHabilitacao],
    )
