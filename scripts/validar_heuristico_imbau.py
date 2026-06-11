# Validação do heurístico no edital REAL de Imbaú/PR (CLAUDE.md §10).
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app import pncp, settings
from app.services import extracao, habilitacao

cli = pncp.ClientePNCP()
arquivos = cli.arquivos("01613770000172", 2026, 67)
destino = settings.ARQUIVOS_DIR / "01613770000172_2026_67"
pdf = cli.baixar_arquivo(arquivos[0]["url"], destino)
print(f"PDF: {pdf.name} ({pdf.stat().st_size/1024:.0f} KB)")

paginas = extracao.extrair_paginas(pdf)
print(f"paginas: {len(paginas)}")

requisitos = habilitacao.extrair_requisitos(paginas, modo="heuristico")
verificados = habilitacao.aplicar_gate(requisitos, paginas)

print(f"\nrequisitos: {len(verificados)}")
for r in verificados:
    selo = "VERIFICADA" if r["verificada"] else "NAO-VERIFICADA!"
    print(f"  [{r['categoria']:>22}] pag {r['pagina']:>2} {selo} {'(obrig)' if r['obrigatorio'] else '(facult)'} {r['requisito']}")
    print(f"      \"{r['excerto'][:110]}\"")
