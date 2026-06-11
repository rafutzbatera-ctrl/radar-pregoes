# Sonda os valores aceitos do param `status` da busca do PNCP.
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app import pncp

cli = pncp.ClientePNCP()

for status in ("recebendo_proposta", "em_julgamento", "encerrado", "encerradas",
               "divulgada", "todos", ""):
    params = {"tipos_documento": "edital", "pagina": 1, "tamanhoPagina": 1,
              "ordenacao": "-data"}
    if status:
        params["status"] = status
    try:
        r = cli._get_json(pncp.BASE_SEARCH, params, usar_cache=False)
        print(f"status={status or '(sem)'}: total={r.get('total')}")
    except Exception as e:
        print(f"status={status or '(sem)'}: ERRO {e}")
