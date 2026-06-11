# P5 — Potencial aderente, enriquecimento na descoberta e filtros de valor

Data: 2026-06-12 · Status: aprovado pelo usuário (chat) · Escopo: Radar de Pregões

## Problema
Editais gigantes (ex.: obra com 426 itens) afogam a lista — o usuário não
consegue ver "o que é melhor PARA MIM". Valor global vem nulo na busca e os
itens só eram buscados ao abrir pregão por pregão.

## Decisões de produto (usuário, 2026-06-12)
1. **Enriquecer na descoberta**: a rodada da busca (manual e 2×/dia) já puxa
   itens + matching + análise de cada pregão novo (e dos antigos ainda sem
   itens). Manual fica ~30-60s mais lento (1 req/s) — aceito.
2. **Potencial aderente** no cartão e no ranking: só itens que casam com o
   catálogo (sugestão ≥ 0,90 ou confirmados/manuais).
3. **Faixa de valor (mín/máx) + ordenação** (potencial ▸ valor ▸ prazo ▸
   recente) nas listas do radar/Meus pregões.

## Definições
- **Item aderente** = item com `produto_id` preenchido (sugerido ou
  confirmado). Itens sem preço esperado (sigiloso sem lance) ficam fora.
- **Receita aderente** (persistida) = Σ preço_esperado × qtd dos itens
  aderentes. **Potencial aderente** (exibido) = receita_aderente ×
  margem_alvo — SEMPRE rotulado "sim." (é cenário, não promessa).
  Persistir a RECEITA (não o potencial) evita reprocessar tudo quando a
  margem alvo muda; deságio já dispara re-análise (P4).
- **Valor efetivo do pregão** (para filtro/ordenação) = valor_global ▸
  Σ valor_total dos itens (valor_itens já computado no resumo).

## Modelo (migração v5)
```sql
ALTER TABLE pregoes ADD COLUMN receita_aderente REAL;
ALTER TABLE pregoes ADD COLUMN itens_aderentes INTEGER;
```
Preenchidas por `analise.analisar_pregao` (que já roda no sync leve/completo).

## Backend
- `analise.analisar_pregao`: além do existente, calcula `itens_aderentes`
  (count produto_id NOT NULL com preço esperado) e `receita_aderente`
  (Σ preço_esperado × qtd desses) e persiste nas colunas novas.
- `descoberta.rodar_busca(..., enriquecer=True, embed=None)`: após persistir,
  para cada pregão NOVO desta rodada + pregões da busca ainda com 0 itens,
  roda `sincronizacao.sincronizar_itens` (melhor-esforço; falha de um não
  derruba a rodada; loga). Resultado ganha `enriquecidos: n`. O scheduler usa
  o mesmo caminho. `embed` injetável para testes.
- `GET /pregoes`: params novos `valor_min: float`, `valor_max: float`
  (sobre o valor efetivo) e `ordem: potencial|valor|prazo|recente` (default
  recente). Filtro/ordenação em Python sobre os resumos (listas pequenas);
  `potencial` ordena por receita_aderente desc (nulos no fim), `valor` por
  valor efetivo desc, `prazo` por data_fim_vigencia asc (nulos no fim).
- Importar do PNCP ao vivo: inalterado (a análise auto-sincroniza ao abrir).

## Frontend
- Listas (radar e Meus pregões): inputs mono "valor mín"/"valor máx" +
  seletor "Ordenar: Potencial p/ você ▸ Maior valor ▸ Prazo ▸ Mais recente"
  → params do GET. Refetch com debounce.
- Cartão: chip de potencial quando `itens_aderentes > 0`:
  `"N itens seus · potencial R$ X sim."` (X = receita_aderente ×
  margem_alvo da config; tag sim. no padrão âmbar tracejado do P4.5).
  Quando enriquecido (itens_total>0) e 0 aderentes: chip cinza
  `"nenhum item do seu ramo"`. Sem itens ainda: nada.
- "Rodar agora": texto do spinner vira "buscando e analisando itens (pode
  levar ~1 min)…".
- `api.js`: adaptarPregao ganha `receitaAderente`/`itensAderentes`;
  listarPregoes aceita os params novos.

## Testes
Migração v5; analisar_pregao persiste receita/itens aderentes (sugerido conta,
sem produto não conta, sigiloso sem lance não conta); rodar_busca enriquece
novos e antigos-sem-itens (com cliente/embed fakes) sem quebrar em falha de um;
GET /pregoes filtra por faixa e ordena por potencial/valor/prazo; front build.

## Fora de escopo
Enriquecimento assíncrono/fila; potencial por categoria; cache de embeddings.
