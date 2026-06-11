# Política global — orquestração multiagente com economia de tokens

Vale para TODOS os projetos. Regras específicas de projeto ficam no ./CLAUDE.md local e têm precedência.

## Princípio
Use sempre o modelo mais barato que resolve a tarefa. Suba de modelo só quando o problema exigir.

## Quando delegar (e para quem)
- **haiku-extractor** → ler arquivos, extrair, resumir, checklist, busca, mapear projeto, converter formato.
- **opus-planner** → arquitetura, plano técnico, trade-offs, decisão complexa. (read-only)
- **sonnet-implementer** → escrever/editar código, refatorar, testes, mexer em arquivos.
- **opus-reviewer** → revisão crítica de segurança/qualidade/regressão antes do aceite. (read-only)

## Regras de economia
- Antes de ler arquivos grandes na sessão principal, delegue ao haiku-extractor e peça só o resumo.
- Não use o modelo da sessão para tarefa mecânica se um agente mais barato resolve.
- Tarefa pequena ou mudança pontual: resolva direto, NÃO orquestre.
- Cada delegação tem escopo fechado e relatório curto: resumo, arquivos, riscos, próximo passo.
- Muitos arquivos → haiku mapeia primeiro. Arquitetura → opus planeja antes do sonnet executar.
  Antes do aceite → opus revisa.

## Fluxo padrão para tarefa grande
MAPEAR (haiku) → PLANEJAR (opus) → EXECUTAR em etapas (sonnet) → REVISAR (opus) → DECIDIR/VALIDAR.

## Custo (jun/2026, input/output por Mtok): Fable $10/$50 · Opus $5/$25 · Sonnet $3/$15 · Haiku $1/$5
Rodar tudo em Fable é caro. Reserve Fable/Opus para decisão e revisão; Sonnet executa; Haiku lê.
