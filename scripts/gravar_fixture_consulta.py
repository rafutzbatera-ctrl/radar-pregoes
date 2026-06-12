# Grava resposta REAL da API de consulta em massa do PNCP para os testes.
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app import pncp

FIXTURES = Path(__file__).resolve().parent.parent / "backend" / "tests" / "fixtures"
cli = pncp.ClientePNCP()
r = cli._get_json(
    "https://pncp.gov.br/api/consulta/v1/contratacoes/proposta",
    {"dataFinal": "20260712", "uf": "SP", "pagina": 1, "tamanhoPagina": 10},
    usar_cache=False,
)
destino = FIXTURES / "consulta_propostas_sp.json"
destino.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
regs = r.get("data") or []
print(f"gravado: {len(regs)} registros, total={r.get('totalRegistros')}")
print("chaves do registro:", sorted(regs[0].keys()) if regs else "—")
