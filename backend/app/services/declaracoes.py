"""Geração de MINUTAS de declarações de habilitação do licitante (RAG Fase 3).

IMPORTANTE — o gate de citação NÃO se aplica aqui. Uma declaração é TEXTO-PADRÃO
DO LICITANTE (Lei 14.133/CF/LC 123), não uma extração do edital. O render é
substituição de string PURA: SEM LLM, SEM chamada à API Anthropic, SEM chave.

Princípio 1 (nunca inventar): se faltar um dado da empresa, o placeholder NÃO é
preenchido com texto plausível — vira a LACUNA VISÍVEL "[<CAMPO> — preencher]" e
a minuta é marcada `completo=false` com a lista `faltando`. Nunca um chute.

`exigido_no_edital`: cruzamento CONSERVADOR entre cada template e os requisitos
extraídos do edital (tabela habilitacao). Só marca true quando há correspondência
CLARA por palavra-chave no texto do requisito; na dúvida, false (não inventa que
o edital exige). É só uma sinalização de apoio — todas as declarações sempre são
sugeridas conforme a `condicao`, independentemente do edital.
"""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from functools import lru_cache
from pathlib import Path

_TEMPLATES = Path(__file__).resolve().parent.parent / "dados" / "declaracoes_templates.json"

# Aviso fixo de TODA minuta (espelha o espírito do §9 do CLAUDE.md): declaração
# é apoio, não peça jurídica pronta — sempre conferir antes de assinar.
AVISO = ("Minuta de apoio — confira com seu jurídico/contador antes de assinar.")

# Placeholders {{campo}} -> coluna da tabela empresa. Mantém a ordem do template.
_CAMPOS = {
    "razao_social": "RAZÃO SOCIAL",
    "cnpj": "CNPJ",
    "endereco": "ENDEREÇO",
    "representante_nome": "NOME DO REPRESENTANTE",
    "representante_cpf": "CPF DO REPRESENTANTE",
    "representante_cargo": "CARGO DO REPRESENTANTE",
}

# Palavras-chave (sem acento, minúsculas) por template, para o cruzamento
# CONSERVADOR com os requisitos do edital. Só dispara `exigido_no_edital` quando
# TODAS as palavras de algum grupo aparecem no texto do requisito. Na dúvida,
# false — nunca inventa que o edital exige (princípio 1).
_KEYWORDS = {
    "menor": [["nao emprega menor"], ["menor", "trabalho"], ["art. 7", "xxxiii"]],
    "idoneidade": [["fato impeditivo"], ["fato superveniente"], ["inidone"],
                   ["impeditivo", "habilitacao"]],
    "cumprimento_habilitacao": [["cumprimento", "requisitos", "habilitacao"],
                                ["pleno cumprimento"], ["cumpre", "habilitacao"]],
    "proposta_independente": [["elaboracao independente"],
                              ["proposta independente"]],
    "me_epp": [["me/epp"], ["me", "epp"], ["microempresa"],
               ["pequeno porte"], ["lc 123"], ["123/2006"]],
    "reserva_cargos": [["reserva de cargos"], ["pessoa com deficiencia"],
                       ["pcd"], ["aprendiz"]],
}


@lru_cache(maxsize=1)
def carregar_templates() -> list[dict]:
    """Lê e cacheia os templates de declaração."""
    return json.loads(_TEMPLATES.read_text(encoding="utf-8"))


def _normalizar(texto: str) -> str:
    """minúsculas, sem acento, espaços colapsados — p/ casar palavras-chave."""
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t.lower()).strip()


def render(template: dict, empresa: dict | None) -> dict:
    """Substitui os placeholders {{campo}} pelos dados da empresa. Para CADA
    campo faltante/vazio, insere a lacuna VISÍVEL "[<CAMPO> — preencher]" e
    acumula em `faltando`. Retorna {texto, completo, faltando}. Nunca chuta."""
    empresa = empresa or {}
    texto = template.get("corpo_template", "")
    faltando: list[str] = []
    for campo, rotulo in _CAMPOS.items():
        marcador = "{{" + campo + "}}"
        if marcador not in texto:
            continue
        valor = empresa.get(campo)
        valor = (str(valor).strip() if valor is not None else "")
        if not valor:
            faltando.append(campo)
            valor = f"[{rotulo} — preencher]"
        texto = texto.replace(marcador, valor)
    return {"texto": texto, "completo": not faltando, "faltando": faltando}


def _empresa(con: sqlite3.Connection) -> dict:
    ln = con.execute("SELECT * FROM empresa WHERE id=1").fetchone()
    return dict(ln) if ln else {}


def _requisitos_normalizados(con: sqlite3.Connection, pregao_id: int) -> list[str]:
    """Texto dos requisitos extraídos do edital, normalizado para o cruzamento."""
    linhas = con.execute(
        "SELECT requisito FROM habilitacao WHERE pregao_id=?", (pregao_id,)
    ).fetchall()
    return [_normalizar(r["requisito"]) for r in linhas]


def _exigido(template_id: str, requisitos_norm: list[str]) -> bool:
    """True só quando há correspondência CLARA: algum grupo de palavras-chave do
    template aparece INTEIRO em algum requisito do edital. Senão, false."""
    grupos = _KEYWORDS.get(template_id, [])
    for req in requisitos_norm:
        for grupo in grupos:
            if all(palavra in req for palavra in grupo):
                return True
    return False


def declaracoes_do_pregao(con: sqlite3.Connection, pregao_id: int) -> list[dict]:
    """Templates SUGERIDOS para o pregão, já renderizados com a empresa.

    - condicao "sempre": sempre incluída.
    - condicao "porte_me_epp": só se empresa.porte == 'me_epp'.
    Cada item marca `exigido_no_edital` (cruzamento conservador com os requisitos
    extraídos) e traz o aviso fixo. Não inventa dado do edital.
    """
    empresa = _empresa(con)
    porte = empresa.get("porte")
    requisitos_norm = _requisitos_normalizados(con, pregao_id)

    resultado: list[dict] = []
    for tpl in carregar_templates():
        cond = tpl.get("condicao", "sempre")
        if cond == "porte_me_epp" and porte != "me_epp":
            continue
        r = render(tpl, empresa)
        resultado.append({
            "id": tpl["id"],
            "titulo": tpl["titulo"],
            "categoria": tpl.get("categoria"),
            "fundamento_legal": tpl.get("fundamento_legal"),
            "texto_renderizado": r["texto"],
            "completo": r["completo"],
            "faltando": r["faltando"],
            "exigido_no_edital": _exigido(tpl["id"], requisitos_norm),
            "aviso": AVISO,
        })
    return resultado


def metadados_templates() -> list[dict]:
    """Metadados dos templates (sem render) — para a tela de catálogo."""
    return [{
        "id": t["id"],
        "titulo": t["titulo"],
        "categoria": t.get("categoria"),
        "fundamento_legal": t.get("fundamento_legal"),
        "condicao": t.get("condicao", "sempre"),
    } for t in carregar_templates()]
