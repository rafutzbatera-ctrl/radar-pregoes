"""Monitoramento agendado (CLAUDE.md §6.1 e M6): roda as buscas ativas 2×/dia."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import db
from .services import certidoes as svc_certidoes
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


def _avisar_certidoes():
    """Loga um resumo das certidões vencidas/vencendo. NÃO envia nada externo —
    o aviso real é in-app (GET /certidoes/alertas); aqui é só observabilidade."""
    con = db.abrir()
    try:
        linhas = [svc_certidoes.enriquecer(dict(r))
                  for r in con.execute("SELECT * FROM certidoes").fetchall()]
        vencidas = [c for c in linhas if c["status"] == "vencida"]
        breve = [c for c in linhas if c["status"] == "vence_em_breve"]
        if vencidas or breve:
            nomes_v = ", ".join(c["nome"] for c in vencidas) or "—"
            nomes_b = ", ".join(
                f"{c['nome']} ({c['dias_restantes']}d)" for c in breve) or "—"
            log.warning(
                "Certidões: %s vencida(s) [%s] · %s vencendo em <=%dd [%s]",
                len(vencidas), nomes_v, len(breve),
                svc_certidoes.JANELA_DIAS, nomes_b)
        else:
            log.info("Certidões: nenhuma vencida ou vencendo.")
    except Exception:
        log.exception("Falha no aviso agendado de certidões")
    finally:
        con.close()


def iniciar() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone="America/Sao_Paulo")
    sched.add_job(_rodar_buscas, CronTrigger(hour="6,18", minute=0),
                  id="monitoramento", replace_existing=True)
    # mesmo horário do monitoramento; job separado para não interferir no
    # existente (id próprio) — só loga o resumo das certidões urgentes.
    sched.add_job(_avisar_certidoes, CronTrigger(hour="6,18", minute=0),
                  id="certidoes", replace_existing=True)
    sched.start()
    log.info("Scheduler ativo: buscas + certidões 2x/dia (06:00 e 18:00)")
    return sched
