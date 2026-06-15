# Radar de Pregões

![CI](https://github.com/rafutzbatera-ctrl/radar-pregoes/actions/workflows/ci.yml/badge.svg)

SaaS pessoal para um fornecedor de áudio/vídeo/AV disputar licitações da Lei
14.133 — descobre pregões com **dados reais do PNCP**, calcula margem/lucro no
preço esperado de disputa e extrai o checklist de habilitação **com citação
verificada**. Nunca inventa: toda informação sai com fonte ou vira "não
disponível".

> Ferramenta de apoio à decisão. O edital oficial e os valores estão no PNCP.
> Confira antes de dar lance.

---

## O que faz

- **Descoberta no PNCP** — buscas salvas por palavra-chave + filtros (UF,
  modalidade, esfera, status), rodadas manualmente ou pelo agendador 2×/dia.
  Fonte oficial: a API pública do PNCP (busca textual e consulta em massa).
- **Análise de viabilidade** — cruza os itens do edital com o catálogo de
  custos do usuário e calcula **margem, lucro e veredito** (Vale / Talvez / Não
  vale) sobre o **preço esperado de disputa**, não sobre o teto. O edital é teto
  (leilão reverso, menor preço vence); a conta abre no cenário realista de
  −20% (deságio configurável), com o teto oficial sempre visível ao lado.
- **CAPAG / risco de pagamento** — classifica a capacidade de pagamento do
  comprador (Tesouro Nacional / SICONFI). É **esfera-aware**: avalia só
  municípios e estados; órgão federal não recebe nota chutada. A localização
  nunca determina a nota — a esfera do órgão manda (ver Diferencial).
- **Habilitação com citação verificada** — baixa o PDF do edital, extrai o
  checklist de documentos (jurídica, fiscal, técnica, econômico-financeira,
  proposta) e, para cada requisito, mostra o **trecho literal** do edital. Um
  gate de citação confere se o excerto existe de fato no PDF; o que não confere
  aparece como "não verificada".
- **Perguntar ao edital (RAG)** — pergunta em linguagem natural sobre o edital
  indexado. Resposta **extrativa** (trechos citados com página) e, opcional,
  uma **síntese em prosa** gerada localmente — sempre presa às citações.
- **Fiscal / prontidão NF-e** — NCM (PNCP → catálogo → vazio), CFOP por regra,
  CST/CSOSN por regime tributário, com selo de prontidão por item. Tudo
  rotulado como sugestão, nunca como orientação contábil.
- **Resultados / inteligência de mercado** — em pregão já homologado, mostra o
  **vencedor por item** (CNPJ, porte) e o **deságio real praticado** vindo do
  PNCP — referência concreta para calibrar o deságio esperado. Edital ainda
  aberto → "sem resultado publicado", nunca um chute.
- **Minhas certidões** — cadastro das certidões do fornecedor com **aviso de
  vencimento** (vencida / vencendo em ≤30 dias / ok) e badge no menu, para não
  perder o prazo de uma habilitação por documento vencido.

## Diferencial — honestidade

A regra nº 1 do produto é **nunca inventar**, e o código foi construído em volta
disso:

- **Toda informação tem fonte.** Valores, prazos e itens vêm da API do PNCP; o
  sistema nunca "corrige" dado oficial e mantém o link para a página do edital.
- **Citação verificável.** Cada requisito de habilitação carrega o excerto
  literal do edital; um verificador (normalização de caixa/espaços) confirma que
  o trecho existe no PDF. Falhou? Marca "não verificada" em vez de afirmar.
- **"Não disponível" em vez de chute.** Item sem custo fica fora da conta,
  visível e cinza. Pergunta sem trecho relevante responde "não encontrado".
  Embedding/modelo trocado sem reindexar responde "reindexar", não um número
  errado.
- **Honestidade onde o concorrente erra.** Um produto anterior atribuía a nota
  de risco do **município** a qualquer órgão sediado na cidade — um instituto
  federal em São Paulo herdava a CAPAG da prefeitura de São Paulo. Aqui a nota
  é **por esfera**: federal não recebe nota, só município/estado são avaliados,
  e a localização nunca decide.

## Stack e arquitetura

**Backend:** Python 3.11+ · FastAPI · SQLite (`data/radar.db`) · httpx (retry +
backoff, rate-limit gentil com a API pública) · APScheduler (monitoramento 2×/dia).
**Frontend:** React + Vite + Framer Motion.
**Testes:** pytest — **312 testes**, verdes, rodando no CI a cada push.

Destaques:

- **e5 local reusado** — o mesmo modelo `intfloat/multilingual-e5-small` faz o
  matching item↔catálogo (similaridade de cosseno, human-in-the-loop) **e** o
  retrieval do RAG. Um modelo, dois usos.
- **Só SQLite + numpy** — sem banco vetorial nem serviço externo no caminho de
  dados. Vetores são BLOB float32; a busca é um `matriz @ q` em numpy. Local-first.
- **Síntese sem custo de API** — a prosa opcional do RAG é gerada pelo Claude
  Code CLI local (`claude_cli`), desarmado (sem ferramentas) e com gate de
  citação duro. A extração de habilitação roda por padrão **100% local** por
  regras (heurístico), sem chave de API.
- **Landing 3D** — apresentação com Three.js + GSAP, carregada via lazy/Suspense
  (não pesa no bundle do app). Tema claro/escuro.

A direção de arte ("mesa de operação" — console de áudio com medidor de
viabilidade estilo VU-meter) e os tokens de design vivem no protótipo de
referência em [`prototipo/`](prototipo/); a especificação completa do produto
(regras de negócio, modelo de dados e contratos das APIs do PNCP) está em
[`CLAUDE.md`](CLAUDE.md).

## Como rodar

Atalho: dois cliques em **`iniciar.bat`** (abre backend + frontend + navegador).
Passo a passo, pré-requisitos e fluxo de uso em **[`COMO_RODAR.md`](COMO_RODAR.md)**.

```powershell
# backend (porta 8000)
cd backend
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000 --reload

# frontend (porta 5173) — abra http://localhost:5173/radar
cd frontend
npm run dev
```

A chave da Anthropic é **opcional** — o extrator de habilitação roda local por
padrão. Detalhes da configuração (`.env`, seed de catálogo) em `COMO_RODAR.md`.

### Docker (preview local / portfólio)

Há um `docker-compose.yml` que sobe a API (FastAPI) e a UI (build do Vite servido
por nginx, com proxy `/api` same-origin) em dois containers. É **preparo** para
preview/portfólio — não é um deploy publicado.

```bash
docker compose up --build      # UI em http://localhost:8080
docker compose down            # para; os volumes preservam os dados
```

- O backend **não** publica porta no host (só rede interna), então roda sem
  conflitar com o `iniciar.bat` de desenvolvimento (que ocupa a 8000).
- 1º `up`: baixa o modelo e5 (~470 MB) num volume nomeado; demora.
- `ANTHROPIC_API_KEY` é opcional (só a síntese RAG usa); o resto funciona sem ela.

## Testes

```powershell
cd backend
.\.venv\Scripts\python -m pytest -q   # 312 testes
```

O mesmo comando roda no GitHub Actions (Python 3.12, ubuntu) a cada push e PR no
`main`.

## Capturas

> Placeholder — prints da landing 3D, da análise do pregão (hero + medidor de
> viabilidade), do checklist de habilitação com citação verificada e da aba
> "Perguntar ao edital" podem ser adicionados aqui. (Sem imagens no repo por
> enquanto.)

## Avisos

- Ferramenta de apoio à decisão. O edital oficial e os valores estão no PNCP.
  Confira antes de dar lance.
- Sugestões fiscais (NCM, CFOP, CST/CSOSN) são apoio, não orientação contábil.
  Confirme com seu contador antes de emitir a nota.

## Escopo

Não é consultoria jurídica nem contábil, não dá lances e não emite NF-e. Uso
próprio, single-user, local-first. Roadmap e melhorias em
[`docs/MELHORIAS.md`](docs/MELHORIAS.md).
