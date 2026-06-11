"""Extrator heurístico LOCAL de requisitos de habilitação (CLAUDE.md §6.3).

Sem IA: quebra o edital em cláusulas, casa cada uma com um dicionário de
padrões (regex com acentos opcionais) e devolve o requisito canônico com o
excerto LITERAL da cláusula (princípios 1 e 2: nunca inventa; o excerto passa
no gate de citação porque é cópia leve do texto — só removemos marcação
markdown `*`, `#`, `_`, que o gate também ignoraria via normalização).

Filtro de contexto: só vira requisito a cláusula que contém um gatilho de
exigência (apresentar, comprovar, certidão, declaração, ...). Isso evita pegar
menções soltas em considerandos. Documento sem nenhum padrão → lista vazia.
"""
import logging
import re

from ..habilitacao import RequisitoHabilitacao

log = logging.getLogger("radar.extratores.heuristico")

EXCERTO_MAX = 400  # chars; corte limpo em fronteira de palavra, sem reticências

# Cláusula inicia por: numeração (9, 9.1, 9.1.1, 10.2), marcador alfabético
# "a)" / "a.", romano "I -" / "II.", ou bullet "•" / "-" / "*".
_INICIO_CLAUSULA = re.compile(
    r"""^\s*(
        \d+(\.\d+)*[\.\)\-\s]      # 9  9.1  9.1.1  10.2)
      | [a-zA-Z][\.\)]             # a)  b.
      | [IVXLC]+\s*[\-\.\)]        # I -  II.  III)
      | [•\-\*]\s                  # bullet
    )""",
    re.VERBOSE,
)

# Gatilhos de exigência — sem um destes, a cláusula não é tratada como requisito.
_GATILHO = re.compile(
    r"apresentar|comprovar|prova de|exigid|dever[áa]|mediante|"
    r"certid|declara[çc]|atestado|documento|registro|balan[çc]o|"
    r"comprovante|inscri[çc]|validade|garantia",
    re.IGNORECASE,
)

_FACULTATIVO = re.compile(r"facultativ|opcional", re.IGNORECASE)

# Heading da seção de habilitação (bônus de precisão).
_HEADING_HABILITACAO = re.compile(
    r"\b(da\s+)?(documentos?\s+(de|para)\s+)?habilita[çc][ãa]o\b",
    re.IGNORECASE,
)

# Número de seção de nível 1 no início da cláusula (ex.: "9", "10.", "11)") —
# captura o número para comparar de qual seção a cláusula é. Nível 1 = um único
# grupo de dígitos sem sub-numeração (9.1 / 9.1.1 NÃO casam).
_SECAO_NIVEL1 = re.compile(r"^\s*(\d+)\s*[\.\)\-\s]?\s*(?!\.?\d)")

# Headings que encerram a região de habilitação por mudança de assunto
# (anexos, minuta, glossário, disposições finais, termo de referência).
_FIM_REGIAO_TEMATICO = re.compile(
    r"(?i)\b(ANEXO|MINUTA|GLOSS[ÁA]RIO|DISPOSI[ÇC][ÕO]ES\s+FINAIS|"
    r"TERMO\s+DE\s+REFER[ÊE]NCIA)\b"
)

# ---------- dicionário de padrões: (regex, requisito canônico, categoria) ----------
# Acentos opcionais via classes como [çc] / [ãa]. Ordem importa: padrões mais
# específicos primeiro dentro da mesma família.
PADROES: list[tuple[re.Pattern, str, str]] = [
    # fiscal
    (re.compile(r"(certid[ãa]o.*(conjunta|negativa).*(d[ée]bitos|tributos)"
                r"|(d[ée]bitos|tributos).*(federa|fazenda nacional|d[íi]vida ativa|\brfb\b|\bpgfn\b))"
                r"|certid[ãa]o.*(federa|fazenda nacional|d[íi]vida ativa|\brfb\b|\bpgfn\b)",
                re.IGNORECASE),
     "Certidão negativa de débitos federais (RFB/PGFN)", "fiscal"),
    (re.compile(r"\bfgts\b|fundo de garantia|\bcrf\b", re.IGNORECASE),
     "Certificado de regularidade do FGTS (CRF)", "fiscal"),
    (re.compile(r"\bcndt\b|d[ée]bitos trabalhistas|regularidade trabalhista", re.IGNORECASE),
     "Certidão negativa de débitos trabalhistas (CNDT)", "fiscal"),
    (re.compile(r"fazenda estadual|\bicms\b|regularidade.*estadual", re.IGNORECASE),
     "Regularidade fiscal estadual", "fiscal"),
    (re.compile(r"fazenda municipal|\biss\b|mobili[áa]rio|regularidade.*municipal", re.IGNORECASE),
     "Regularidade fiscal municipal", "fiscal"),
    (re.compile(r"\binss\b|seguridade social", re.IGNORECASE),
     "Regularidade com a Seguridade Social", "fiscal"),
    # juridica
    (re.compile(r"ato constitutivo|contrato social|estatuto", re.IGNORECASE),
     "Ato constitutivo / contrato social em vigor", "juridica"),
    (re.compile(r"(me/epp|microempresa|empresa de pequeno porte|lc\s*123|lei complementar 123)"
                r".*(declara|enquadramento)"
                r"|(declara|enquadramento).*(me/epp|microempresa|empresa de pequeno porte|lc\s*123)",
                re.IGNORECASE),
     "Declaração de enquadramento ME/EPP", "juridica"),
    (re.compile(r"n[ãa]o emprega menor|trabalho noturno.*menor|inciso xxxiii", re.IGNORECASE),
     "Declaração de que não emprega menor", "juridica"),
    (re.compile(r"procura[çc][ãa]o|credenciamento", re.IGNORECASE),
     "Procuração / credenciamento do representante", "juridica"),
    (re.compile(r"\bcnpj\b.*(inscri[çc]|comprovante)|(inscri[çc]|comprovante).*\bcnpj\b", re.IGNORECASE),
     "Comprovante de inscrição no CNPJ", "juridica"),
    # tecnica
    (re.compile(r"atestado.*capacidade t[ée]cnica|comprova[çc][ãa]o de aptid[ãa]o", re.IGNORECASE),
     "Atestado de capacidade técnica", "tecnica"),
    (re.compile(r"registro.*(\bcrea\b|\bcau\b|conselho)", re.IGNORECASE),
     "Registro no conselho profissional", "tecnica"),
    # economico_financeira
    (re.compile(r"balan[çc]o patrimonial", re.IGNORECASE),
     "Balanço patrimonial do último exercício", "economico_financeira"),
    (re.compile(r"fal[êe]ncia|recupera[çc][ãa]o judicial|concordata", re.IGNORECASE),
     "Certidão negativa de falência", "economico_financeira"),
    (re.compile(r"(capital social|patrim[ôo]nio l[íi]quido).*(m[íi]nimo)"
                r"|(m[íi]nimo).*(capital social|patrim[ôo]nio l[íi]quido)", re.IGNORECASE),
     "Capital social / patrimônio líquido mínimo", "economico_financeira"),
    (re.compile(r"[íi]ndices?\s+de\s+liquidez", re.IGNORECASE),
     "Índices de liquidez", "economico_financeira"),
    # proposta / outros
    (re.compile(r"validade.*proposta|proposta.*validade", re.IGNORECASE),
     "Validade mínima da proposta", "proposta"),
    (re.compile(r"garantia.*contratual|garantia.*execu[çc][ãa]o", re.IGNORECASE),
     "Garantia (proposta/contratual)", "outros"),
    (re.compile(r"garantia.*proposta|proposta.*garantia", re.IGNORECASE),
     "Garantia (proposta/contratual)", "proposta"),
]


def _limpar_markdown(linha: str) -> str:
    """Remove SÓ a marcação markdown leve (`*`, `#`, `_`); preserva o conteúdo.

    O gate normaliza caixa/espaços, então não precisamos mexer no texto — apenas
    tirar os marcadores que o pymupdf4llm injeta (negrito **x**, headings #).
    """
    linha = re.sub(r"[*_#]+", "", linha)
    return re.sub(r"[ \t]+", " ", linha).strip()


def _truncar(texto: str, limite: int = EXCERTO_MAX) -> str:
    """Trunca em fronteira de palavra, sem reticências inventadas — corte limpo."""
    if len(texto) <= limite:
        return texto
    corte = texto[:limite]
    espaco = corte.rfind(" ")
    if espaco > 0:
        corte = corte[:espaco]
    return corte.rstrip()


def _quebrar_clausulas(paginas: list[str]) -> list[tuple[int, str]]:
    """(pagina_1based, texto_da_clausula). Linhas de continuação juntam à anterior."""
    clausulas: list[tuple[int, str]] = []
    for pagina, conteudo in enumerate(paginas, start=1):
        atual_pagina: int | None = None
        atual_texto = ""
        for linha_bruta in (conteudo or "").splitlines():
            linha = _limpar_markdown(linha_bruta)
            if not linha:
                continue
            if _INICIO_CLAUSULA.match(linha_bruta) or _INICIO_CLAUSULA.match(linha):
                if atual_texto:
                    clausulas.append((atual_pagina, atual_texto.strip()))
                atual_pagina = pagina
                atual_texto = linha
            elif atual_texto:
                # continuação da cláusula anterior
                atual_texto += " " + linha
            else:
                # texto solto antes de qualquer numeração: vira sua própria cláusula
                atual_pagina = pagina
                atual_texto = linha
                clausulas.append((atual_pagina, atual_texto.strip()))
                atual_texto = ""
                atual_pagina = None
        if atual_texto:
            clausulas.append((atual_pagina, atual_texto.strip()))
    return clausulas


def _posicao_habilitacao(clausulas: list[tuple[int, str]]) -> int | None:
    """Índice da cláusula que abre a seção 'DA HABILITAÇÃO', se houver."""
    for i, (_pag, texto) in enumerate(clausulas):
        if _HEADING_HABILITACAO.search(texto):
            return i
    return None


def _secao_nivel1(texto: str) -> int | None:
    """Número da seção de nível 1 que abre a cláusula (ex.: '9.' → 9), ou None.

    Só cláusulas de nível 1 (um único número, sem sub-numeração) contam — '9.1'
    e '9.1.1' retornam None, pois são sub-itens da seção e não a fecham.
    """
    m = _SECAO_NIVEL1.match(texto)
    return int(m.group(1)) if m else None


def _fim_habilitacao(clausulas: list[tuple[int, str]], inicio_hab: int) -> int:
    """Índice (exclusivo) onde a região de habilitação termina.

    A região começa em `inicio_hab` e vai até a PRIMEIRA cláusula seguinte que
    seja (a) um heading de seção de nível 1 com número MAIOR ou IGUAL ao da
    seção de habilitação (se a habilitação abriu em '9.', qualquer '10.', '11.'
    etc. fecha) — OU (b) um heading temático de fim (ANEXO/MINUTA/GLOSSÁRIO/
    DISPOSIÇÕES FINAIS/TERMO DE REFERÊNCIA). Sem nenhum desses, a região vai até
    o fim do documento. Isso evita requisitos-fantasma de glossário/minuta/anexo
    que vêm DEPOIS do heading de habilitação mas não pertencem a ela.
    """
    secao_hab = _secao_nivel1(clausulas[inicio_hab][1])
    for idx in range(inicio_hab + 1, len(clausulas)):
        texto = clausulas[idx][1]
        if _FIM_REGIAO_TEMATICO.search(texto):
            return idx
        secao = _secao_nivel1(texto)
        if secao is not None and secao_hab is not None and secao >= secao_hab:
            return idx
    return len(clausulas)


def extrair(paginas: list[str]) -> list[RequisitoHabilitacao]:
    clausulas = _quebrar_clausulas(paginas)
    inicio_hab = _posicao_habilitacao(clausulas)
    # Fim da região: sem ele, glossário/minuta/anexos após o heading dispensariam
    # o gatilho de exigência e gerariam requisitos-fantasma.
    fim_hab = (_fim_habilitacao(clausulas, inicio_hab)
               if inicio_hab is not None else 0)

    # canônico -> (RequisitoHabilitacao, na_regiao_habilitacao)
    encontrados: dict[str, tuple[RequisitoHabilitacao, bool]] = {}

    for idx, (pagina, texto) in enumerate(clausulas):
        na_regiao = inicio_hab is not None and inicio_hab <= idx < fim_hab
        # Filtro de contexto: cláusula precisa de um gatilho de exigência para
        # virar requisito — EXCETO dentro da seção de habilitação, onde o
        # cabeçalho ("deverá apresentar os documentos a seguir") já estabelece a
        # exigência para a lista inteira (sub-itens 9.2, 9.3... herdam).
        if not na_regiao and not _GATILHO.search(texto):
            continue
        for regex, requisito, categoria in PADROES:
            if not regex.search(texto):
                continue
            obrigatorio = not bool(_FACULTATIVO.search(texto))
            novo = RequisitoHabilitacao(
                requisito=requisito,
                categoria=categoria,
                obrigatorio=obrigatorio,
                pagina=pagina or 1,
                excerto=_truncar(texto),
            )
            existente = encontrados.get(requisito)
            # dedupe: mantém ocorrência da região de habilitação sobre as de fora;
            # entre duas iguais, fica a primeira.
            if existente is None:
                encontrados[requisito] = (novo, na_regiao)
            elif na_regiao and not existente[1]:
                encontrados[requisito] = (novo, True)

    return [req for req, _ in encontrados.values()]
