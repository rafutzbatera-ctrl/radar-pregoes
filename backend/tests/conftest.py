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
    yield c
    c.close()


class ClientePNCPFake:
    """Serve as respostas REAIS gravadas em tests/fixtures/ sem bater na API."""

    def __init__(self):
        self.chamadas = {"buscar": 0, "itens": 0, "arquivos": 0, "baixar": 0}
        # captura dos kwargs de cada chamada a buscar (para testes de repasse)
        self.buscas = []

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

    def itens(self, cnpj, ano, seq, usar_cache=True):
        self.chamadas["itens"] += 1
        return carregar_fixture("itens_01613770000172_2026_67.json")

    def arquivos(self, cnpj, ano, seq, usar_cache=True):
        self.chamadas["arquivos"] += 1
        return carregar_fixture("arquivos_01613770000172_2026_67.json")

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
