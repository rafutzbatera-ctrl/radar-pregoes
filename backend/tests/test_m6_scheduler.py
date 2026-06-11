"""M6 — monitoramento agendado: job registrado 2×/dia (06:00 e 18:00)."""
from app import scheduler


def test_scheduler_registra_job_2x_dia():
    sched = scheduler.iniciar()
    try:
        job = sched.get_job("monitoramento")
        assert job is not None
        trigger = str(job.trigger)
        assert "hour='6,18'" in trigger
        assert "minute='0'" in trigger
    finally:
        sched.shutdown(wait=False)
