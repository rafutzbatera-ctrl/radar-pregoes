# Calibracao do GATE de honestidade do RAG (offline, e5 local, sem chave).
#
# Para cada pergunta-ancora (backend/tests/fixtures/eval_ancoras.json), indexa o
# edital real e reporta o MAX cosseno sobre TODOS os chunks — que e o sinal do
# gate SEMANTICO-puro proposto (lexico vira so ranking, nao abre mais o gate).
# Imprime a separacao on-topic x off-topic e SUGERE um threshold com margem.
#
# Uso: backend\.venv\Scripts\python scripts\calibra_gate.py
import io
import json
import sys
import tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

import numpy as np  # noqa: E402

from app import db  # noqa: E402
from app.services import extracao, matching, rag  # noqa: E402

ANCORAS = RAIZ / "backend" / "tests" / "fixtures" / "eval_ancoras.json"


def _max_cosseno(con, pregao_id, pergunta) -> float:
    rows, matriz = rag._carregar_matriz(con, pregao_id)
    if matriz is None:
        return float("nan")
    q = np.asarray(matching.embed_padrao(["query: " + pergunta])[0],
                   dtype=np.float32)
    scores = matriz @ q
    return float(np.max(scores))


def main() -> int:
    dados = json.loads(ANCORAS.read_text(encoding="utf-8"))
    on_topo: list[float] = []
    off_topo: list[float] = []

    for ed in dados["editais"]:
        pdf = RAIZ / ed["pdf"]
        if not pdf.exists():
            print(f"(pulando {ed['id']}: PDF ausente em {pdf})")
            continue
        print(f"\n=== {ed['id']} ===")
        with tempfile.TemporaryDirectory() as tmp:
            con = db.abrir(Path(tmp) / "calibra.db")
            try:
                cur = con.execute(
                    "INSERT INTO pregoes (cnpj, ano, seq, numero_controle, titulo)"
                    " VALUES (?,?,?,?,?)",
                    (ed["cnpj"], ed["ano"], ed["seq"],
                     f"{ed['cnpj']}-{ed['ano']}-{ed['seq']}", ed["id"]),
                )
                pid = cur.lastrowid
                cur2 = con.execute(
                    "INSERT INTO arquivos (pregao_id, titulo, tipo, url, caminho_local)"
                    " VALUES (?,?,?,?,?)",
                    (pid, "Edital", "Edital", str(pdf), str(pdf)),
                )
                paginas = extracao.extrair_paginas(pdf)
                rag.indexar_chunks(con, pid, [(cur2.lastrowid, paginas)],
                                   embed=matching.embed_padrao)
                for p in ed["perguntas"]:
                    mc = _max_cosseno(con, pid, p["pergunta"])
                    alvo = on_topo if p["espera"] == "encontrado" else off_topo
                    alvo.append(mc)
                    tag = "ON " if p["espera"] == "encontrado" else "OFF"
                    print(f"  {tag} max_cos={mc:.4f}  {p['pergunta'][:70]}")
            finally:
                con.close()

    print("\n===== SEPARACAO (max cosseno) =====")
    if on_topo:
        print(f"ON-topic : n={len(on_topo)}  min={min(on_topo):.4f}  "
              f"max={max(on_topo):.4f}")
    if off_topo:
        print(f"OFF-topic: n={len(off_topo)}  min={min(off_topo):.4f}  "
              f"max={max(off_topo):.4f}")
    if on_topo and off_topo:
        gap_lo, gap_hi = max(off_topo), min(on_topo)
        if gap_lo < gap_hi:
            sugerido = round((gap_lo + gap_hi) / 2, 3)
            print(f"\nSEPARAVEL: off_max={gap_lo:.4f} < on_min={gap_hi:.4f}")
            print(f"THRESHOLD SUGERIDO (ponto medio): {sugerido}")
        else:
            print(f"\nSOBREPOSICAO: off_max={gap_lo:.4f} >= on_min={gap_hi:.4f} "
                  f"— gate semantico puro nao separa 100%; ver achado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
