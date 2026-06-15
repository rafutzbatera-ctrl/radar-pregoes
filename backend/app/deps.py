"""Dependências FastAPI."""
from . import db


def get_db():
    # conectar() em vez de abrir(): a migração roda UMA vez na subida (lifespan
    # em main.py chama db.abrir()). Evita o overhead de migrar() (PRAGMA
    # user_version + loop) a cada requisição HTTP, mantendo a conexão-por-request.
    con = db.conectar()
    try:
        yield con
    finally:
        con.close()
