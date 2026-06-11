# P4 — Preço esperado de disputa (lance, deságio, pisos)

Data: 2026-06-11 · Status: aprovado pelo usuário (chat) · Escopo: Radar de Pregões

## Problema
O valor do edital é TETO (pregão = leilão reverso; menor preço vence). A
margem calculada no teto é o cenário mais otimista possível — superestima
lucro e veredito. O usuário precisa raciocinar no preço em que acha que o
pregão vai fechar e saber até onde pode descer na disputa.

## Decisões de produto (usuário, 2026-06-11)
1. **Lance previsto por item** (digitado) + **deságio esperado global**
   (config, % abaixo do teto). Lance digitado vence o deságio.
2. **Pisos por item com custo**: "pode descer até R$ X mantendo a margem
   alvo" (= custo ÷ (1−margem_alvo)) e "empate em R$ Y" (= custo).
3. **Veredito no preço esperado** (lance ▸ deságio ▸ teto), com o cenário
   explícito no hero.

## Regra de preço (backend e client-side IDÊNTICOS)
- `preco_esperado` do item = `lance_previsto` ▸ senão `teto × (1 − desagio_esperado)`
  ▸ senão teto. Item sigiloso (teto nulo): só entra se houver `lance_previsto`.
- margem = (preco_esperado − custo_efetivo) / preco_esperado;
  lucro = (preco_esperado − custo_efetivo) × qtd.
- Agregados, veredito e medidor passam a usar preco_esperado. A coluna/cartão
  continua EXIBINDO o teto oficial (dado do PNCP, nunca some) — o preço
  esperado aparece ao lado, identificado.
- `desagio_esperado` default **0.00** (= teto): sem deságio inventado; o
  usuário configura o seu.
- Simulação de custo máximo (P3) passa a usar preco_esperado como base.
- Pisos (item com custo): `lance_minimo_alvo = custo ÷ (1 − margem_alvo)`;
  `empate = custo`. São derivações do custo do usuário — não entram no
  veredito, são guia de disputa.

## Modelo (migração v4)
```sql
ALTER TABLE itens_pregao ADD COLUMN lance_previsto REAL;
INSERT OR IGNORE INTO config(chave, valor) VALUES ('desagio_esperado', '0.00');
```

## API
- `PATCH /itens/{id}`: aceita também `lance_previsto: float|null` (ge=0;
  null limpa). Recalcula análise; retorna `{item, pregao}`.
- `PATCH /config`: `desagio_esperado` (0–0.90; 422 fora). Mudança de deságio
  exige recálculo dos agregados de TODOS os pregões? Não — recalcular sob
  demanda: ao mudar a config, a UI refaz o fetch do pregão aberto e o
  backend recalcula no GET? Os agregados são persistidos por analisar_pregao;
  decisão: `PATCH /config` com desagio_esperado dispara re-análise apenas dos
  pregões com salvo=1 OU com itens (loop barato, banco local) para manter
  cartões/funil coerentes.
- `GET /pregoes/{id}/itens`: expõe `preco_esperado`, `fonte_preco`
  ("lance"|"desagio"|"teto"|null), `lance_minimo_alvo`, `empate`
  (os dois últimos só com custo efetivo); margem/lucro já no preço esperado.
- `analise.py`: preco esperado na conta agregada (mesma precedência).

## UI
- Cabeçalho da tabela de itens: controle "deságio esperado N%" ao lado da
  "margem alvo N%" → PATCH config + refetch.
- Célula "Valor unit. estimado": teto oficial sempre visível; quando o preço
  esperado difere, mostra o esperado em destaque com fonte ("lance"/"−15%")
  e o teto vira referência menor (silk). Campo de lance editável na linha
  (input mono, padrão CostInput) e no DetailPanel.
- DetailPanel: bloco "Disputa do item": lance previsto (editável), preço
  esperado, pisos ("desce até R$ X no alvo · empate R$ Y") rotulados como
  guia de disputa.
- Hero: sub-rótulo do cenário sob o veredito: "cenário: teto" | "cenário:
  deságio de N%" | "cenário: N lances previstos · deságio M%".
- `helpers.analisar`: paridade total (estado ao vivo de lance também —
  `estado.lances[n]` análogo a custos).

## Testes
Migração v4; precedência lance ▸ deságio ▸ teto na análise (agregados e
veredito mudam com deságio); sigiloso com lance entra na conta; pisos
corretos; PATCH lance (422 negativo, null limpa); validação desagio_esperado;
re-análise após PATCH config; client build verde.

## Fora de escopo
Deságio por modalidade/órgão; histórico de deságios reais de disputas;
lances por fornecedor concorrente.
