"""Relatório PDF do pregão (Recurso 3) — fpdf2, fonte core 'helvetica'.

Monta um PDF de uma página (ou mais, paginação automática) com: cabeçalho do
edital (nº/título, órgão, município/UF, modalidade, situação, datas, valor,
link PNCP), descrição, VEREDITO + os números da NOSSA análise (lucro potencial,
margem média, cobertura — diferencial sobre o Zionn), bloco CAPAG (nota +
indicadores ou "federal"/"não avaliado"), tabela de itens e, no rodapé, os DOIS
avisos fixos do CLAUDE.md §9 (literais — apoio à decisão / sugestão fiscal).

Acentos: fpdf2 com fonte core 'helvetica' codifica em latin-1; o português cabe
em latin-1, mas caracteres fora dele (ex. emoji, traços tipográficos) quebram.
`_l1()` substitui o que não couber por '?' (encode latin-1 'replace'),
preservando todo o português acentuado. Nada é inventado: campos sem dado viram
"—" e o veredito sempre vem acompanhado dos números crus (princípio 1 e §6.2).
"""
from fpdf import FPDF

MARCA = "Radar de Pregoes - dados do PNCP"

# Avisos fixos do CLAUDE.md §9 (copiados literalmente).
AVISO_DECISAO = (
    "Ferramenta de apoio à decisão. O edital oficial e os valores estão no "
    "PNCP. Confira antes de dar lance."
)
AVISO_FISCAL = (
    "Sugestões fiscais (NCM, CFOP, CST/CSOSN) são apoio, não orientação "
    "contábil. Confirme com seu contador antes de emitir a nota."
)

VEREDITO_TXT = {"vale": "Vale", "talvez": "Talvez", "nao_vale": "Não vale"}


def _l1(s) -> str:
    """Texto seguro para a fonte core latin-1 do fpdf2 (preserva o português;
    troca o que não couber por '?'). None/número viram string."""
    if s is None:
        return ""
    return str(s).encode("latin-1", "replace").decode("latin-1")


def _brl(v) -> str:
    """R$ no padrão pt-BR (1.234,56). None → '—'."""
    if v is None:
        return "—"
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "—"
    inteiro = f"{n:,.2f}"  # 1,234.56
    inteiro = inteiro.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {inteiro}"


def _pct(v) -> str:
    """Fração (0.32) → '32,0%'. None → '—'."""
    if v is None:
        return "—"
    try:
        return f"{float(v) * 100:.1f}".replace(".", ",") + "%"
    except (TypeError, ValueError):
        return "—"


def _ou_traco(v) -> str:
    return _l1(v) if v not in (None, "") else "—"


def _trunc(s: str, n: int) -> str:
    s = _l1(s)
    return s if len(s) <= n else s[: n - 1] + "…"


class _PDF(FPDF):
    def footer(self):
        # rodapé fixo em TODAS as páginas: marca + nº de página
        self.set_y(-12)
        self.set_font("helvetica", "I", 7)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, _l1(f"{MARCA}  ·  pág. {self.page_no()}"),
                  align="C")
        self.set_text_color(0, 0, 0)


def _titulo_secao(pdf: FPDF, texto: str) -> None:
    pdf.ln(2)
    pdf.set_font("helvetica", "B", 11)
    pdf.set_fill_color(238, 240, 244)
    pdf.cell(0, 7, _l1(texto), new_x="LMARGIN", new_y="NEXT", fill=True)
    pdf.ln(1)


def _linha_chave_valor(pdf: FPDF, chave: str, valor: str) -> None:
    pdf.set_font("helvetica", "B", 9)
    pdf.cell(40, 5, _l1(chave))
    pdf.set_font("helvetica", "", 9)
    pdf.multi_cell(0, 5, _l1(valor), new_x="LMARGIN", new_y="NEXT")


def montar_pdf(pregao, itens, capag, agregados) -> bytes:
    """Gera o PDF (bytes) do pregão.

    `pregao`: dict/Row com cnpj, ano, seq, titulo, descricao, orgao, municipio,
        uf, modalidade, situacao, data_inicio_vigencia, data_fim_vigencia,
        valor_global, valor_itens, link_pncp, numero_controle.
    `itens`: lista de dicts (os calculados de GET /itens — número, descricao,
        qtd, valor_unit_estimado, valor_total, custo_efetivo, margem, lucro).
    `capag`: dict de services.capag.capag_do_pregao (disponivel/motivo/...).
    `agregados`: dict do _resumo_pregao (veredito, lucro_potencial, margem_media,
        cobertura — a NOSSA análise).
    """
    p = dict(pregao)
    pdf = _PDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(left=14, top=14, right=14)
    pdf.add_page()

    # ---- cabeçalho ----
    pdf.set_font("helvetica", "B", 14)
    titulo = p.get("titulo") or f"Edital {p.get('seq')}/{p.get('ano')}"
    pdf.multi_cell(0, 7, _l1(titulo), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 9)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(0, 5, _l1(MARCA), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    municipio_uf = "—"
    if p.get("municipio") or p.get("uf"):
        municipio_uf = f"{p.get('municipio') or '—'}/{p.get('uf') or '—'}"
    valor = p.get("valor_global")
    if valor is None:
        valor = p.get("valor_itens")
    rotulo_valor = "Valor total estimado"
    if p.get("valor_global") is None and p.get("valor_itens") is not None:
        rotulo_valor += " (Σ dos itens)"

    _linha_chave_valor(pdf, "Órgão", _ou_traco(p.get("orgao")))
    _linha_chave_valor(pdf, "Município/UF", municipio_uf)
    _linha_chave_valor(pdf, "Modalidade", _ou_traco(p.get("modalidade")))
    _linha_chave_valor(pdf, "Situação", _ou_traco(p.get("situacao")))
    _linha_chave_valor(
        pdf, "Propostas",
        f"{_ou_traco(p.get('data_inicio_vigencia'))}  ->  "
        f"{_ou_traco(p.get('data_fim_vigencia'))}",
    )
    _linha_chave_valor(pdf, rotulo_valor, _brl(valor))
    link = p.get("link_pncp") or (
        f"https://pncp.gov.br/app/editais/{p.get('cnpj')}/"
        f"{p.get('ano')}/{p.get('seq')}"
    )
    _linha_chave_valor(pdf, "PNCP", link)
    if p.get("numero_controle"):
        _linha_chave_valor(pdf, "Nº controle", _ou_traco(p.get("numero_controle")))

    # ---- descrição ----
    if p.get("descricao"):
        _titulo_secao(pdf, "Descrição")
        pdf.set_font("helvetica", "", 9)
        pdf.multi_cell(0, 5, _l1(p.get("descricao")), new_x="LMARGIN", new_y="NEXT")

    # ---- veredito + números (a NOSSA análise) ----
    _titulo_secao(pdf, "Veredito (nossa análise)")
    ag = dict(agregados or {})
    veredito = ag.get("veredito")
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 6, _l1(VEREDITO_TXT.get(veredito, "A casar")),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 9)
    pdf.cell(0, 5, _l1(
        f"Lucro potencial: {_brl(ag.get('lucro_potencial'))}   "
        f"·   Margem média: {_pct(ag.get('margem_media'))}   "
        f"·   Cobertura de custos: {_pct(ag.get('cobertura'))}"
    ), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "I", 8)
    pdf.set_text_color(110, 110, 110)
    pdf.multi_cell(0, 4, _l1(
        "Veredito: Vale se margem >= 20% e cobertura >= 60% e lucro >= R$ "
        "1.000; Não vale se margem < 8% ou lucro < R$ 300; senão Talvez. "
        "O veredito nunca esconde a conta."
    ), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

    # ---- CAPAG (risco de pagamento do comprador) ----
    _titulo_secao(pdf, "CAPAG - capacidade de pagamento do comprador")
    c = dict(capag or {})
    pdf.set_font("helvetica", "", 9)
    if c.get("disponivel"):
        pdf.set_font("helvetica", "B", 10)
        ente = c.get("ente") or c.get("municipio") or "—"
        pdf.cell(0, 5, _l1(f"Nota {c.get('nota')}  ·  {ente}"),
                 new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "", 9)
        for ind in (c.get("indicadores") or []):
            pct = ind.get("valor_pct")
            pct_txt = (f"{pct:.2f}".replace(".", ",") + "%") if pct is not None else "—"
            pdf.cell(0, 5, _l1(
                f"  - {ind.get('rotulo')}: nota {ind.get('nota') or '—'}  ({pct_txt})"
            ), new_x="LMARGIN", new_y="NEXT")
        if c.get("icf"):
            pdf.cell(0, 5, _l1(f"  Ranking ICF: {c.get('icf')}"),
                     new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "I", 8)
        pdf.set_text_color(110, 110, 110)
        pdf.cell(0, 4, _l1(f"Fonte: {c.get('fonte') or 'Tesouro Nacional / SICONFI'}"
                           + (f"  ·  {c.get('origem')}" if c.get("origem") else "")),
                 new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
    elif c.get("motivo") == "federal":
        pdf.multi_cell(0, 5, _l1(
            "Órgão federal - pagamento pela União (risco baixo). A CAPAG do "
            "Tesouro avalia apenas municípios e estados."
        ), new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.multi_cell(0, 5, _l1(
            "CAPAG não disponível para este órgão (sem dado no Tesouro). Nada "
            "foi estimado - sem dado, sem nota."
        ), new_x="LMARGIN", new_y="NEXT")

    # ---- tabela de itens ----
    _titulo_secao(pdf, f"Itens do edital ({len(itens or [])})")
    # larguras (mm): nº, descrição, qtd, valor unit, valor total = 182 úteis (A4-margens)
    larg = [12, 96, 18, 28, 28]
    cabec = ["Nº", "Descrição", "Qtd", "Valor unit.", "Valor total"]
    pdf.set_font("helvetica", "B", 8)
    pdf.set_fill_color(238, 240, 244)
    for w, t in zip(larg, cabec):
        pdf.cell(w, 6, _l1(t), border=1, fill=True, align="C")
    pdf.ln(6)
    pdf.set_font("helvetica", "", 8)
    for it in (itens or []):
        d = dict(it)
        sig = d.get("sigiloso")
        vu = None if sig else d.get("valor_unit_estimado")
        vt = None if sig else d.get("valor_total")
        pdf.cell(larg[0], 5, _l1(str(d.get("numero") or "")), border=1, align="C")
        pdf.cell(larg[1], 5, _trunc(d.get("descricao"), 62), border=1)
        qtd = d.get("qtd")
        pdf.cell(larg[2], 5, _l1("" if qtd is None else f"{qtd:g}"),
                 border=1, align="R")
        pdf.cell(larg[3], 5, _l1("sigiloso" if sig else _brl(vu)),
                 border=1, align="R")
        pdf.cell(larg[4], 5, _l1("sigiloso" if sig else _brl(vt)),
                 border=1, align="R")
        pdf.ln(5)
    if not itens:
        pdf.set_font("helvetica", "I", 8)
        pdf.cell(0, 5, _l1("Sem itens carregados (sincronize o pregão no PNCP)."),
                 new_x="LMARGIN", new_y="NEXT")

    # ---- avisos fixos §9 ----
    pdf.ln(3)
    pdf.set_font("helvetica", "I", 7)
    pdf.set_text_color(110, 110, 110)
    pdf.multi_cell(0, 4, _l1(AVISO_DECISAO), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    pdf.multi_cell(0, 4, _l1(AVISO_FISCAL), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

    saida = pdf.output()
    return bytes(saida)
