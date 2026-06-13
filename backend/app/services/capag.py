"""CAPAG — Capacidade de Pagamento do comprador (risco de o ente pagar).

Fonte oficial: Tesouro Nacional / SICONFI (nota+indicadores do XLSX anual da
CAPAG, casados por CNPJ→cod_ibge via /entes). Os dados são POPULADOS por
scripts/seed_capag.py (manual/mensal) nas tabelas capag_entes/capag_notas;
este serviço só LÊ — nunca baixa nada no request.

Princípio nº 1 do projeto (CLAUDE.md §2): NUNCA inventar. Ente federal ou sem
dado no Tesouro NÃO recebe nota chutada — devolve {disponivel: False} com o
motivo ("federal" | "nao_avaliado"). A CAPAG só avalia municípios e estados.

ESFERA-AWARE (corrigido 13/06/2026): a CAPAG vale só para municípios/estados;
federal = pagamento pela União (risco baixo), NÃO recebe nota. A LOCALIZAÇÃO
NÃO pode determinar a nota — a ESFERA do órgão manda. O bug anterior usava o
fallback por município+UF para QUALQUER CNPJ desconhecido: um órgão FEDERAL
sediado em São Paulo (ex.: IFSP) herdava a CAPAG do MUNICÍPIO de São Paulo
(erro do Zionn). Agora o fallback por município só roda quando a esfera do PNCP
confirma M/E; esfera F nunca procura nota; esfera desconhecida (None) não faz
fallback (evita misatribuir).
"""
import re
import sqlite3
import unicodedata

FONTE = "Tesouro Nacional / SICONFI"

# rótulos dos 3 indicadores da CAPAG (na ordem do XLSX "Prévia da CAPAG")
ROTULOS = ["Endividamento", "Poupança Corrente", "Liquidez Relativa"]


def so_digitos(s: str | None) -> str:
    """Normaliza CNPJ para só dígitos (a base do Tesouro e a do PNCP podem
    vir com pontuação diferente)."""
    return re.sub(r"\D", "", s or "")


def _normalizar_nome(s: str | None) -> str:
    """Caixa baixa, sem acento, espaços colapsados — para casar município por
    nome quando o CNPJ não casa (mesma filosofia do gate de citação)."""
    if not s:
        return ""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", sem_acento.lower()).strip()


def cor_da_nota(nota: str | None) -> str | None:
    """Faixa de cor por nota CAPAG: A→ok (verde), B→atenção (âmbar),
    C/D→ruim (vermelho). A UI mapeia ok→--sinal, atenção→--pico, ruim→--clip."""
    if not nota:
        return None
    n = nota.strip().upper()[:1]
    if n == "A":
        return "ok"
    if n == "B":
        return "atencao"
    if n in ("C", "D"):
        return "ruim"
    return None


def _round_pct(valor) -> float | None:
    """Indicador (fração, ex. 0.32746) → percentual com 2 casas (32.75).
    None/valor inválido → None (não inventa número)."""
    if valor is None:
        return None
    try:
        return round(float(valor) * 100, 2)
    except (TypeError, ValueError):
        return None


def _montar_disponivel(nota_row: sqlite3.Row, ente: str | None,
                       esfera: str | None) -> dict:
    """Constrói o dict 'disponível' a partir de uma linha de capag_notas."""
    inds = [
        {"rotulo": ROTULOS[0], "nota": nota_row["nota1"],
         "valor_pct": _round_pct(nota_row["ind1"])},
        {"rotulo": ROTULOS[1], "nota": nota_row["nota2"],
         "valor_pct": _round_pct(nota_row["ind2"])},
        {"rotulo": ROTULOS[2], "nota": nota_row["nota3"],
         "valor_pct": _round_pct(nota_row["ind3"])},
    ]
    return {
        "disponivel": True,
        "nota": nota_row["nota"],
        "cor": cor_da_nota(nota_row["nota"]),
        "icf": nota_row["icf"],
        "origem": nota_row["origem"],
        "ente": ente or nota_row["municipio"],
        "municipio": nota_row["municipio"],
        "uf": nota_row["uf"],
        "esfera": esfera or nota_row["esfera"],
        "fonte": FONTE,
        "indicadores": inds,
    }


def _normalizar_esfera(esfera: str | None) -> str | None:
    """Esfera do PNCP → letra única maiúscula (F|E|M|D) ou None se vazia."""
    if not esfera:
        return None
    letra = esfera.strip().upper()[:1]
    return letra or None


def capag_do_pregao(con: sqlite3.Connection, cnpj: str | None,
                    uf: str | None, municipio: str | None,
                    esfera: str | None = None) -> dict:
    """Resolve a CAPAG do ente comprador do pregão (ESFERA-AWARE).

    A ESFERA do órgão (do PNCP, não a localização) decide se há CAPAG:

      0. esfera == "F" → federal: pagamento pela União (risco baixo). NÃO
         procura nota nenhuma → {disponivel: False, motivo: "federal"}.
      1. Casamento direto por CNPJ em capag_entes (esfera M/E) → nota por
         cod_ibge → disponível. Vale SEMPRE que casar, independente da esfera
         informada — o CNPJ ser um ente já prova que é municipal/estadual.
      2. Fallback por (município normalizado + UF) SOMENTE se esfera ∈ {M, E}:
         a esfera confirma que é municipal/estadual; o CNPJ do comprador é um
         sub-órgão (fundo/secretaria) do mesmo município. Esfera None/desconhecida
         NÃO faz fallback (evita misatribuir — bug do órgão federal em SP).
      3. Sem nada → {disponivel: False, motivo: "nao_avaliado"}.

    Nunca inventa nota (princípio nº 1). NÃO afirma "federal" por ausência de
    CNPJ em capag_entes (isso rotulava errado fundos/secretarias municipais);
    só afirma federal quando a esfera do PNCP diz F.
    """
    esf = _normalizar_esfera(esfera)

    # 0. federal: União paga (risco baixo). Não procura nota nenhuma.
    if esf == "F":
        return {
            "disponivel": False,
            "motivo": "federal",
            "fonte": FONTE,
            "uf": uf,
            "ente": None,
        }

    cnpj_d = so_digitos(cnpj)
    ente_row = None
    if cnpj_d:
        ente_row = con.execute(
            "SELECT cod_ibge, ente, uf, esfera FROM capag_entes WHERE cnpj=?",
            (cnpj_d,),
        ).fetchone()

    # 1. casamento direto por CNPJ → cod_ibge. O CNPJ casar em capag_entes já
    #    prova esfera M/E (o /entes só traz municípios e estados) — vale mesmo
    #    se a esfera informada vier None/desconhecida.
    if ente_row is not None and (ente_row["esfera"] in ("M", "E")):
        nota_row = con.execute(
            "SELECT * FROM capag_notas WHERE cod_ibge=?", (ente_row["cod_ibge"],)
        ).fetchone()
        if nota_row is not None:
            return _montar_disponivel(nota_row, ente_row["ente"], ente_row["esfera"])

    # 2. fallback por (município normalizado + UF) — SÓ se a esfera do PNCP
    #    confirma municipal/estadual. Aí é seguro: o comprador é um sub-órgão
    #    (fundo/secretaria) do mesmo município/estado. Sem esfera M/E, NÃO faz
    #    fallback (um órgão federal sediado num município não herda a nota dele).
    if esf in ("M", "E") and municipio and uf:
        mun_norm = _normalizar_nome(municipio)
        uf_up = uf.strip().upper()
        candidatos = con.execute(
            "SELECT * FROM capag_notas WHERE UPPER(uf)=?", (uf_up,)
        ).fetchall()
        for c in candidatos:
            if _normalizar_nome(c["municipio"]) == mun_norm:
                return _montar_disponivel(c, c["municipio"], c["esfera"])

    # 3. sem nota: não avaliado. NÃO inferimos "federal" por ausência de CNPJ
    #    em capag_entes (rotulava errado fundos/secretarias municipais com CNPJ
    #    próprio). Só dizemos "federal" quando a esfera do PNCP diz F (caso 0).
    return {
        "disponivel": False,
        "motivo": "nao_avaliado",
        "fonte": FONTE,
        "uf": uf,
        "ente": None,
    }
