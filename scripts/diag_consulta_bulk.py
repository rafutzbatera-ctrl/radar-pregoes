# A API de Consultas do PNCP tem endpoint em massa de contratações com
# recebimento de propostas aberto? Com valores embutidos? Filtros?
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app import pncp

cli = pncp.ClientePNCP()
BASE = "https://pncp.gov.br/api/consulta/v1/contratacoes/proposta"

casos = {
    "dataFinal+modalidade 6 (pregao eletr.)": {
        "dataFinal": "20260712", "codigoModalidadeContratacao": "6",
        "pagina": 1, "tamanhoPagina": 10},
    "+ uf=SP": {
        "dataFinal": "20260712", "codigoModalidadeContratacao": "6",
        "uf": "SP", "pagina": 1, "tamanhoPagina": 10},
    "sem modalidade": {"dataFinal": "20260712", "pagina": 1, "tamanhoPagina": 10},
}
for nome, params in casos.items():
    try:
        r = cli._get_json(BASE, params, usar_cache=False)
        regs = r.get("data") or r.get("items") or []
        total = r.get("totalRegistros") or r.get("total")
        com_valor = sum(1 for x in regs if x.get("valorTotalEstimado") is not None)
        amostra = ({k: regs[0].get(k) for k in
                    ("numeroControlePNCP", "valorTotalEstimado", "objetoCompra",
                     "modalidadeNome", "unidadeOrgao")} if regs else None)
        print(f"{nome}: OK total={total} pagina={len(regs)} com_valor={com_valor}")
        if amostra:
            print("   amostra:", json.dumps(amostra, ensure_ascii=False)[:300])
    except Exception as e:
        print(f"{nome}: FALHOU — {e}")
