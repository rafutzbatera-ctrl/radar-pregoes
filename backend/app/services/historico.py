"""Histórico do pregão — filtro de RUÍDO de sincronização (Recurso 4a).

O endpoint /historico do PNCP repete a CADA 5 min um evento de "Sincronizacao
automatica (scheduler 5min)" — verificado ao vivo (13/06/2026): um pregão tinha
2166 eventos, quase todos ruído de sync. Aqui ficam só os MARCOS: inclusões,
alterações com justificativa real, documentos. O cliente pncp devolve a lista
crua; este helper (testável, sem rede) filtra e adapta para a UI.

Filtro: descartar entradas cuja `justificativa` NORMALIZADA (minúsculas, sem
acento) contenha "sincroniza" — pega "Sincronizacao automatica", "sincronização",
etc. Cap defensivo de 50 eventos (os mais recentes). Mesma filosofia de
normalização do gate de citação e do matching de município (capag).
"""
import unicodedata

CAP_EVENTOS = 50


def _normalizar(s: str | None) -> str:
    """Caixa baixa, sem acento, espaços colapsados — para casar 'sincroniza'
    em qualquer grafia ('Sincronizacao', 'sincronização', ...)."""
    if not s:
        return ""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )
    return " ".join(sem_acento.lower().split())


def _e_ruido_sync(justificativa: str | None) -> bool:
    """True se a justificativa é ruído de sincronização automática (scheduler)."""
    return "sincroniza" in _normalizar(justificativa)


def _data_de(ev: dict) -> str:
    """Chave de ordenação por data (string ISO ordena lexicograficamente)."""
    return ev.get("logManutencaoDataInclusao") or ""


def filtrar_eventos(eventos: list, cap: int = CAP_EVENTOS) -> list[dict]:
    """Filtra o ruído de sync e adapta os marcos para o shape da UI.

    Cada evento de saída: {data, evento (tipo + " - " + categoria), responsavel,
    justificativa, documento}. Mantém só marcos (sem "sincroniza" na
    justificativa); ordena por data decrescente e corta no cap (mais recentes).
    """
    if not eventos:
        return []
    marcos = [ev for ev in eventos if not _e_ruido_sync(ev.get("justificativa"))]
    # mais recentes primeiro; lista crua pode vir em qualquer ordem
    marcos.sort(key=_data_de, reverse=True)
    saida = []
    for ev in marcos[:cap]:
        tipo = ev.get("tipoLogManutencaoNome") or ""
        categoria = ev.get("categoriaLogManutencaoNome") or ""
        if tipo and categoria:
            rotulo = f"{tipo} - {categoria}"
        else:
            rotulo = tipo or categoria or "Evento"
        saida.append({
            "data": ev.get("logManutencaoDataInclusao"),
            "evento": rotulo,
            "responsavel": ev.get("usuarioNome"),
            "justificativa": ev.get("justificativa"),
            "documento": ev.get("documentoTitulo"),
        })
    return saida
