# Re-skin "Noite Fósforo" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-skin do app inteiro na linguagem da landing (noite + fósforo), CSS-only, sem mudar layout/comportamento.

**Architecture:** Mesmos nomes de tokens com novos valores (spec §2) + sweep semântico dos ~199 pontos de cor hardcoded do styles.css (1718 linhas) seguindo a regra de ouro da spec §3 (usos de --tinta como superfície re-mapeados à mão). 4 cores inline no JSX do app mapeadas a variáveis.

**Tech Stack:** CSS variables; React (só cores inline); verificação via build + preview DevTools.

**Spec:** `docs/superpowers/specs/2026-06-12-reskin-noite-fosforo-design.md` (tokens exatos, regras por componente, aceite).

**Verificação por task:** `npm run build` verde + preview da(s) tela(s) afetada(s) com console limpo. Sem test runner JS (convenção do projeto). NUNCA matar processos nas portas 8000/5173.

---

### Task 1: Tokens + base do shell

**Files:** Modify: `frontend/src/styles.css` (bloco :root, body, .app, sidebar, cabeçalhos de tela, :focus-visible, scrollbars)

- [ ] Trocar os valores do bloco `:root` pelos da spec §2 (+ --fundo-2/--halo), atualizando o comentário com nota datada.
- [ ] Re-mapear a sidebar (usos de --tinta como SUPERFÍCIE → #050807; item ativo com acento fósforo; `.nav-apresentacao` conferida).
- [ ] body/atmosfera: radial-gradients fosforosos a ~4% (spec §4).
- [ ] `:focus-visible` global → outline --sinal.
- [ ] `npm run build` verde; preview: shell/side navegável e legível em todas as telas (mesmo com o miolo ainda desatualizado).
- [ ] Commit: `Reskin T1: tokens noite-fosforo + shell (sidebar, foco, atmosfera)`

### Task 2: Tela Encontrar (radar + PNCP ao vivo)

**Files:** Modify: `frontend/src/styles.css` (seções de cards, filtros, chips, MultiSelect, toggle, faixa de valor, skeletons, estados vazio/erro/carregando)

- [ ] Sweep semântico de TODAS as regras dessas seções (regra de ouro §3; sombras pretas + hairlines; LEDs/status semânticos; botões primários = fósforo sobre noite).
- [ ] `npm run build` verde; preview: Encontrar nas duas fontes, com cards reais, chips, dropdowns abertos, skeleton e estado de erro visíveis e AA.
- [ ] Commit: `Reskin T2: tela Encontrar (cards, filtros, estados)`

### Task 3: Análise + painéis de detalhe

**Files:** Modify: `frontend/src/styles.css` (hero da análise, medidor, tabela de itens, controles de margem/deságio, abas, habilitação/checklist, fiscal, DetailPanel)

- [ ] Sweep semântico (números mono neve; chips "simulação"/"sugestão" mantêm rótulos com AA; vereditos nas cores semânticas; tabela com hairlines e hover --fundo-2).
- [ ] `npm run build` verde; preview: abrir um pregão real, conferir hero blend, tabela, checklist.
- [ ] Commit: `Reskin T3: analise (hero, tabela, habilitacao, fiscal)`

### Task 4: Funil/Kanban, Buscas, Catálogo, toasts + JSX inline

**Files:** Modify: `frontend/src/styles.css` (faixa-resumo, quadro, colunas, cartões, BuscasScreen, CatalogScreen, toasts/diálogos) · `frontend/src/helpers.jsx` (3 cores inline) · `frontend/src/App.jsx` (1 cor inline)

- [ ] Sweep dessas seções + mapear as 4 cores inline a variáveis (`var(--…)`).
- [ ] `npm run build` verde; preview: Meus pregões lista+quadro, Buscas, Catálogo, um toast.
- [ ] Commit: `Reskin T4: funil, buscas, catalogo, toasts e cores inline`

### Task 5: Varredura final + prova

- [ ] Grep no styles.css: nenhum hex claro órfão (#E4E7E1, #FAFBF8, #CDD2CA, brancos sobre claro) e nenhum verde/âmbar/vermelho antigo (#149357, #C98A04, #CC4537).
- [ ] Preview DevTools: console zero erros; screenshots de TODAS as telas (aceite §6.2); contraste amostrado (--silk e --tinta-2 sobre --painel).
- [ ] `cd backend; .venv\Scripts\python -m pytest tests -q` → 172 passed.
- [ ] Revisão opus-reviewer; ajustes; commit final.
