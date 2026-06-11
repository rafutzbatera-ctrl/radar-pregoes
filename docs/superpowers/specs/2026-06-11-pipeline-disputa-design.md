# P2 — Pipeline de disputa + resumo de resultados

Data: 2026-06-11 · Status: aprovado pelo usuário (chat) · Escopo: Radar de Pregões

## Objetivo
Acompanhar o funil de disputa dos pregões salvos (do orçamento ao ganho/perdido)
e ver resultados agregados, sem sair de "Meus pregões". Gap identificado na
análise comparativa com a Zionn.ai; versão enxuta para usuário único.

## Decisões de produto (usuário, 2026-06-11)
- Status: conjunto FIXO de 6 — `cotacao → habilitacao → disputando → ganho |
  perdido | suspenso` (sem editor de status nesta versão).
- Local: evoluir a tela "Meus pregões" (alternância Lista | Quadro). Sem item
  novo de menu.
- Campos extras: `data_disputa` e `valor_final` (proposto/arrematado).
- Dashboard: faixa-resumo no topo de Meus pregões (sem tela dedicada).

## Arquitetura escolhida
Colunas novas na própria tabela `pregoes` (abordagem A). Alternativa B (tabela
de transições com histórico) rejeitada por YAGNI — ninguém pediu auditoria.

### Modelo de dados — migração v2 (`backend/app/db.py`)
```sql
ALTER TABLE pregoes ADD COLUMN status_pipeline TEXT;  -- NULL = fora do funil
ALTER TABLE pregoes ADD COLUMN data_disputa TEXT;     -- ISO "YYYY-MM-DD HH:MM"
ALTER TABLE pregoes ADD COLUMN valor_final REAL;      -- R$ proposto/arrematado
```
Regras:
- Salvar pregão (`salvo=1`) com `status_pipeline IS NULL` ⇒ seta `cotacao`
  (no PATCH do backend, não na UI).
- Dessalvar preserva `status_pipeline` (some do funil porque o funil filtra
  `salvo=1`; re-salvar volta onde estava).

### API
- `PATCH /pregoes/{id}`: aceita também `status_pipeline`
  (`Literal[cotacao|habilitacao|disputando|ganho|perdido|suspenso] | None`),
  `data_disputa: str | None`, `valor_final: float | None`. Inválido ⇒ 422.
- `GET /pipeline/resumo`: sobre pregões `salvo=1`:
  `{por_status: {status: n}, total_funil, ganhos, perdidos,
    taxa_ganho: ganhos/(ganhos+perdidos) | null,
    valor_ganho: Σ valor_final dos ganhos COM valor preenchido | null,
    ganhos_sem_valor: n}`.
  Princípio 1: valor_ganho nunca usa estimativa como se fosse resultado;
  sem dado ⇒ null e a UI mostra "—".
- Colunas novas entram em `GET /pregoes`/`GET /pregoes/{id}` automaticamente
  (linha completa já é serializada).

### UI (frontend/src)
- "Meus pregões": faixa-resumo no topo (padrão visual `.resumo`): cartões por
  status, taxa de ganho, valor ganho. Alternância **Lista | Quadro** com o
  mesmo segmentado do modo PNCP ao vivo.
- Quadro: 6 colunas fixas; cartão compacto (título, órgão, valor estimado,
  chip de veredito, data da disputa); ordenação por `data_disputa` asc,
  nulos no fim. Mudança de status via SELECT no cartão (drag & drop fica para
  uma versão futura). `data_disputa` e `valor_final` editáveis no cartão
  (inputs mono, padrão CostInput/data).
- Tela de análise: módulo "Disputa" (status + data + valor final) + botão
  "Salvar no funil" quando `salvo=0` (hoje a UI não tem ação de salvar).
- Mutações: otimista → API → reverte com toast (padrão existente).

### Testes (pytest; suíte hoje: 84 verdes)
- Migração v2 sobre banco v1 populado preserva dados e é idempotente.
- PATCH: status inválido 422; válido persiste; salvar ⇒ `cotacao` automático;
  dessalvar/re-salvar preserva status.
- /pipeline/resumo: contagens, taxa (null quando 0 disputas encerradas),
  valor_ganho null sem valores, ganhos_sem_valor.
- Front: `npm run build` verde.

## Fora de escopo (desta entrega)
Drag & drop no quadro; editor de status; histórico de transições; tela de
dashboard com gráfico mensal; Pedidos/Entregas pós-ganho.
