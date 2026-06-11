import sqlite3

from fastapi import APIRouter, Depends

from ..deps import get_db

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

STATUS_FUNIL = ("cotacao", "habilitacao", "disputando",
                "ganho", "perdido", "suspenso")


@router.get("/resumo")
def resumo(con: sqlite3.Connection = Depends(get_db)):
    """Resultados do funil (pregões salvos). Princípio 1: valor_ganho só soma
    valor_final PREENCHIDO de pregões ganhos — sem dado, é null, nunca chute."""
    linhas = con.execute(
        "SELECT status_pipeline s, valor_final v FROM pregoes WHERE salvo=1"
    ).fetchall()
    por_status = {s: 0 for s in STATUS_FUNIL}
    valor_ganho = 0.0
    tem_valor = False
    ganhos_sem_valor = 0
    for ln in linhas:
        if ln["s"] in por_status:
            por_status[ln["s"]] += 1
            if ln["s"] == "ganho":
                if ln["v"] is not None:
                    valor_ganho += ln["v"]
                    tem_valor = True
                else:
                    ganhos_sem_valor += 1
    ganhos, perdidos = por_status["ganho"], por_status["perdido"]
    encerrados = ganhos + perdidos
    return {
        "por_status": por_status,
        "total_funil": sum(por_status.values()),
        "ganhos": ganhos,
        "perdidos": perdidos,
        "taxa_ganho": (ganhos / encerrados) if encerrados else None,
        "valor_ganho": valor_ganho if tem_valor else None,
        "ganhos_sem_valor": ganhos_sem_valor,
    }
