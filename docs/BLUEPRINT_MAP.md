# BLUEPRINT_MAP — Visão do dono × Realidade do código

Espelho honesto entre o blueprint de visão (`../plataforma_pensamento.md`, a
arquitetura/sonho em 5 camadas) e o que o **Radar de Pregões** efetivamente tem
hoje no código. Não é um roadmap nem uma promessa: cada linha foi conferida
contra arquivos reais (`backend/app/services/`, `backend/app/routers/`,
`frontend/src/`, [`../CLAUDE.md`](../CLAUDE.md), [`../README.md`](../README.md)).
Seguindo o **princípio nº 1 do projeto** (nunca inventar), só está marcado ✅ o
que foi confirmado no código nesta verificação; na dúvida fica 🟡 com o que
falta checar, e o que não existe fica ⬜.

Observação de escopo importante: o blueprint descreve um **SaaS multi-tenant
comercial** (billing, equipes, alertas WhatsApp, robô de lances). O Radar é um
recorte deliberado disso — **single-user, local-first, sem custo, sem conta**,
focado no produtor de áudio/vídeo/AV. Por isso várias categorias do blueprint
estão "⬜ Falta" **por decisão consciente**, não por dívida (ver seção de
decisões adiante).

---

## Mapa principal — categorias do blueprint × estado atual

As categorias abaixo são as do blueprint (§2 "Mapa-mestre" e as 5 camadas §0).

| Categoria do blueprint | Status | O que existe hoje (com arquivo) | O que falta p/ fechar |
|---|---|---|---|
| **1. Cobertura de editais (ingestão PNCP)** | ✅ Temos | Cliente PNCP com retry/backoff/cache/rate-limit (`backend/app/pncp.py`); busca textual + consulta em massa, buscas salvas e scheduler 2×/dia (`services/descoberta.py`, `services/sincronizacao.py`, `routers/buscas.py`, `routers/descobrir.py`) | Cobertura PNCP completa para o caso de uso. |
| **2. Scrapers fora do PNCP (municipais, BLL, BNC, Diários)** | ⬜ Falta | Nenhum scraper no código (`grep playwright/scrapy/scraper` → vazio) | Adapters Playwright por portal. Fora do escopo v1 do projeto (CLAUDE.md §6.5). |
| **3. Normalização + dedup ("vocabulário variado")** | 🟡 Parcial | Dedup por `numero_controle_pncp` com `ON CONFLICT DO NOTHING` (`services/descoberta.py:115-151`); schema canônico em SQLite (CLAUDE.md §5); classificador de objeto "só compra de bens" validado contra corpus rotulado (`services/classificador.py`) | Falta dedup fuzzy (rapidfuzz) por órgão+processo+ano — só há dedup exato pela chave PNCP; sem múltiplas fontes, o ganho é menor. |
| **4. Enriquecimento CNPJ (Receita/BrasilAPI)** | ⬜ Falta | Não há chamada a Receita/BrasilAPI no código (`grep brasilapi/receita/cnae` → nada relevante) | Exige fonte externa; não há classificação por CNAE do fornecedor. |
| **5. Busca híbrida (BM25 léxico + embeddings + reranking)** | 🟡 Parcial | **Híbrida confirmada**: cosseno e5 + BM25 via SQLite **FTS5**, fundidos por **Reciprocal Rank Fusion (RRF, k=60)**, com degradação para só-vetor sem FTS5 (`services/rag.py`, blocos "FTS5 (léxica BM25)" e "Reciprocal Rank Fusion") — isso é o RAG sobre o edital | Falta a busca híbrida aplicada à **descoberta** de editais (hoje a descoberta usa a busca textual do PNCP, não índice híbrido local); e não há reranker cross-encoder (RRF cobre a fusão). |
| **6. Score de aderência ("esse edital é pra mim?")** | ✅ Temos | Aderência por melhor cosseno do item × catálogo ≥ threshold 0.90, em memória no modo ao vivo (`services/avaliacao.py`) e como matching persistido com human-in-the-loop (`services/matching.py`); receita/itens aderentes agregados | Versão por regras+semântica; ML (LightGBM) com sinal de conversão é V2/V3 do blueprint, não feito. |
| **7. RAG sobre o edital (resumo/checklist/conversar)** | ✅ Temos | Parsing PDF (`services/extracao.py`, pymupdf4llm), chunking com offsets verbatim + indexação e5 (`services/rag.py`), Q&A extrativo, e **síntese em prosa opcional** via Claude CLI local desarmado com gate duro (`services/rag_sintese.py`); aba "Perguntar ao edital" no front (`frontend/src/api.js` ragPerguntar/ragStatus/ragIndexar) | Recall (ajuste de k / mais cobertura) é melhoria conhecida (MELHORIAS §3). |
| **8. Citar a página exata (anti-alucinação)** | ✅ Temos | Gate de citação: extração de habilitação retorna excerto literal + página, verificado contra o texto do PDF por normalização (`services/habilitacao.py` `verificar_citacao`, reusado em `rag_sintese.py`); offsets verbatim no RAG | Cumpre o princípio nº 2 do projeto. |
| **9. Gerar impugnação/recurso/proposta (RAG jurídico)** | ⬜ Falta | Não há geração de peças (`grep impugnac/minuta` só pega regex de fim-de-documento no heurístico) | V3 do blueprint, alto risco jurídico. "RAG Fase 3 — declarações por template" está no roadmap (MELHORIAS §3), ainda não feito. |
| **10. Histórico de preços para calibrar proposta** | 🟡 Parcial | Resultados/homologação por edital: vencedor, valor homologado e deságio real praticado por item (`services/resultados.py`, `routers/pregoes.py:418-431`) — calibra o `desagio_esperado` | Falta série temporal agregada por item/órgão ao longo do tempo (o blueprint pede TimescaleDB/DuckDB); hoje é por edital, sob demanda, não um histórico acumulado consultável. |
| **11. Inteligência de concorrentes (por CNPJ)** | 🟡 Parcial | `services/resultados.py` extrai CNPJ/razão social/porte do vencedor por item (quem ganhou) | Falta a visão agregada por concorrente (perfil de um CNPJ ao longo de vários editais) e enriquecimento Receita. |
| **12. Órgão "bom pagador" (CAPAG)** | ✅ Temos | CAPAG esfera-aware com fonte Tesouro Nacional/SICONFI, casada por CNPJ→IBGE; federal/sem-dado não recebe nota chutada (`services/capag.py`, `routers/pregoes.py:452`, endpoint `/pregoes/{id}/capag`); front `api.capag` | Heurística/nota oficial; o preditivo ML do blueprint (V3) não está feito. "CAPAG de estados" mais ampla está no roadmap. |
| **13. Prever quem vence (ML supervisionado)** | ⬜ Falta | Nenhum modelo preditivo no código | V3 do blueprint, exige volume de dados rotulados. |
| **14. Alertas multi-canal (WhatsApp/e-mail/Telegram/voz, < 2 min)** | ⬜ Falta | Nenhuma integração de notificação (`grep smtp/whatsapp/telegram/resend/webhook` → vazio); o scheduler marca "novo" no banco mas não dispara canal | "Notificação de novos pregões" (e-mail/desktop) está no roadmap (MELHORIAS §3). Canais que exigem conta/credencial externa ficam fora por decisão (ver abaixo). |
| **15. Gestão documental + vencimento de certidões** | ✅ Temos | CRUD de certidões com status calculado a partir de "hoje" (vencida/vence_em_breve/sem_validade/ok), janela de 30 dias e alertas (`services/certidoes.py`, `routers/certidoes.py`, `frontend/src/CertidoesScreen.jsx`, `api.alertasCertidoes`) | Cumpre o item #13 do blueprint. Falta storage S3/MinIO dos PDFs (o blueprint cita; aqui é metadado de validade, não guarda o arquivo da certidão). |
| **16. Monitor do chat do pregoeiro** | ⬜ Falta | Nenhum monitor de sessão autenticada | V2/alto risco; fora do escopo v1 (CLAUDE.md §6.5). |
| **17. Robô de lances** | ⬜ Falta | Nada | V3, máximo risco jurídico+técnico; explicitamente fora de escopo (CLAUDE.md §6.5). |
| **18. Onboarding/educação (RAG Lei 14.133)** | ⬜ Falta | Há referências à Lei 14.133 só como fonte do checklist base (`backend/app/dados/checklist_base.json`), não um assistente de onboarding | V2 do blueprint. |
| **19. App web (frontend)** | ✅ Temos | React + Vite + Framer Motion: telas de análise, descoberta, certidões, kanban, detalhe, landing 3D lazy (`frontend/src/AnalysisScreen.jsx`, `FindScreen.jsx`, `CertidoesScreen.jsx`, `Kanban.jsx`, `DetailPanel.jsx`, `landing/`) | Mobile nativo (React Native) é V2 do blueprint; PWA não confirmado nesta verificação. |
| **20. Análise de margem/lucro/veredito** | ✅ Temos | (Não é categoria explícita do blueprint, mas é o coração do produto) margem/lucro/veredito sobre preço esperado de disputa, custo efetivo, cobertura (`services/analise.py`, `services/avaliacao.py`, CLAUDE.md §6.2); selo fiscal/NF-e (`services/fiscal.py`) | — |
| **21. Billing / cancelamento fácil / multi-tenant / RBAC** | ⬜ Falta | Sem auth, sem billing, single-user (`grep stripe/asaas/billing/auth` → vazio; CORS restrito a localhost) | Exige conta/cobrança; fora do ethos local-first single-user por decisão. |
| **22. Orquestração transversal (n8n/Temporal/Celery)** | ⬜ Falta (por design) | APScheduler embutido (`backend/app/scheduler.py`, ligado em `main.py:24-25`) cobre o agendamento; sem n8n/Celery/Temporal | O blueprint trata isso como "categorias"; APScheduler in-process atende o agendamento single-user sem fila externa. |
| **23. Observabilidade (Grafana/Prometheus/Sentry)** | 🟡 Parcial | `GET /health` (`routers/health.py`) e logging por módulo (`logging.getLogger("radar.*")`) | Sem métricas/erros centralizados; aceitável para single-user local. |

---

## Decisões de arquitetura conscientes

Estas escolhas são **deliberadas** e satisfazem as *categorias* do blueprint
sem adotar a stack pesada que ele lista — o próprio blueprint pede para tratar
as ferramentas como categorias, não como obrigações de marca (§ "Observação
final").

### Não migrar para Postgres / pgvector / Qdrant / OpenSearch / TimescaleDB

O blueprint sugere Postgres + pgvector (vetores), `ts_vector`/OpenSearch (BM25
léxico) e TimescaleDB (preços). O Radar entrega as **mesmas categorias** com
**SQLite + numpy + FTS5 + e5 local**:

- **Vector store** → vetores como BLOB float32 no SQLite; busca = `matriz @ q`
  em numpy (`services/rag.py`, `services/matching.py`). Cobre a categoria
  "embeddings semânticos" sem serviço externo.
- **Léxico BM25** → SQLite **FTS5** nativo (`rag_fts`), sem dependência nova
  (`services/rag.py`, bloco "FTS5 (léxica BM25)").
- **Busca híbrida** → **RRF** fundindo cosseno e5 + BM25 FTS5
  (`services/rag.py`, "Reciprocal Rank Fusion"). É exatamente a categoria
  "busca híbrida" do blueprint §4, com degradação graciosa para só-vetor.

Motivo: **ethos local-first, sem custo, sem conta, single-user**. Um banco
vetorial dedicado ou um cluster OpenSearch adicionaria operação e custo sem
ganho real no volume de um usuário. O mesmo modelo e5 serve matching e RAG (um
modelo, dois usos). A migração só se justifica se o produto virar multi-tenant
em escala — o que hoje está fora de escopo.

### Itens que exigem conta/credencial externa ficam fora do escopo automatizado

Por princípio (e por serem **fora do escopo v1** em CLAUDE.md §6.5), o sistema
**não automatiza** nada que dependa de conta de terceiros, credencial sensível
ou cobrança:

- **WhatsApp / e-mail / Telegram / voz** (alertas) — exigem provedor/conta
  (Meta Cloud API, Z-API, Resend...). A notificação de novos pregões prevista
  no roadmap nasce por canal local (desktop/e-mail próprio), não como SaaS de
  mensageria.
- **Deploy hospedado / billing / multi-tenant / RBAC** — contrariam o
  local-first single-user; sem auth e CORS preso a `localhost`.
- **Robô de lances / monitor do chat do pregoeiro** — exigem certificado
  ICP-Brasil e sessão autenticada no portal, com risco jurídico (TCU). Fora de
  escopo por princípio.

Isso preserva o **princípio nº 1** (nunca inventar / nunca prometer o que não
controla) e mantém o produto auditável e sem segredos de terceiros no caminho.

---

## Próximas fases sugeridas (valor × esforço)

Derivado do que ficou 🟡/⬜ acima, cruzado com o roadmap já discutido em
[`MELHORIAS.md §3`](MELHORIAS.md) (não duplicado aqui — consulte lá os detalhes
de esforço e dependências). Foco no que fecha lacunas do blueprint dentro do
ethos local-first:

1. **Notificação de novos pregões (canal local)** — valor alto, esforço
   baixo-médio. Fecha parte da categoria #14 sem conta externa: o scheduler já
   marca "novo"; falta o disparo (e-mail próprio/desktop). Roadmap MELHORIAS §3.
2. **Recall do RAG (ajuste de k / cobertura)** — valor alto, esforço médio.
   Reduz "não encontrado" legítimo na categoria #7, que já é híbrida. MELHORIAS §3.
3. **RAG Fase 3 — declarações por template** — valor médio-alto (destaque),
   esforço médio. Primeiro passo seguro rumo à categoria #9 (geração de peças),
   ancorado nos requisitos já extraídos. MELHORIAS §3.
4. **Histórico de preços agregado por item/órgão** — valor médio, esforço
   médio. Evolui a categoria #10 de "por edital, sob demanda" para série
   acumulada consultável (sem TimescaleDB — agregação SQLite/numpy).
5. **OCR para PDFs escaneados** — valor médio, esforço alto. Amplia categorias
   #7/#8 a editais-imagem (fallback docling/Tesseract). MELHORIAS §3.
6. **CAPAG de estados / M7-eval do extrator** — portfólio e robustez; ver
   MELHORIAS §3.

> Fora desta lista por decisão (não por prioridade): scrapers de portais,
> enriquecimento Receita, ML preditivo, billing/multi-tenant, robô de lances e
> monitor de chat — ver "Decisões de arquitetura conscientes".
