# Handoff: Radar de Pregões — Front-end (telas + fluxos)

## Visão geral
**Radar de Pregões** é um SaaS de uso próprio para um fornecedor de equipamentos de
áudio/vídeo/AV que disputa pregões e licitações (Lei 14.133). O front-end aqui
documentado cobre o ciclo: **descobrir** pregões no PNCP → **analisar viabilidade**
(margem, lucro, veredito) cruzando os itens do edital com o catálogo de custos do
usuário → revisar o **checklist de habilitação** com citação verificada → conferir a
**prontidão fiscal/NF-e** por item.

O escopo de produto, regras de negócio, modelo de dados e contratos de API estão no
arquivo **`CLAUDE.md`** incluído neste pacote — ele é a fonte da verdade do backend.
Este README cobre **o front-end**: telas, componentes, estados, tokens e interações.

---

## Sobre os arquivos de design
Os arquivos em `prototipo/` são **referências de design feitas em HTML/React+Babel** —
um protótipo que mostra aparência e comportamento pretendidos, **não** código de
produção para copiar direto. A tarefa é **recriar estas telas no ambiente do
codebase-alvo** (o `CLAUDE.md` define **React + Vite + Framer Motion**) usando os
padrões já estabelecidos lá e ligando aos endpoints reais do FastAPI.

O protótipo roda com dados mock (`radar/data.js`) que espelham o modelo real
(`buscas_salvas`, `pregoes`, `itens_pregao`, `catalogo_produtos`, `habilitacao`,
`config`). Troque o mock pelas chamadas de API descritas no `CLAUDE.md` §7.

## Fidelidade
**Alta fidelidade (hifi).** Cores, tipografia, espaçamento, estados e animações são
finais. Recrie a UI fielmente. As únicas coisas "de mentira" são os dados (mock) e o
fato de o matching/extração já virem prontos — no real eles vêm do backend.

---

## Direção de arte — "Mesa de operação"
A metáfora visual é um **console de áudio/AV**: chassi de alumínio claro, módulos de
painel claros, uma *channel strip* escura na lateral, serigrafia em fonte mono, e um
**medidor de viabilidade** estilo VU-meter como elemento-assinatura. Evite cara de
"SaaS genérico": nada de gradientes roxos, cantos exageradamente arredondados ou Inter.

### Tipografia
| Uso | Fonte | Pesos | Observações |
|---|---|---|---|
| Display (títulos, vereditos, nomes) | **Big Shoulders Display** | 500–800 | sempre `text-transform: uppercase`, `letter-spacing: 0.02–0.06em` |
| Corpo / UI | **Archivo** | 400–700 | base 14px |
| Mono (serigrafia, números, dados) | **IBM Plex Mono** | 400–600 | `font-variant-numeric: tabular-nums` em toda métrica |

A classe utilitária `.silk` (mono, 10.5px, uppercase, `letter-spacing 0.12em`, cor
`--silk`) é a "etiqueta serigrafada" usada em todos os rótulos de campo.

### Paleta (tokens nomeados, em `radar/styles.css :root`)
| Token | Hex | Papel |
|---|---|---|
| `--aluminio` | `#E4E7E1` | chassi / fundo da aplicação (tweakável) |
| `--painel` | `#FAFBF8` | faces de painel / cards / módulos |
| `--tinta` | `#171C1A` | texto principal, sidebar, hero escuro |
| `--tinta-2` | `#3C443F` | texto secundário |
| `--silk` | `#69716C` | rótulos serigrafados, texto terciário |
| `--linha` | `#CDD2CA` | bordas / divisórias |
| `--sinal` | `#149357` | verde — margem saudável / "Vale" / verificado |
| `--pico` | `#C98A04` | âmbar — atenção / "Talvez" / pendente / sugerido |
| `--clip` | `#CC4537` | vermelho — prejuízo / "Não vale" / não tenho |

Cores "acesas" (LEDs sobre fundo escuro) usam variantes mais claras: sinal `#35C580`,
pico `#EFB02A`, clip `#E5604F`. Vereditos no hero escuro: vale `#3CCB87`,
talvez `#F0B428`, não `#F0685A`.

### Outros tokens
- Raio: cards/módulos `10px`, inputs/botões `6–8px`, pills `5–6px`, chips `4px`.
- Sombra de card em hover: `0 10px 26px -12px rgba(18,24,20,.35)`.
- Sidebar largura: `--sidebar-w: 236px`. Densidade de linha: `--row-pad` (13px conf. / 8px compacta).
- Aviso fixo de rodapé: barra escura `rgba(23,28,26,.96)`, sempre visível.

---

## Telas / Views

### 1. Encontrar pregões (`FindScreen`, `apenasSalvos=false`)
- **Propósito:** descobrir oportunidades do PNCP por palavra-chave e filtros, com
  **veredito prévio** antes de abrir a análise.
- **Layout:** título display + subtítulo; barra de filtros (flex, gap 10px); contador
  de resultados (`.silk`); lista de cartões (coluna, gap 12px).
- **Filtros:** busca textual (input mono com ícone lupa), select UF, select modalidade,
  toggle "Recebendo propostas" (LED), toggle "Só novos" (com badge de contagem). A
  busca filtra por tokens ≥3 chars sobre título+órgão+município+descrição+itens
  (normalizando acentos).
- **Cartão de pregão (`CartaoPregao`):** grid 2 colunas (`1fr auto`). Coluna esquerda:
  linha `.silk` (badge "novo" verde quando `pregao.novo` + modalidade · cidade/UF ·
  status), título display (21px), órgão, descrição (clamp 2 linhas), faixa de metadados
  mono (valor estimado, propostas até, nº de itens, cobertura X/Y). Coluna direita:
  **etiqueta de veredito** + opcional "sincronizar p/ habilitação" quando
  `!sincronizado`. Hover: `translateY(-2px)` + sombra. É um `<button>`.

### 2. Meus pregões (`FindScreen`, `apenasSalvos=true`)
- Mesma estrutura, sem campo de busca textual; lista só `pregao.salvo`. Subtítulo fala
  do monitoramento automático.

### 3. Buscas salvas (`BuscasScreen`)
- **Propósito:** CRUD/monitoramento das buscas que rodam 2×/dia (PNCP).
- **Cartão de busca (`.busca-card`):** nome display, status (LED Ativa/Pausada), chips
  de termos, metadados mono (UFs, status, última execução, badge "N novos"), e botão
  **"Rodar agora"** à direita. Clicar → estado "Rodando…" com spinner (~1.4s no mock; no
  real, `POST /buscas/{id}/rodar`).

### 4. Meu catálogo (`CatalogScreen`)
- **Propósito:** base de custos + dados fiscais. Tabela: Código (mono), Produto (+categoria),
  NCM (mono, "faltam dados" em cinza se nulo), Custo unit. (mono, BRL).
- No protótipo é read-only; no real expõe `GET/POST/PATCH /catalogo`.

### 5. Análise do pregão (`AnalysisScreen`) — tela central
Estrutura vertical:
1. **Cabeçalho:** botão "Voltar"; linha `.silk` (modalidade · amparo · situação); título
   display (34px); órgão · cidade/UF; unidade compradora (mono); linha de prazo
   ("Propostas: início → **fim** (horário de Brasília)"); **link "Ver no PNCP"** (com
   `numeroControle`, abre `https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}`);
   parágrafo de descrição do objeto.
2. **Hero (módulo escuro):** gradiente `#1D2320→--tinta`. Três blocos: "Lucro potencial
   estimado" (mono ~46px, tween animado), "Margem média" (mono ~32px), "Veredito"
   (palavra display gigante 44–64px, colorida por veredito). Abaixo, o **Medidor de
   Viabilidade**. Rodapé com a regra textual do veredito.
3. **Faixa de resumo (`.resumo`):** grid auto-fit de módulos: Valor total, Cobertura do
   catálogo (+sugeridos a confirmar), Habilitação (pendentes/total), Prontidão NF-e (X/Y).
4. **Abas (`role=tablist`):** "Itens & margem" (badge "N a casar" âmbar se houver
   sugeridos), "Habilitação" (badge pendentes/total), "Fiscal · NF-e" (badge X/Y).

#### Aba Itens & margem (`ItensTab`)
- Aviso âmbar quando há matches sugeridos ("N itens sugeridos aguardando confirmação…
  Só itens confirmados entram no cálculo").
- **Tabela** (grid 8 colunas: Nº, Descrição&match, Qtd, Valor unit. estimado, Seu custo
  unit., Margem %, Lucro do item, Status). Cada linha (`LinhaItem`):
  - Marca lateral por status (`inset 3px 0 0` na cor): âmbar=sugerido, cinza=sem match,
    vermelho=prejuízo.
  - Custo unit. é **input editável** (`CostInput`) quando há produto casado; recalcula
    margem/lucro/veredito ao vivo (com tween). Aceita formato pt-BR.
  - Margem mostra pill colorido; quando ainda não confirmado, pill cinza com tag "prévia".
  - Status: LED + texto (Saudável/Atenção/Prejuízo/Sugerido/Sem match/Sigiloso).
  - **Sigiloso:** quando `item.sigiloso` (orçamento sigiloso do PNCP), valor vira
    "sigiloso", sem custo/margem/lucro.
  - **Sub-barra de match (`MatchBar`)** aparece sob itens "sugerido" ou "sem match":
    - Sugerido: "Sugestão: <produto> · similaridade NN%" + botões **Confirmar / Trocar
      / Recusar**.
    - Sem match: "Nenhum produto casou automaticamente" + **Casar manualmente** (abre
      `SeletorProduto`, um select do catálogo).
- Linha **Total**: itens confirmados, margem agregada (pill), lucro potencial.
- Clicar numa linha (fora de input/botão/select) abre o **painel de detalhe**.

#### Aba Habilitação (`HabilitacaoTab`)
- Se `pregao.habilitacao == null` → **estado vazio**: "Habilitação ainda não extraída"
  + chips dos arquivos do edital (no real: dispara `POST /pregoes/{id}/sincronizar`).
- Caso contrário: aviso do **gate de citação** (quantas citações não puderam ser
  confirmadas); requisitos **agrupados por categoria** (Jurídica, Fiscal, Técnica,
  Econômico-financeira, Proposta, Outros).
- **Cartão de requisito (`RequisitoCard`):** borda esquerda colorida pelo status do
  usuário; nome + tag Obrigatório/Opcional; três botões de status **Tenho / Pendente /
  Não tenho** (`aria-pressed`); **citação** entre aspas (trecho literal do edital) com
  rodapé: selo **"Citação verificada no PDF"** (verde) ou **"Citação não verificada"**
  (vermelho) conforme `h.verificada`, e link "pág. N · ver no PNCP".
- No real: `GET /pregoes/{id}/habilitacao`, `PATCH /habilitacao/{id}`.

#### Aba Fiscal · NF-e (`FiscalTab`)
- **Selo agregado:** "X de N itens prontos" + barra de progresso; toggle de **regime
  tributário** Simples (CSOSN) / Presumido (CST); rótulo "UF origem → destino".
- **Tabela por item:** Nº, Item, **NCM** (chip + fonte "PNCP"/"catálogo", ou "faltam
  dados"), **CFOP** (chip "sugestão" — regra local: mesma UF→5102, diferente→6102),
  **CST/CSOSN** (chip "sugestão", conforme regime), **Prontidão** (LED Pronto/Incompleto).
  Itens sem produto casado mostram "Sem produto casado — confirme o match…".
- Disclaimer fixo: "Sugestões fiscais (NCM, CFOP, CST/CSOSN) são apoio, não orientação
  contábil. Confirme com seu contador antes de emitir a nota."

### 6. Painel de detalhe do item (`DetailPanel`)
- Drawer à direita (desktop) / bottom-sheet (mobile). Conteúdo (`PainelConteudo`):
  especificação completa do edital; condições do certame (grid); bloco de **match**
  (confirmar/recusar + custo editável + margem/lucro prévia); bloco de **prontidão
  NF-e** (NCM/CFOP/CST-CSOSN/unidade). Fecha com Esc, clique no overlay, botão X, ou
  **arrastar** (drag-to-close com threshold/momentum).

---

## Interações & comportamento
- **Recálculo ao vivo:** editar custo ou confirmar/recusar match recomputa margem por
  item, agregados, veredito e medidor — todos com tween suave. Lógica em
  `helpers.jsx → analisar(pregao, estado)` e `fiscalDoItem(item, pregao, config)`.
- **Veredito (regra, do CLAUDE.md §6.2):** *Vale* se margem média ≥20% **e** cobertura
  ≥60% **e** lucro ≥ R$1.000; *Não vale* se margem <8% **ou** lucro < R$300; senão
  *Talvez*. **Só itens com match confirmado entram na conta.** O veredito nunca esconde
  os números.
- **Medidor de Viabilidade (assinatura):** VU-meter de 32 LEDs (ou barra contínua via
  tweak), escala de margem −10→40% com zonas Não vale (<8) / Talvez (8–20) / Vale (≥20);
  sobe com spring de overshoot contido ao montar. É `role="meter"` com `aria-valuetext`.
- **Animações (Framer Motion):** entrada orquestrada por screen (stagger de
  cards/linhas, springs), parallax leve do cabeçalho ao rolar, drawer com spring + drag.
  Durações/easing nos componentes. **Respeita `prefers-reduced-motion`** (aparição
  instantânea; nada parte de `opacity:0` dependente de tick).
- **Estados de lista (Tweak "Estado das listas"):** *Carregando* (skeleton shimmer) /
  *Erro* (mensagem de rate-limit do PNCP + "Tentar de novo") / *Dados*. No real, derive
  de loading/error das chamadas.
- **Acessibilidade:** foco visível (outline 2px `--tinta`), navegação por teclado nas
  linhas (Enter/Espaço abre detalhe), Esc fecha o painel, `aria-pressed`/`aria-selected`
  nos toggles e abas, `role=table/row/cell` na tabela.

## Gerenciamento de estado (no protótipo, a portar)
- `tela`: `{ nome, pregaoId?, origem? }` — roteamento simples (use o router do codebase).
- `estadoPregoes[pregaoId] = { custos:{n:valor}, matches:{n:match|null}, habilitacao:{id:status} }`
  — edições do usuário sobre os dados do backend (não muta o original). Setters:
  `setCusto`, `setMatch`, `setHabil` (via `mutarEstado(campo, chave, valor)`).
- `config` fiscal `{ regime_tributario, uf_origem }` — toggle de regime recomputa CST/CSOSN.
- Tweaks (persistidos): `medidor`, `densidade`, `chassi`, `estado` (demo de loading/erro).

## Mapa telas → endpoints (CLAUDE.md §7)
| Tela / ação | Endpoint |
|---|---|
| Encontrar / Meus pregões | `GET /pregoes?novos=&uf=` |
| Buscas salvas / Rodar agora | `GET /buscas`, `POST /buscas`, `POST /buscas/{id}/rodar` |
| Abrir análise | `GET /pregoes/{id}`, `GET /pregoes/{id}/itens` |
| Sincronizar (itens+arquivos+habilitação) | `POST /pregoes/{id}/sincronizar` |
| Confirmar/recusar/trocar match | `POST /itens/{id}/match {produto_id\|null, confirmado}` |
| Habilitação | `GET /pregoes/{id}/habilitacao`, `PATCH /habilitacao/{id}` |
| Catálogo | `GET/POST/PATCH /catalogo` |
| Config fiscal | `GET/PATCH /config` |

## Assets
Sem imagens. Todos os ícones são SVG inline de traço (objeto `Ico` em `helpers.jsx` e
`Tabs.jsx`). Fontes via Google Fonts (Big Shoulders Display, Archivo, IBM Plex Mono).
Não há assets de marca de terceiros — se o codebase tiver design system próprio, mapeie
os tokens acima para os equivalentes dele.

## Arquivos (em `prototipo/`)
- `Radar de Pregões.html` — entrada; carrega React 18 + Babel + Framer Motion e os scripts abaixo.
- `radar/styles.css` — todos os tokens e estilos (≈1300 linhas, comentado por seção).
- `radar/data.js` — dados mock espelhando o modelo real (substituir por API).
- `radar/helpers.jsx` — cálculo (`analisar`, `fiscalDoItem`, `linkPncp`), formatação
  pt-BR, medidor, números com tween, ícones, contexto de motion.
- `radar/FindScreen.jsx` — Encontrar/Meus pregões, Buscas salvas, Catálogo, estados.
- `radar/AnalysisScreen.jsx` — análise, abas, tabela de itens, matching, custo editável.
- `radar/Tabs.jsx` — abas Habilitação e Fiscal/NF-e.
- `radar/DetailPanel.jsx` — painel/bottom-sheet de detalhe do item.
- `radar/App.jsx` — shell, sidebar, navegação, estado, aviso fixo, Tweaks.
- `radar/tweaks-panel.jsx` — painel de Tweaks (somente protótipo; não portar).
- `../CLAUDE.md` — **fonte da verdade** do produto, regras, modelo de dados e APIs.
