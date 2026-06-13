"""Stream B — histórico (sem ruído de sync), export CSV/XLSX, relatório PDF.

Tudo com fixtures pequenas / cliente_fake (NÃO bate na API real). O cliente_fake
serve historico_amostra.json (2 marcos + 3 entradas "sincroniza"); o filtro
testável (services.historico) deve devolver SÓ os 2 marcos.
"""
import io

from app.services import historico
from app.services.relatorio import montar_pdf

CNPJ = "01613770000172"


def _patch_pncp(monkeypatch, cliente):
    from app import pncp as pncp_mod
    monkeypatch.setattr(pncp_mod, "cliente", lambda: cliente)


def _criar_pregao(con, **extra):
    cols = {
        "cnpj": CNPJ, "ano": 2026, "seq": 67, "numero_controle": "NC-SB",
        "titulo": "Pregão de áudio e vídeo", "descricao": "Aquisição de equipamentos de AV",
        "orgao": "Município de Imbaú", "municipio": "Imbaú", "uf": "PR",
        "modalidade": "Pregão - Eletrônico", "situacao": "Recebendo proposta",
        "data_inicio_vigencia": "2026-06-13", "data_fim_vigencia": "2026-06-25",
        "valor_global": 50000.0, "link_pncp": "https://pncp.gov.br/app/editais/x",
    }
    cols.update(extra)
    campos = ", ".join(cols)
    marks = ", ".join("?" for _ in cols)
    con.execute(f"INSERT INTO pregoes({campos}) VALUES ({marks})", tuple(cols.values()))
    con.commit()
    return con.execute("SELECT id FROM pregoes WHERE numero_controle=?",
                       (cols["numero_controle"],)).fetchone()["id"]


def _inserir_itens(con, pregao_id):
    con.executemany(
        "INSERT INTO itens_pregao(pregao_id, numero, descricao, qtd, unidade,"
        " valor_unit_estimado, valor_total, sigiloso) VALUES (?,?,?,?,?,?,?,?)",
        [
            (pregao_id, 1, "Caixa de som ativa 500W", 4, "UN", 1200.0, 4800.0, 0),
            (pregao_id, 2, "Microfone sem fio duplo", 2, "UN", 800.0, 1600.0, 0),
        ],
    )
    con.commit()


# ---------- histórico: filtro de ruído ----------

def test_filtrar_eventos_descarta_sync_mantem_marcos():
    """Fixture: 2 marcos (Inclusão Contratação + Inclusão Documento) e 3 de
    'sincroniza' (grafias variadas) → só os 2 marcos sobram."""
    from tests.conftest import carregar_fixture
    cru = carregar_fixture("historico_amostra.json")
    evs = historico.filtrar_eventos(cru)
    assert len(evs) == 2
    for e in evs:
        assert "sincroniza" not in (e["justificativa"] or "").lower()
    # ordenado por data DECRESCENTE (mais recente primeiro)
    assert evs[0]["data"] == "2026-06-13T09:30:00"
    assert evs[0]["evento"] == "Inclusão - Documento"
    assert evs[0]["responsavel"] == "João Pereira"
    assert evs[0]["documento"] == "Edital Retificado.pdf"
    assert evs[1]["evento"] == "Inclusão - Contratação"


def test_filtrar_eventos_lista_vazia():
    assert historico.filtrar_eventos([]) == []
    assert historico.filtrar_eventos(None) == []


def test_filtrar_eventos_cap():
    """Cap defensivo: mais de 50 marcos → corta nos 50 mais recentes."""
    muitos = [
        {"logManutencaoDataInclusao": f"2026-01-01T00:{i:02d}:00",
         "tipoLogManutencaoNome": "Inclusão",
         "categoriaLogManutencaoNome": "Documento",
         "justificativa": f"marco {i}"}
        for i in range(60)
    ]
    evs = historico.filtrar_eventos(muitos)
    assert len(evs) == 50


def test_endpoint_historico_filtra_ruido(client, con, cliente_fake, monkeypatch):
    """GET /pregoes/{id}/historico via cliente_fake (fixture) → só 2 marcos."""
    _patch_pncp(monkeypatch, cliente_fake)
    pid = _criar_pregao(con)
    r = client.get(f"/pregoes/{pid}/historico")
    assert r.status_code == 200
    eventos = r.json()["eventos"]
    assert len(eventos) == 2
    assert cliente_fake.chamadas["historico"] == 1


def test_endpoint_historico_pregao_inexistente(client):
    r = client.get("/pregoes/999999/historico")
    assert r.status_code == 404


# ---------- export CSV / XLSX ----------

def test_export_csv_cabecalho_e_linhas(client, con):
    pid = _criar_pregao(con, numero_controle="NC-CSV")
    _inserir_itens(con, pid)
    r = client.get(f"/pregoes/{pid}/itens/export?formato=csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"]
    assert f"itens_{CNPJ}_2026_67.csv" in r.headers["content-disposition"]
    texto = r.content.decode("utf-8-sig")
    linhas = [ln for ln in texto.splitlines() if ln.strip()]
    # 1 cabeçalho + 2 itens
    assert len(linhas) == 3
    assert linhas[0].startswith("número;descrição;qtd")
    assert "Caixa de som ativa 500W" in linhas[1]


def test_export_xlsx_200_content_type(client, con):
    pid = _criar_pregao(con, numero_controle="NC-XLSX")
    _inserir_itens(con, pid)
    r = client.get(f"/pregoes/{pid}/itens/export?formato=xlsx")
    assert r.status_code == 200
    assert ("spreadsheetml.sheet" in r.headers["content-type"])
    assert f"itens_{CNPJ}_2026_67.xlsx" in r.headers["content-disposition"]
    # xlsx é um zip → começa com PK
    assert r.content[:2] == b"PK"


def test_export_formato_invalido_422(client, con):
    pid = _criar_pregao(con, numero_controle="NC-INV")
    r = client.get(f"/pregoes/{pid}/itens/export?formato=pdf")
    assert r.status_code == 422


def test_export_pregao_inexistente_404(client):
    r = client.get("/pregoes/999999/itens/export?formato=csv")
    assert r.status_code == 404


# ---------- relatório PDF ----------

def test_montar_pdf_retorna_bytes_pdf():
    pregao = {
        "cnpj": CNPJ, "ano": 2026, "seq": 67, "titulo": "Pregão áudio/vídeo",
        "descricao": "Aquisição de equipamentos com acento: ção, ã, é",
        "orgao": "Município de Imbaú", "municipio": "Imbaú", "uf": "PR",
        "modalidade": "Pregão - Eletrônico", "situacao": "Recebendo proposta",
        "data_inicio_vigencia": "2026-06-13", "data_fim_vigencia": "2026-06-25",
        "valor_global": 50000.0, "valor_itens": None,
        "link_pncp": "https://pncp.gov.br/app/editais/x", "numero_controle": "NC-1",
    }
    itens = [
        {"numero": 1, "descricao": "Caixa de som ativa 500W", "qtd": 4,
         "valor_unit_estimado": 1200.0, "valor_total": 4800.0,
         "custo_efetivo": 900.0, "margem": 0.25, "lucro": 1200.0, "sigiloso": 0},
    ]
    capag = {"disponivel": False, "motivo": "nao_avaliado",
             "fonte": "Tesouro Nacional / SICONFI"}
    agregados = {"veredito": "talvez", "lucro_potencial": 1200.0,
                 "margem_media": 0.25, "cobertura": 0.5}
    pdf = montar_pdf(pregao, itens, capag, agregados)
    assert isinstance(pdf, (bytes, bytearray))
    assert pdf[:4] == b"%PDF"


def test_montar_pdf_descricao_longa_nao_quebra():
    """Regressão (13/06/2026): descrição de item > 62 chars era truncada com
    '…' (U+2026), fora do latin-1 da fonte core → FPDFUnicodeEncodingException
    (500 ao vivo). A truncagem agora usa '...' ASCII. Item real do PNCP."""
    pregao = {"cnpj": CNPJ, "ano": 2026, "seq": 67, "titulo": "Pregão x",
              "municipio": "Imbaú", "uf": "PR"}
    itens = [{
        "numero": 1,
        "descricao": "AQUISIÇÃO DE TONER PARA IMPRESSORAS QUE ATENDEM A "
                     "SECRETARIA MUNICIPAL DE EDUCAÇÃO, ESCOLAS MUNICIPAIS DO "
                     "ENSINO FUNDAMENTAL E DO ENSINO INFANTIL",
        "qtd": 12, "valor_unit_estimado": 471.15, "valor_total": 5653.8,
        "custo_efetivo": None, "margem": None, "lucro": None, "sigiloso": 0,
    }]
    pdf = montar_pdf(pregao, itens, {"disponivel": False, "motivo": "nao_avaliado"},
                     {"veredito": None})
    assert pdf[:4] == b"%PDF"


def test_endpoint_relatorio_pdf(client, con):
    pid = _criar_pregao(con, numero_controle="NC-PDF")
    _inserir_itens(con, pid)
    r = client.get(f"/pregoes/{pid}/relatorio.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert f"relatorio_{CNPJ}_2026_67.pdf" in r.headers["content-disposition"]
    assert r.content[:4] == b"%PDF"


def test_endpoint_relatorio_pregao_inexistente(client):
    r = client.get("/pregoes/999999/relatorio.pdf")
    assert r.status_code == 404
