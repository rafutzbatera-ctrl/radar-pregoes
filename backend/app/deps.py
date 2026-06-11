"""Dependências FastAPI."""
from . import db


def get_db():
    con = db.abrir()
    try:
        yield con
    finally:
        con.close()
