"""CAPAG — Capacidade de Pagamento do comprador (risco de o ente pagar).

Fonte oficial: Tesouro Nacional / SICONFI (nota+indicadores do XLSX anual da
CAPAG, casados por CNPJ→cod_ibge via /entes). Os dados são POPULADOS por
scripts/seed_capag.py (manual/mensal) nas tabelas capag_entes/capag_notas;
este serviço só LÊ — nunca baixa nada no request.

Princípio nº 1 do projeto (CLAUDE.md §2): NUNCA inventar. Ente federal ou sem
dado no Tesouro NÃO recebe nota chutada — devolve {disponivel: False} com o
motivo ("federal" | "sem_dados"). A CAPAG só avalia municípios e estados.
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


def capag_do_pregao(con: sqlite3.Connection, cnpj: str | None,
                    uf: str | None, municipio: str | None) -> dict:
    """Resolve a CAPAG do ente comprador do pregão.

    Pipeline:
      1. capag_entes por CNPJ (só dígitos) → cod_ibge + esfera.
         - esfera M/E → capag_notas por cod_ibge → nota disponível.
      2. Fallback (sem casar por CNPJ, ou esfera fora de {M,E}): casar por
         (município normalizado + UF) em capag_notas.
      3. Sem nenhuma nota:
         - CNPJ não consta em capag_entes (e há entes carregados) → provável
           federal (federais não aparecem no /entes) → motivo "federal".
         - senão → motivo "sem_dados".

    Nunca inventa nota (princípio nº 1).
    """
    cnpj_d = so_digitos(cnpj)
    ente_row = None
    if cnpj_d:
        ente_row = con.execute(
            "SELECT cod_ibge, ente, uf, esfera FROM capag_entes WHERE cnpj=?",
            (cnpj_d,),
        ).fetchone()

    # 1. casamento direto por CNPJ → cod_ibge (esfera municipal/estadual)
    if ente_row is not None and (ente_row["esfera"] in ("M", "E")):
        nota_row = con.execute(
            "SELECT * FROM capag_notas WHERE cod_ibge=?", (ente_row["cod_ibge"],)
        ).fetchone()
        if nota_row is not None:
            return _montar_disponivel(nota_row, ente_row["ente"], ente_row["esfera"])

    # 2. fallback por (município normalizado + UF) — cobre CNPJ que não casa em
    #    capag_entes mas é claramente municipal (ente existe, base só do XLSX).
    if municipio and uf:
        mun_norm = _normalizar_nome(municipio)
        uf_up = uf.strip().upper()
        candidatos = con.execute(
            "SELECT * FROM capag_notas WHERE UPPER(uf)=?", (uf_up,)
        ).fetchall()
        for c in candidatos:
            if _normalizar_nome(c["municipio"]) == mun_norm:
                return _montar_disponivel(c, c["municipio"], c["esfera"])

    # 3. sem nota: distinguir federal de sem_dados.
    #    Federais NÃO aparecem em capag_entes (CLAUDE.md: o /entes só traz M/E).
    #    Se há entes carregados e este CNPJ não está lá, é provável federal.
    tem_entes = con.execute(
        "SELECT 1 FROM capag_entes LIMIT 1"
    ).fetchone() is not None
    if cnpj_d and tem_entes and ente_row is None:
        return {
            "disponivel": False,
            "motivo": "federal",
            "fonte": FONTE,
            "uf": uf,
            "ente": None,
        }

    return {
        "disponivel": False,
        "motivo": "sem_dados",
        "fonte": FONTE,
        "uf": uf,
        "ente": None,
    }
