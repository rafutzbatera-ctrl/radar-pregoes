# Melhorias — Radar de Pregões

Documento de manhã. Resume o que foi feito na rodada noturna e o backlog
priorizado a partir de uma **auditoria multiagente read-only** (21 agentes, 46
achados brutos; 15 verificados no código, os demais informativos). Nada aqui foi
aplicado às cegas: cada item traz o quê, arquivo, severidade, esforço, risco de
corrigir e recomendação. Itens de **risco médio** foram conscientemente
**adiados** — precisam de aprovação/cuidado e estão sinalizados.

Estado atual: **260 testes pytest verdes**, CI no GitHub Actions a cada push.

---

## 1. Feito nesta rodada (noturna)

Cinco commits de baixo risco, cada um com teste:

1. **`204a722`** — WAL + `synchronous=NORMAL`, índices v10, `GET /health` e cap
   de 2000 chars na pergunta do RAG.
   *Ganho:* concorrência leitura×escrita melhor (scheduler + requests), queries
   por `pregao_id`/filtros indexadas, healthcheck para o CI/deploy, e prompt do
   RAG protegido contra entrada patológica.
2. **`7313a01`** — toast de erro vermelho (variante por tipo), distinto do aviso
   fixo.
   *Ganho:* erro de mutação fica visível e não se confunde com o disclaimer.
3. **`a875fa0`** — migração só na subida (não a cada request).
   *Ganho:* remove trabalho repetido e a janela de corrida de migração por
   request; conexão-por-request continua segura.
4. **`511f38e`** — `_retorno` devolve 404 (não 500) se o item sumiu após o UPDATE.
   *Ganho:* concorrência rara passa a ser erro honesto (404), não crash opaco.
5. **`dff9db1`** — padroniza a chave de export para `material_ou_servico`.
   *Ganho:* remove o caso especial frágil do XLSX; refactor futuro não quebra a
   coluna em silêncio.

---

## 2. Backlog priorizado (da auditoria)

Legenda: severidade (alta/média/baixa) · esforço · risco de corrigir.

### 2.0 Honestidade do RAG — achado do eval M7 e fix (2026-06-15) ✅ RESOLVIDO

**Achado:** o eval `scripts/eval_rag.py` sobre o edital real de Imbaú mostrou
**recall 6/6 (perfeito)** mas **rejeição 0/2** — perguntas claramente fora do
escopo ("drone de vigilância", "treinamento de mergulho" num edital de
palanques) **vazavam** (score 0.82–0.85) em vez de "não encontrado". Causa: o
`multilingual-e5-small` tem **floor de similaridade ~0.82** (texto PT qualquer
pontua alto) e o **ramo léxico** do gate híbrido (`cosseno≥thr OR match FTS`)
abria a resposta para qualquer pergunta que compartilhasse um termo genérico
("fornecedor"/"profissional") com o edital. Feria os princípios 1 e 2.

**Fix (commit do gate semântico-primário):** separei a *decisão de responder* da
*inclusão de trecho* em `rag.perguntar`:
- **Gate (responde?)** = **semântico-puro**: só abre se algum chunk tem cosseno
  ≥ `RAG_THRESHOLD`. O ramo léxico **não** abre mais o gate.
- **Inclusão de trecho** (gate já aberto) = cosseno ≥ thr **OU** match léxico —
  então numa pergunta on-topic um match exato (BM25) com cosseno um pouco abaixo
  ainda entra como contexto (preserva o recall do híbrido da Onda 1; o teste
  `test_hibrido_recall_...` continua verde sem mudança).
- **Threshold recalibrado 0.84 → 0.858** (calibrado com `scripts/calibra_gate.py`
  em **2 editais reais de bens** — Imbaú/PR e Barueri/SP, órgãos e objetos
  distintos: off-topic ≤ 0.8546 < on-topic ≥ 0.8615; 0.858 = ponto médio, com
  ~0.0035 de margem de cada lado).

**Resultado (eval M7 nos 2 editais):** recall **11/11**, rejeição **4/4**,
hit-rate **15/15**; e no extrator de habilitação citação verificada **24/24** e
cobertura de categorias **100%** (`eval_habilitacao.py`). Teste de regressão
`test_gate_semantico_rejeita_match_so_lexico_generico`.

**Tradeoff residual (documentado):** pelo floor do e5-small, as faixas de cosseno
on/off-topic ficam próximas (~0.85–0.86); uma pergunta legítima nesse limbo pode
cair em "não encontrado" — erra para o lado **honesto** (princípio 1, melhor que
inventar). Upgrade opcional para separar sem esse tradeoff: **cross-encoder
reranker** (sentence-transformers já é dep; modelo local, sem chave) como camada
de gate, injetável e degradando gracioso — próximo nível, não bloqueante.

### 2.1 Bugs confirmados (corrigir — risco de fix baixo)

Todos verificados no código; nenhum exige refactor arriscado. Ordem por impacto.

| # | O quê | Arquivo | Sev. | Esforço | Risco fix |
|---|---|---|---|---|---|
| 1 | `PATCH /config` aceita `veredito_*` não-numérico → 500 em todo match/edição/sincronização até alguém corrigir a config (estado global corrompido) | `routers/config.py:38-65` | **alta** | peq. | baixo |
| 2 | Cache JSON corrompido/meio-escrito brica a query por até 6h (sem try/except no `json.loads`; escrita não-atômica) | `pncp.py:90-91,107,118-120` | média | peq. | baixo |
| 3 | RAG `/perguntar` estoura 500 se o modelo de embedding mudar sem reindexar (mismatch de dimensão no matmul) | `rag.py:316-321` | média | peq. | baixo |
| 4 | `POST /descobrir/importar` dá 500 com hit malformado (ano/seq não-numérico em `int(...)`) | `descoberta.py:117-118` via `routers/descobrir.py:414-429` | média | peq. | baixo |
| 5 | `_persistir_itens` aborta o lote inteiro se um item vier sem `numeroItem` (NOT NULL) — pregão fica sem itens em silêncio | `sincronizacao.py:114-144` | média | peq. | baixo |
| 6 | CNPJ do hit do usuário não validado flui cru para path de URL do PNCP (request forgery) e para nome de diretório local (path traversal) | `descoberta.py:116`; `pncp.py:203+`; `sincronizacao.py:150` | média | peq. | baixo |
| 7 | `_baixar_arquivos` chama `baixar_arquivo(None,...)` quando `url` é None → aborta os demais arquivos e some o edital | `sincronizacao.py:152-169` | baixa | peq. | baixo |
| 8 | Score NaN no RAG sobe ao topo e passa pelo gate de threshold (`nan < thr == False`) | `rag.py:323-324,339-341` | baixa | peq. | baixo |
| 9 | Constante morta `_MIN_INTERVALO` no cliente PNCP | `pncp.py:38` | baixa | peq. | baixo |
| 10 | Modelo `ConfigPatch` é código morto (handler usa `dict`); remover junto o import `BaseModel` | `routers/config.py:22-25` | baixa | peq. | baixo |

**Recomendação:** os itens 1–8 são correções pequenas e testáveis (cada um com
um teste de regressão óbvio). Priorize **#1** (maior raio de estrago) e **#6**
(segurança). #9 e #10 são limpeza trivial — podem ir junto. Atenção em #1: a
auditoria exagerou o raio ("todo GET cai") — na prática derruba
match/edição-de-item/sincronização, **não** a listagem/detalhe/itens nem o PDF.

### 2.2 Risco MÉDIO — conscientemente ADIADOS

Precisam de aprovação porque mudam SQL/shape de saída ou markup interativo, e
exigem cobertura de teste nova antes de tocar.

- **N+1 em `GET /pregoes`** (`routers/pregoes.py:29-63,86-98`) — média · risco
  **médio**. `listar()` chama `_resumo_pregao` por pregão, cada um com 3 SELECTs
  → 3N+1 queries na tela inicial, sem paginação. *Por que adiar:* o shape de
  saída (`itens_total`, `cobertura`, `arquivos[]`…) é consumido pelo
  `adaptarPregao` do front e reusado em `/descobrir` e no PDF; agregar com
  `GROUP BY` ou paginar exige refactor cuidadoso + teste de shape. **Os índices
  v10 (já entregues) reduzem muito o custo de cada query — atacar isto só se a
  listagem realmente pesar.**
- **N+1 no fiscal** (`services/fiscal.py:57-69`) — baixa · risco médio. 1 SELECT
  no catálogo por item; trocável por `LEFT JOIN` (mesmo padrão de
  `analisar_pregao`). *Por que adiar:* muda o SQL; convém um teste do shape
  fiscal antes. Impacto baixo hoje (poucos itens).
- **`matmul` numpy em matching/avaliação** (`services/matching.py:78-88`,
  `services/avaliacao.py:92-98`) — baixa · risco médio. Hoje é loop Python
  O(itens × produtos); dá para `vet_itens @ vet_prod.T` + argmax (numpy puro,
  respeita o princípio "só SQLite+numpy"). *Por que adiar:* muda o caminho de
  cálculo; os fakes de embed dos testes retornam **listas** — manter o fallback
  `_dot` ou converter com `np.asarray`, e reexecutar `test_m2_matching`,
  `test_p5`, `test_p6`. Ganho cresce com catálogo grande.
- **`manualChunks` no Vite** (`frontend/vite.config.js`) — baixa · risco baixo,
  mas **adiado por baixo valor**. `three`/`gsap` **já** são lazy via
  React.lazy/Suspense (não pesam no first load). A melhoria seria só um vendor
  chunk cacheável entre deploys — não é prioritário.

### 2.3 Robustez (baixo risco, opcional)

- Teto de bytes no download de PDF do PNCP (`pncp.py:257-279`) — sem limite hoje;
  PDF anormalmente grande = DoS local. Mitigado por timeout httpx 60s e
  single-user. Decidir o limite com o dono.
- `rag.ingerir` sem try por arquivo (`services/extracao.py`) — um PDF
  corrompido/protegido aborta a indexação inteira; envolver por arquivo (pular +
  logar). Teste novo com PDF ruim no meio do lote.
- `ano/seq` de hit viram 0 com valor não-numérico → link PNCP quebrado
  (`descoberta.py:117-118`). Mesma raiz do bug #4 — resolver junto validando.
- Lockfile do backend (`requirements.txt`) — só piso `>=`, sem upper-bound nem
  lock; um `pip install` futuro pode puxar major com regressão. Gerar
  `requirements.lock` (pip-compile/freeze) e commitar. **Dono valida** (muda o
  ambiente). O frontend já tem `package-lock.json`.

### 2.4 Qualidade / dívida técnica (baixa)

- **Duplicação do runner do Claude CLI** (`extratores/claude_cli.py:58-106` ×
  `rag_sintese.py:89-137`) — ~40 linhas quase idênticas, e é **código de
  segurança** (hardening anti prompt-injection: `--disallowedTools …`). O risco
  real é divergência futura (bloquear uma tool num e esquecer no outro). Extrair
  `extratores/_claude_cli_runner.py` com a lista de tools bloqueadas num lugar
  só. Risco médio (refatora 2 chamadores); cobrir com os testes de argv
  existentes.
- **Cinco helpers de normalização de texto** quase iguais (`habilitacao.py`,
  `classificador.py`, `historico.py`, `capag.py`, `routers/descobrir.py`).
  Unificar num `services/texto.py`. **Cuidado:** o `_normalizar` do gate de
  citação (`habilitacao.py`) tem regra especial markdown→espaço que **não pode
  ser perdida** (princípio 2) — manter separado ou parametrizado.
- Dois PADROES com mesmo requisito canônico e categorias diferentes — a dedup
  por nome torna a variante "proposta" inalcançável (`extratores/heuristico.py:114-117`).
  Dar nomes canônicos distintos. Decisão de produto.
- `while True` + break incondicional em `rodar_busca` (`descoberta.py:33-49`) —
  faz 1 iteração; simplificar para chamada direta. Comentário stale em
  `_itens_calculados` (`routers/pregoes.py:197-201`) — guard que nunca dispara
  em banco migrado.

### 2.5 UX / acessibilidade (baixa-média)

Sem teste de a11y no projeto — toda mudança aqui precisa verificação manual com
teclado/leitor; risco de regressão visual.

- Padrão ARIA de abas incompleto — `tablist` sem `tabpanel`/`aria-controls` nem
  navegação por setas (`AnalysisScreen.jsx:256-295`). média.
- Linha de item com `role="row"` + comportamento de botão (semântica ambígua
  para AT) (`AnalysisScreen.jsx:982-991`). média · risco médio.
- Contraste de `.silk` (10.5px) pode ficar no limite de AA em alguns fundos
  (`styles.css`). média · medir par-a-par.
- Toast sem botão de fechar nem pausa em hover (some em 5,5s fixo;
  `App.jsx:56-60`). baixa.
- Toast e aviso fixo podem se sobrepor no mobile (`App.jsx:616-629`). baixa.

> A auditoria também listou vários itens de a11y como **verificado-OK** (foco de
> teclado via `:focus-visible`, `prefers-reduced-motion` já tratado em JS,
> `role=meter` correto, barra fiscal `aria-hidden` com texto adjacente). Não há
> ação nesses — refutados como "defeito inexistente".

### 2.6 Segurança

- **CNPJ não validado** → ver bug **#6** (§2.1). É o item de segurança mais
  concreto; fix por `re.fullmatch(r"\d{14}")` em `persistir_hit` + `quote` nos
  segmentos de path.
- **CORS / sem auth** (`main.py:33-38`) — `allow_origins` já restrito a
  `localhost:5173`, mas `allow_methods`/`allow_headers` são `*` e a API não tem
  auth. Aceitável para local-first single-user; estreitar métodos para
  GET/POST/PATCH e documentar a premissa "só loopback, sem auth". Validar
  manualmente (mexer em CORS pode quebrar o dev).

---

## 3. Roadmap de fases (discutido com o dono)

| Fase | Valor | Esforço | Dependências |
|---|---|---|---|
| **RAG Fase 3 — declarações por template** | Gera minutas de declarações de habilitação a partir dos requisitos extraídos (acelera a montagem da proposta) | médio | RAG Fase 2 (síntese) já entregue; templates a definir |
| **Recall do RAG (k / híbrido)** | Menos "não encontrado" legítimo — ajustar `k`, busca híbrida (lexical + vetorial) | médio | RAG indexação atual; medir com editais reais |
| ~~**OCR para PDFs escaneados**~~ ✅ feito (15/06/2026) | Seam injetável de OCR no fallback de baixa densidade: `extrair_paginas(..., ocr=)` despacha por `RADAR_OCR` (`docling`/`off`); docling é **opcional** (`backend/requirements-ocr.txt`, fora do CI). Densidade via `RADAR_OCR_DENSIDADE`. Testado com OCR fake (sem instalar docling). | alto | módulo de extração; decidir docling vs Tesseract |
| **CAPAG de estados** | Cobre licitações estaduais no risco de pagamento (hoje forte em municípios) | médio | base do Tesouro/SICONFI por estado; seed |
| **M7 — eval do extrator** | Métrica de confiança (ragas/faithfulness) sobre 3 editais reais; valor de portfólio | médio | editais baixados; dataset de referência |
| **Notificação de novos pregões** | Avisa o dono quando o scheduler acha pregão novo (e-mail/desktop) | baixo-médio | scheduler 2×/dia já existe; canal a escolher |
| **Deploy de demo** | Vitrine pública navegável (com dados de exemplo) | médio | `GET /health` já existe; decidir host e dados |

---

## 4. Sugestão de ordem

1. **Hoje, sem aprovação extra:** bugs #1, #6, #2, #3 (§2.1) — alto impacto,
   risco de fix baixo, cada um com teste.
2. **Junto, se sobrar tempo:** #4/#5/#7/#8 e a limpeza #9/#10.
3. **Com aprovação do dono:** itens de risco médio (§2.2) — só se a performance
   pesar de fato; índices v10 já aliviaram o N+1.
4. **Roadmap:** priorizar por valor × esforço — Notificação e Deploy de demo são
   os de melhor relação para a vitrine; RAG Fase 3 e M7-eval são os de maior
   destaque técnico.
