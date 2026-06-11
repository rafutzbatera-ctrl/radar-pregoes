# Política global — orquestração multiagente (MODO MAX: Fable + Opus)
# TEMPORÁRIO (~1 mês). Original arquivado — reverter depois.
Vale para TODOS os projetos. Regras específicas de projeto ficam no ./CLAUDE.md local e têm precedência.

## Princípio
Plano Max: o custo por token não importa, o que importa é o LIMITE DE USO e o contexto limpo.
Opus é o padrão para tudo; Fable só na sessão principal (fable-orchestrator) para decisão e validação.

## Quando delegar (e para quem)
- **opus-extractor** → ler arquivos, extrair, resumir, checklist, busca, mapear projeto, converter formato.
- **opus-planner** → arquitetura, plano técnico, trade-offs, decisão complexa. (read-only)
- **opus-implementer** → escrever/editar código, refatorar, testes, mexer em arquivos.
- **opus-reviewer** → revisão crítica de segurança/qualidade/regressão antes do aceite. (read-only)

## Regras de economia (de limite e de contexto)
- Antes de ler arquivos grandes na sessão principal, delegue ao opus-extractor e peça só o resumo
  (isolamento de contexto continua valendo, mesmo sem diferença de preço).
- Tarefa pequena ou mudança pontual: resolva direto, NÃO orquestre.
- Cada delegação tem escopo fechado e relatório curto: resumo, arquivos, riscos, próximo passo.
- Muitos arquivos → opus-extractor mapeia primeiro. Arquitetura → opus-planner antes do
  opus-implementer executar. Antes do aceite → opus-reviewer.

## Fluxo padrão para tarefa grande
MAPEAR (opus-extractor) → PLANEJAR (opus-planner) → EXECUTAR em etapas (opus-implementer) → REVISAR (opus-reviewer) → DECIDIR/VALIDAR (orquestrador).

## Consumo de limite (referência API por Mtok: Fable $10/$50 · Opus $5/$25)
Fable consome a janela 5h/semanal ~2x mais rápido que Opus por token. Reserve Fable para a
sessão orquestradora; Opus planeja, executa, lê e revisa.
