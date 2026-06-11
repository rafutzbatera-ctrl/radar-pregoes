# Sonda empírica: quais params extras a busca do PNCP aceita de verdade?
# Critério: param aceito ⇔ total muda drasticamente vs baseline.
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app import pncp

cli = pncp.ClientePNCP()


def total(params_extras: dict) -> int | str:
    base = {"tipos_documento": "edital", "status": "recebendo_proposta",
            "pagina": 1, "tamanhoPagina": 1, "ordenacao": "-data"}
    base.update(params_extras)
    try:
        r = cli._get_json(pncp.BASE_SEARCH, base, usar_cache=False)
        return r.get("total", "?")
    except Exception as e:
        return f"ERRO {e}"


baseline = total({})
print(f"baseline (sem extras): {baseline}")

candidatos = {
    "modalidades=6 (pregao eletr.)": {"modalidades": "6"},
    "modalidades=8 (dispensa)": {"modalidades": "8"},
    "esferas=M": {"esferas": "M"},
    "esferas=F": {"esferas": "F"},
    "poderes=E": {"poderes": "E"},
    "municipios=3550308 (IBGE SP capital)": {"municipios": "3550308"},
    "orgaos=46523015000135 (cnpj Barueri)": {"orgaos": "46523015000135"},
    "tipos_documento=ata": {"tipos_documento": "ata"},
    "ordenacao=relevancia (com q)": {"q": "notebook", "ordenacao": "relevancia"},
    "ordenacao=data (asc, com q)": {"q": "notebook", "ordenacao": "data"},
}
for nome, extras in candidatos.items():
    print(f"{nome}: {total(extras)}")
