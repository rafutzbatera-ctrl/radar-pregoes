"""Extrator de requisitos de habilitação via LLM + gate de citação (CLAUDE.md §6.3).

Princípios 1 e 2: NUNCA inventar. Todo requisito sai com excerto literal e
página; o gate confere se o excerto existe de fato no texto extraído do PDF
(normalização: caixa baixa + espaços colapsados). Citação que falha vira
verificada=false — nunca é descartada em silêncio, a UI mostra o aviso.
"""
import logging
import re
import sqlite3
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field

from .. import settings

log = logging.getLogger("radar.habilitacao")


class RequisitoHabilitacao(BaseModel):
    requisito: str = Field(description="Nome curto do requisito, ex.: 'Certidão negativa de débitos federais'")
    categoria: Literal["juridica", "fiscal", "tecnica",
                       "economico_financeira", "proposta", "outros"]
    obrigatorio: bool
    pagina: int = Field(description="Página do edital onde o requisito aparece (1-based)")
    excerto: str = Field(description="Trecho LITERAL do edital que exige o documento, copiado sem alteração")


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


def extrair_requisitos(paginas: list[str], modelo: str | None = None) -> list[RequisitoHabilitacao]:
    """Chama o LLM via instructor (saída Pydantic validada)."""
    import anthropic
    import instructor

    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY ausente no .env — necessário para extrair habilitação"
        )

    texto = "\n\n".join(
        f"[página {n}]\n{conteudo}" for n, conteudo in enumerate(paginas, start=1)
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
            "content": ("Extraia os requisitos de habilitação deste edital:\n\n" + texto),
        }],
        response_model=list[RequisitoHabilitacao],
    )


# ---------- gate de citação (princípio 2) ----------

def _normalizar(texto: str) -> str:
    """Caixa baixa + espaços colapsados (inclui quebras de linha) + acentos NFC."""
    texto = unicodedata.normalize("NFC", texto).lower()
    return re.sub(r"\s+", " ", texto).strip()


def verificar_citacao(excerto: str, paginas: list[str]) -> bool:
    """True se o excerto existir literalmente (normalizado) no texto do PDF."""
    if not excerto.strip():
        return False
    alvo = _normalizar(excerto)
    documento = _normalizar(" ".join(paginas))
    return alvo in documento


def aplicar_gate(requisitos: list[RequisitoHabilitacao],
                 paginas: list[str]) -> list[dict]:
    """Anexa verificada=True/False a cada requisito."""
    saida = []
    for r in requisitos:
        verificada = verificar_citacao(r.excerto, paginas)
        if not verificada:
            log.warning("Citação NÃO verificada: %r (pág. %s)", r.requisito, r.pagina)
        saida.append({**r.model_dump(), "verificada": verificada})
    return saida


def persistir(con: sqlite3.Connection, pregao_id: int,
              requisitos_verificados: list[dict]) -> int:
    """Substitui o checklist do pregão preservando status do usuário por requisito."""
    anteriores = {
        ln["requisito"]: ln["status_usuario"]
        for ln in con.execute(
            "SELECT requisito, status_usuario FROM habilitacao WHERE pregao_id=?",
            (pregao_id,),
        )
    }
    con.execute("DELETE FROM habilitacao WHERE pregao_id=?", (pregao_id,))
    for r in requisitos_verificados:
        con.execute(
            """INSERT INTO habilitacao
                 (pregao_id, requisito, categoria, obrigatorio, pagina,
                  excerto, verificada, status_usuario)
               VALUES (?,?,?,?,?,?,?,?)""",
            (pregao_id, r["requisito"], r["categoria"], int(r["obrigatorio"]),
             r["pagina"], r["excerto"], int(r["verificada"]),
             anteriores.get(r["requisito"], "pendente")),
        )
    con.commit()
    return len(requisitos_verificados)
