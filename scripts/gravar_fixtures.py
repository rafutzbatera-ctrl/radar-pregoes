# Grava respostas REAIS da API do PNCP em backend/tests/fixtures/.
# Roda uma vez no setup (M0); os testes batem nas fixtures, não na API.
import json
import time
import urllib.request
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "backend" / "tests" / "fixtures"
FIXTURES.mkdir(parents=True, exist_ok=True)
UA = "RadarPregoes/0.1 (uso pessoal)"

ALVOS = {
    # busca textual (4.1)
    "search_audio_sp.json": (
        "https://pncp.gov.br/api/search/?q=%C3%A1udio&tipos_documento=edital"
        "&ufs=SP&status=recebendo_proposta&ordenacao=-data&pagina=1&tamanhoPagina=10"
    ),
    # pregão verificado de Imbaú/PR (CLAUDE.md §10)
    "itens_01613770000172_2026_67.json": (
        "https://pncp.gov.br/api/pncp/v1/orgaos/01613770000172/compras/2026/67/itens"
        "?pagina=1&tamanhoPagina=100"
    ),
    "arquivos_01613770000172_2026_67.json": (
        "https://pncp.gov.br/api/pncp/v1/orgaos/01613770000172/compras/2026/67/arquivos"
        "?pagina=1&tamanhoPagina=20"
    ),
}


def baixar(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


for nome, url in ALVOS.items():
    destino = FIXTURES / nome
    dados = baixar(url)
    destino.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    n = len(dados.get("items", dados) if isinstance(dados, dict) else dados)
    print(f"{nome}: {n} registros")
    time.sleep(1.1)  # gentileza: 1 req/s
