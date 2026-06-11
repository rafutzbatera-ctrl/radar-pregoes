# Validação real do extrator heurístico: roda no edital REAL já baixado
# (Barueri, 15 MB) e imprime requisitos + status do gate de citação.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app import db
from app.services import extracao, habilitacao

con = db.abrir()
arq = con.execute(
    "SELECT caminho_local FROM arquivos WHERE caminho_local LIKE '%.pdf' LIMIT 1"
).fetchone()
if not arq:
    sys.exit("nenhum PDF baixado no banco")

pdf = Path(arq["caminho_local"])
print(f"PDF: {pdf.name} ({pdf.stat().st_size/1e6:.1f} MB)")

paginas = extracao.extrair_paginas(pdf)
print(f"páginas extraídas: {len(paginas)}")

requisitos = habilitacao.extrair_requisitos(paginas, modo="heuristico")
verificados = habilitacao.aplicar_gate(requisitos, paginas)

print(f"\nrequisitos encontrados: {len(verificados)}")
for r in verificados:
    selo = "VERIFICADA" if r["verificada"] else "NAO VERIFICADA!"
    print(f"  [{r['categoria']:>22}] pag {r['pagina']:>3} {selo}  {r['requisito']}")
    print(f"      excerto: {r['excerto'][:100]}...")
