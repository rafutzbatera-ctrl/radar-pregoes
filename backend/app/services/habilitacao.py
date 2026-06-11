"""Requisitos de habilitação: modelo, gate de citação e persistência (CLAUDE.md §6.3).

Princípios 1 e 2: NUNCA inventar. Todo requisito sai com excerto literal e
página; o gate confere se o excerto existe de fato no texto extraído do PDF
(normalização: caixa baixa + espaços colapsados). Citação que falha vira
verificada=false — nunca é descartada em silêncio, a UI mostra o aviso.

A extração em si é PLUGÁVEL (CLAUDE.md §6.3): `extrair_requisitos` delega ao
dispatcher em `extratores/` (heurístico local por padrão, ou API/CLI). O modelo
`RequisitoHabilitacao` vive aqui para os extratores importarem sem ciclo.
"""
import logging
import re
import sqlite3
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field

log = logging.getLogger("radar.habilitacao")


class RequisitoHabilitacao(BaseModel):
    requisito: str = Field(description="Nome curto do requisito, ex.: 'Certidão negativa de débitos federais'")
    categoria: Literal["juridica", "fiscal", "tecnica",
                       "economico_financeira", "proposta", "outros"]
    obrigatorio: bool
    pagina: int = Field(description="Página do edital onde o requisito aparece (1-based)")
    excerto: str = Field(description="Trecho LITERAL do edital que exige o documento, copiado sem alteração")


def extrair_requisitos(paginas: list[str], modo: str | None = None) -> list[RequisitoHabilitacao]:
    """Delega ao extrator plugável (CLAUDE.md §6.3).

    `modo` default = settings.EXTRATOR_HABILITACAO ("heuristico" | "api" | "claude_cli").
    Import local evita ciclo (os extratores importam RequisitoHabilitacao daqui).
    """
    from .extratores import extrair
    return extrair(paginas, modo=modo)


# ---------- gate de citação (princípio 2) ----------

def _normalizar(texto: str) -> str:
    """Caixa baixa + espaços colapsados (inclui quebras de linha) + acentos NFC.

    Também remove a marcação markdown leve (`*`, `#`, `_`) que o pymupdf4llm
    injeta (negrito **x**, headings #). A marcação só é descartada quando NÃO
    está entre dois caracteres de palavra (fronteira de token), e vira ESPAÇO —
    nunca string vazia. Assim a marcação real (`60**dias**` → `60 dias`) some
    sem JAMAIS fundir tokens distintos: um excerto fabricado como `60dias`,
    `abc` (de `a_b_c`) ou `1020` (de `10*20`) passaria a casar se a remoção
    fundisse os lados — por isso a substituição por espaço é o que fecha o
    buraco no gate. Aplicada antes do colapso de `\\s+`.
    """
    texto = unicodedata.normalize("NFC", texto).lower()
    texto = re.sub(r"(?<!\w)[*_#]+|[*_#]+(?!\w)", " ", texto)
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
