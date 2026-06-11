# Diagnóstico: como o texto real do edital aparece para o heurístico?
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app import db
from app.services import extracao

con = db.abrir()
arq = con.execute(
    "SELECT caminho_local FROM arquivos WHERE caminho_local LIKE '%.pdf' LIMIT 1"
).fetchone()
paginas = extracao.extrair_paginas(Path(arq["caminho_local"]))

dens = [len(p) for p in paginas]
print(f"densidade: min={min(dens)} max={max(dens)} media={sum(dens)/len(dens):.0f}")

# onde aparece "habilita"?
for n, p in enumerate(paginas, 1):
    for m in re.finditer(r"(?i)habilita", p):
        ini = max(0, m.start() - 80)
        trecho = p[ini:m.start() + 120].replace("\n", "\\n")
        print(f"\npag {n}: …{trecho}…")
        break  # 1 por página

# amostra de linhas da página com mais menções a certidão/FGTS
alvo = max(range(len(paginas)),
           key=lambda i: len(re.findall(r"(?i)certid|fgts|cndt", paginas[i])))
print(f"\n=== amostra da pag {alvo+1} (mais menções a certidões) ===")
print(paginas[alvo][:2500])
