# O site do PNCP mostra "VALOR TOTAL ESTIMADO DA COMPRA" na página de detalhe.
# Que endpoint serve isso? Testa candidatos com o pregão do print do usuário.
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app import pncp

cli = pncp.ClientePNCP()
cnpj, ano, seq = "46227849000101", 2026, 24

candidatos = {
    "pncp/v1 detalhe": f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}",
    "consulta/v1 detalhe": f"https://pncp.gov.br/api/consulta/v1/orgaos/{cnpj}/compras/{ano}/{seq}",
}
for nome, url in candidatos.items():
    try:
        r = cli._get_json(url, {}, usar_cache=False)
        campos_valor = {k: v for k, v in r.items() if "alor" in k}
        print(f"{nome}: OK — campos de valor: {json.dumps(campos_valor, ensure_ascii=False)}")
    except Exception as e:
        print(f"{nome}: FALHOU — {e}")
