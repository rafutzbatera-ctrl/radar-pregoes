import sys
sys.path.insert(0, r"D:\CLAUDE PROJECTS\Radar_pregao\backend")

from app import pncp

cli = pncp.ClientePNCP()
for termo in ("áudio", "microfone", "caixa de som"):
    try:
        r = cli.buscar(termo, ufs="SP", usar_cache=False)
        print(f"{termo}: {r.get('total')} total, {len(r.get('items', []))} na página")
    except Exception as e:
        print(f"{termo}: ERRO {type(e).__name__}: {e}")
