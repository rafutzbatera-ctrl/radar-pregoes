import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import db, settings
from .routers import (buscas, catalogo, certidoes, config, descobrir, empresa,
                      habilitacao, health, itens, pipeline, pregoes, rag)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")

AVISO = ("Ferramenta de apoio à decisão. O edital oficial e os valores estão no "
         "PNCP. Confira antes de dar lance.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    con = db.abrir()          # cria/migra o banco na subida
    con.close()
    sched = None
    if settings.SCHEDULER_ATIVO:
        from . import scheduler
        sched = scheduler.iniciar()
    yield
    if sched:
        sched.shutdown(wait=False)


app = FastAPI(title="Radar de Pregões", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(buscas.router)
app.include_router(descobrir.router)
app.include_router(pregoes.router)
app.include_router(itens.router)
app.include_router(catalogo.router)
app.include_router(certidoes.router)
app.include_router(empresa.router)
app.include_router(habilitacao.router)
app.include_router(config.router)
app.include_router(pipeline.router)
app.include_router(rag.router)
app.include_router(health.router)


@app.get("/")
def raiz():
    return {"app": "Radar de Pregões", "aviso": AVISO}
