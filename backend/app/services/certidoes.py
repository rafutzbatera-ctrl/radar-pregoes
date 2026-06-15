"""Status de validade das certidões do fornecedor (CLAUDE.md — "Minhas certidões").

O status é sempre CALCULADO a partir de "hoje" (nunca persistido — assim não
envelhece errado no banco). Regra:
  - sem_validade : validade NULL/ausente (indeterminada — nunca um chute)
  - vencida      : validade < hoje (dias_restantes negativo)
  - vence_em_breve: 0 <= dias_restantes <= JANELA (30 dias) — inclui vence hoje
  - ok           : dias_restantes > JANELA
"""
from __future__ import annotations

from datetime import date, datetime

# janela de "atenção" antes do vencimento (decisão: 30 dias)
JANELA_DIAS = 30

# ordem de urgência para a listagem (menor = mais urgente / topo da lista)
_PRIORIDADE = {"vencida": 0, "vence_em_breve": 1, "sem_validade": 2, "ok": 3}


def _parse_iso(valor: str) -> date:
    """Aceita 'YYYY-MM-DD' (e tolera 'YYYY-MM-DDTHH:MM:SS'); levanta em formato
    inválido — o router converte em 422 ANTES de gravar."""
    return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()


def validade_valida(valor) -> bool:
    """True se `valor` é uma data ISO 'YYYY-MM-DD' válida. None/'' não é validade
    (a coluna aceita NULL), então é tratado pelo router conforme o caso."""
    if valor is None:
        return False
    try:
        _parse_iso(valor)
        return True
    except (ValueError, TypeError):
        return False


def dias_restantes(validade, hoje: date | None = None) -> int | None:
    """Dias de hoje até a validade (negativo se já passou). None se sem validade."""
    if not validade:
        return None
    hoje = hoje or date.today()
    return (_parse_iso(validade) - hoje).days


def status_certidao(validade, hoje: date | None = None) -> str:
    """Status de UMA certidão. Testável e puro (recebe `hoje`)."""
    if not validade:
        return "sem_validade"
    dias = dias_restantes(validade, hoje)
    if dias < 0:
        return "vencida"
    if dias <= JANELA_DIAS:
        return "vence_em_breve"
    return "ok"


def enriquecer(linha: dict, hoje: date | None = None) -> dict:
    """Acrescenta `status` e `dias_restantes` a um dict de certidão (linha do DB)."""
    validade = linha.get("validade")
    return {
        **linha,
        "status": status_certidao(validade, hoje),
        "dias_restantes": dias_restantes(validade, hoje),
    }


def ordem_urgencia(certidao: dict):
    """Chave de ordenação: urgência primeiro (vencida > breve > sem_validade > ok);
    dentro do mesmo status, menos dias restantes primeiro; depois nome."""
    pri = _PRIORIDADE.get(certidao.get("status"), 9)
    dias = certidao.get("dias_restantes")
    dias_chave = dias if dias is not None else 10**9
    return (pri, dias_chave, str(certidao.get("nome") or "").lower())


# status que disparam alerta (badge/dashboard e log do scheduler)
STATUS_ALERTA = ("vencida", "vence_em_breve")


def eh_alerta(certidao: dict) -> bool:
    return certidao.get("status") in STATUS_ALERTA
