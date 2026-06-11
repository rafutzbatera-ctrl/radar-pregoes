"""Monitoramento agendado (CLAUDE.md §6.1 e M6): roda as buscas ativas 2×/dia."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import db
from .services import descoberta

log = logging.getLogger("radar.scheduler")


def _rodar_buscas():
    con = db.abrir()
    try:
        resultados = descoberta.rodar_todas_ativas(con)
        log.info("Monitoramento: %s", resultados)
    except Exception:
        log.exception("Falha no monitoramento agendado")
    finally:
        con.close()


def iniciar() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone="America/Sao_Paulo")
    sched.add_job(_rodar_buscas, CronTrigger(hour="6,18", minute=0),
                  id="monitoramento", replace_existing=True)
    sched.start()
    log.info("Scheduler ativo: buscas 2x/dia (06:00 e 18:00)")
    return sched
