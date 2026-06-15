import os

os.environ["RADAR_SCHEDULER"] = "0"  # antes de importar o app

import json
from pathlib import Path

import pytest

from app import db

FIXTURES = Path(__file__).parent / "fixtures"


def carregar_fixture(nome: str):
    return json.loads((FIXTURES / nome).read_text(encoding="utf-8"))


@pytest.fixture
def con(tmp_path):
    c = db.abrir(tmp_path / "radar_test.db")
    # baseline dos testes: conta no TETO (deságio 0). O default de PRODUTO é
    # 0.20 (cenário realista de leilão reverso); testes que exercitam deságio
    # setam o valor explicitamente.
    c.execute("UPDATE config SET valor='0.00' WHERE chave='desagio_esperado'")
    c.commit()
    yield c
    c.close()


class ClientePNCPFake:
    """Serve as respostas REAIS gravadas em tests/fixtures/ sem bater na API."""

    def __init__(self):
        self.chamadas = {
            "buscar": 0, "itens": 0, "arquivos": 0, "baixar": 0,
            "consulta": 0, "detalhe": 0, "historico": 0, "resultados": 0,
        }
        # captura dos kwargs de cada chamada a buscar (para testes de repasse)
        self.buscas = []
        # idem para a API de Consulta em massa (§4.4)
        self.consultas = []

    def buscar(self, q="", ufs="", status="", pagina=1, tamanho=50, usar_cache=True,
               tipos_documento="edital", ordenacao="-data", modalidades="",
               esferas=""):
        self.chamadas["buscar"] += 1
        self.buscas.append({
            "q": q, "ufs": ufs, "status": status, "pagina": pagina,
            "tamanho": tamanho, "tipos_documento": tipos_documento,
            "ordenacao": ordenacao, "modalidades": modalidades, "esferas": esferas,
        })
        return carregar_fixture("search_audio_sp.json")

    def consulta_propostas(self, data_final, modalidade="", uf="", pagina=1,
                           tamanho=50, usar_cache=True):
        self.chamadas["consulta"] += 1
        self.consultas.append({
            "data_final": data_final, "modalidade": modalidade, "uf": uf,
            "pagina": pagina, "tamanho": tamanho,
        })
        return carregar_fixture("consulta_propostas_sp.json")

    def detalhe_compra(self, cnpj, ano, seq, usar_cache=True):
        self.chamadas["detalhe"] += 1
        return {
            "numeroControlePNCP": f"{cnpj}-1-{int(seq):06d}/{ano}",
            "valorTotalEstimado": 12345.67,
            "valorTotalHomologado": None,
        }

    def itens(self, cnpj, ano, seq, usar_cache=True):
        self.chamadas["itens"] += 1
        return carregar_fixture("itens_01613770000172_2026_67.json")

    def arquivos(self, cnpj, ano, seq, usar_cache=True):
        self.chamadas["arquivos"] += 1
        return carregar_fixture("arquivos_01613770000172_2026_67.json")

    def historico(self, cnpj, ano, seq, usar_cache=True):
        self.chamadas["historico"] += 1
        # fixture pequena: 2 marcos + 3 entradas de "sincroniza" (ruído)
        return carregar_fixture("historico_amostra.json")

    def resultados_item(self, cnpj, ano, seq, numero_item, usar_cache=True):
        self.chamadas["resultados"] += 1
        # item 1 tem resultado (fixture real); demais itens ainda sem resultado
        # (array vazio) — permite testar item COM e SEM homologação.
        if int(numero_item) == 1:
            return carregar_fixture("resultados_item.json")
        return []

    def baixar_arquivo(self, url, destino_dir: Path):
        self.chamadas["baixar"] += 1
        destino_dir.mkdir(parents=True, exist_ok=True)
        destino = destino_dir / "edital_fake.pdf"
        destino.write_bytes(b"%PDF-1.4 fake para teste")
        return destino


@pytest.fixture
def cliente_fake():
    return ClientePNCPFake()


@pytest.fixture
def client(con):
    """TestClient da API com o banco de teste injetado."""
    from fastapi.testclient import TestClient

    from app import deps
    from app.main import app

    app.dependency_overrides[deps.get_db] = lambda: con
    yield TestClient(app)
    app.dependency_overrides.clear()
