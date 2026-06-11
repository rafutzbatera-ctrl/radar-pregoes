# P3 — Custo por item, margem alvo e matching conservador

Data: 2026-06-11 · Status: aprovado pelo usuário (chat) · Escopo: Radar de Pregões

## Problema
O matching e5 empurrou sugestão errada (Fone Ouvido → Microfone sem fio, 0,88)
e a análise dependia 100% do catálogo: item sem match ficava fora da conta,
mesmo quando o usuário sabe o custo de cabeça. A "prévia" de margem negativa
em sugestões erradas assustava.

## Decisões de produto (usuário, 2026-06-11)
1. **Custo digitado por item** entra na conta como dado do usuário (igual ao
   custo do catálogo). Catálogo vira atalho opcional.
2. **Simulação por margem alvo** (config `margem_alvo`, padrão 20%) como guia
   nos itens SEM custo: custo máx. admissível e lucro no alvo — SEMPRE
   rotulado "simulação", NUNCA entra no veredito.
3. **Matching conservador**: threshold 0,83 → 0,90; recusa memorizada por item
   (não re-sugere o mesmo produto); sem prévia de margem em sugeridos.

## Regra nova da conta (substitui parte do CLAUDE.md §6.2 — atualizar lá)
- custo efetivo do item = `custo_manual` ▸ senão custo do produto com match
  CONFIRMADO ▸ senão sem custo.
- Entra na margem/lucro/veredito todo item com custo efetivo e valor unitário
  oficial (não sigiloso). Cobertura = itens com custo efetivo / total.
- Editar custo NA TABELA DO PREGÃO grava `custo_manual` (override local do
  pregão); o custo do catálogo só muda na tela Meu catálogo.

## Modelo (migração v3)
```sql
ALTER TABLE itens_pregao ADD COLUMN custo_manual REAL;
ALTER TABLE itens_pregao ADD COLUMN produtos_recusados TEXT;  -- JSON [ids]
INSERT OR IGNORE INTO config(chave, valor) VALUES ('margem_alvo', '0.20');
```

## API
- `PATCH /itens/{id}` `{custo_manual: float|null}` (null limpa → volta ao
  catálogo se houver) → recalcula análise; retorna `{item, pregao}` (como o
  endpoint de match). Validação: custo ≥ 0 → 422 se negativo.
- `POST /itens/{id}/match` com `produto_id=null` (recusa): além de limpar,
  appenda o produto recusado em `produtos_recusados`.
- `GET /pregoes/{id}/itens`: expõe `custo_manual`, `custo_efetivo`,
  `fonte_custo` ("manual"|"catalogo"|null) e, quando sem custo e com valor
  unitário, `simulacao_custo_max` e `simulacao_lucro` (margem alvo da config).
  `margem`/`lucro` passam a usar o custo efetivo.
- `PATCH /config`: aceita `margem_alvo` (float 0–0,95; 422 fora).
- `matching.sugerir_matches`: pula produtos em `produtos_recusados` do item.
- `settings.MATCH_THRESHOLD = 0.90`.

## UI
- Tabela de itens: célula de custo SEMPRE editável (CostInput), mesmo sem
  match; vazia mostra placeholder "máx R$ X (alvo)" da simulação; blur/Enter
  → PATCH custo_manual. Item com produto confirmado E custo manual mostra
  tag "manual" + ação limpar (volta ao custo do catálogo).
- MatchBar de sugerido: só "Sugestão: <produto> · NN% · Confirmar/Trocar/
  Recusar" — sem pill de margem prévia.
- DetailPanel: bloco de CUSTO primeiro (editável + simulação rotulada);
  match vira seção secundária.
- Controle da margem alvo: input compacto junto do cabeçalho da tabela de
  itens ("margem alvo NN%") → PATCH /config; recarrega itens (simulação).
- helpers.analisar (client-side, recálculo ao vivo) espelha a regra nova.
- Hero/veredito: inalterados na semântica — só custo real conta.

## Fora de escopo
Sugestão de catálogo por histórico de recusas global; multi-margem por
categoria; edição de catálogo a partir do pregão.
