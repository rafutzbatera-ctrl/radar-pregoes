# Eval LOCAL (M7) do extrator de HABILITACAO — sem ragas, sem chave de API.
# Mede os principios 1 e 2 (CLAUDE.md): citacao verificada e honestidade.
#
# Metricas:
#   (1) taxa de citacao verificada = requisitos com verificada=True / total
#       (gate de citacao confere que o excerto existe LITERALMENTE no PDF).
#   (2) cobertura de categorias = |presentes ∩ esperadas| / |esperadas|
#       (as esperadas vem das ancoras versionadas, conferidas no PDF real).
#
# Determinismo: roda o extrator HEURISTICO (local, sem IA) + aplica_gate sobre
# o texto extraido do PDF real. Nada de rede, nada de chave.
#
# Exit != 0 se qualquer metrica ficar abaixo do alvo (gate manual de portfolio).
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

from app.services import extracao, habilitacao  # noqa: E402

# alvos (ajustados aos numeros REAIS observados no edital de Imbau, ver relatorio)
ALVO_CITACAO = 1.0
ALVO_COBERTURA = 1.0

ANCORAS = RAIZ / "backend" / "tests" / "fixtures" / "eval_ancoras.json"


def main() -> int:
    dados = json.loads(ANCORAS.read_text(encoding="utf-8"))
    falhou = False

    for ed in dados["editais"]:
        pdf = RAIZ / ed["pdf"]
        print(f"\n=== EDITAL {ed['id']} ===")
        print(f"PDF: {ed['pdf']}")
        if not pdf.exists():
            print(f"ERRO: PDF nao encontrado em {pdf}. "
                  f"Baixe o edital antes (nao baixo em silencio).")
            return 2

        paginas = extracao.extrair_paginas(pdf)
        print(f"paginas extraidas: {len(paginas)}")

        requisitos = habilitacao.extrair_requisitos(paginas, modo="heuristico")
        verificados = habilitacao.aplicar_gate(requisitos, paginas)
        total = len(verificados)
        if total == 0:
            print("ERRO: extrator nao retornou nenhum requisito.")
            return 2

        n_ver = sum(1 for r in verificados if r["verificada"])
        taxa_citacao = n_ver / total

        presentes = {r["categoria"] for r in verificados}
        esperadas = set(ed["categorias_esperadas"])
        intersec = presentes & esperadas
        cobertura = len(intersec) / len(esperadas) if esperadas else 1.0

        # relatorio deterministico
        from collections import Counter
        cont = Counter(r["categoria"] for r in verificados)
        print(f"\nrequisitos: {total}")
        print(f"por categoria: {dict(sorted(cont.items()))}")
        print(f"\n[1] CITACAO VERIFICADA: {n_ver}/{total} = {taxa_citacao:.3f} "
              f"(alvo >= {ALVO_CITACAO})")
        print(f"[2] COBERTURA CATEGORIAS: {len(intersec)}/{len(esperadas)} = "
              f"{cobertura:.3f} (alvo >= {ALVO_COBERTURA})")
        print(f"    esperadas: {sorted(esperadas)}")
        print(f"    presentes: {sorted(presentes)}")
        faltam = esperadas - presentes
        if faltam:
            print(f"    FALTAM:    {sorted(faltam)}")

        # cada requisito NAO-verificado (transparencia do gate)
        nao_ver = [r for r in verificados if not r["verificada"]]
        if nao_ver:
            print(f"\nREQUISITOS NAO-VERIFICADOS ({len(nao_ver)}):")
            for r in nao_ver:
                print(f"  [{r['categoria']}] pag {r['pagina']} {r['requisito']}")
                print(f"      excerto: \"{r['excerto'][:120]}\"")
        else:
            print("\nNenhum requisito nao-verificado (gate 100% limpo).")

        if taxa_citacao < ALVO_CITACAO:
            print(f"\nFALHA: citacao {taxa_citacao:.3f} < alvo {ALVO_CITACAO}")
            falhou = True
        if cobertura < ALVO_COBERTURA:
            print(f"\nFALHA: cobertura {cobertura:.3f} < alvo {ALVO_COBERTURA}")
            falhou = True

    print("\n" + ("RESULTADO: FALHOU (abaixo do alvo)" if falhou
                  else "RESULTADO: OK (todos os alvos atingidos)"))
    return 1 if falhou else 0


if __name__ == "__main__":
    sys.exit(main())
