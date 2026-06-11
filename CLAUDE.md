# CLAUDE.md — Radar de Pregões (sistema REAL, dados reais)

Documento-norte para o agente de código (Claude Code). Leia tudo antes de
escrever qualquer linha. Em conflito entre este arquivo e um pedido pontual,
pergunte antes.

## 1. O que é
SaaS de uso próprio (usuário nº 1 = o dono) para **fornecedor que disputa
pregões/licitações** (Lei 14.133) vendendo equipamento de áudio/vídeo/AV.
O sistema: (a) **descobre** pregões no PNCP por palavras-chave salvas;
(b) **lê os itens** e cruza com o catálogo do fornecedor (custo + dados
fiscais) para calcular **margem, lucro potencial e veredito** (Vale / Talvez /
Não vale); (c) **baixa o PDF do edital** e extrai o **checklist de documentos
de habilitação** com citação verificada; (d) marca a **prontidão NF-e** por
item (NCM/CFOP/CST-CSOSN como sugestão).

Não é consultoria jurídica nem contábil. Não dá lances. Não emite NF-e.

## 2. Princípios INEGOCIÁVEIS
1. **Nunca inventar.** Toda informação extraída do PDF do edital sai com
   citação do trecho original (página + excerto). Se não achou, o campo é
   `nao_encontrado` — nunca um chute.
2. **Gate de citação:** após a extração via LLM, um verificador confere se o
   excerto citado existe de fato no texto extraído do PDF (busca por
   normalização: caixa baixa, espaços colapsados). Citações que falham viram
   `verificada=false` e a UI mostra "não verificada".
3. **Fonte oficial é o PNCP.** Valores, prazos e itens vêm da API; o sistema
   nunca "corrige" dado oficial. Link para a página do PNCP sempre visível:
   `https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}`.
4. **Custo é dado do usuário.** Margem/lucro só são calculados para itens
   casados com o catálogo; item sem match fica fora da conta, visível e cinza.
5. **Fiscal é sugestão.** NCM/CFOP/CST-CSOSN aparecem sempre com a etiqueta
   "sugestão — confirme com contador". Nada é apresentado como definitivo.
6. **Gentileza com API pública:** máx. 1 req/s ao PNCP, backoff exponencial em
   erro, cache local de respostas, User-Agent identificável
   (`RadarPregoes/0.1 (uso pessoal)`).

## 3. Stack
- **Backend:** Python 3.11+, FastAPI, SQLite (arquivo `data/radar.db`),
  httpx (com retry/backoff), APScheduler (monitoramento agendado).
- **Extração de PDF:** pymupdf4llm (texto nativo) com fallback docling/OCR
  quando a densidade de texto por página for baixa (mesmo padrão do projeto
  Auditor — reaproveite o módulo de ingestão se possível).
- **Extração estruturada via LLM:** Anthropic API (Claude Sonnet) + `instructor`
  para saída Pydantic validada. A chave vem de `ANTHROPIC_API_KEY` no `.env`
  (runtime do app ≠ assinatura do agente de código).
- **Matching de itens ↔ catálogo:** embeddings locais
  `intfloat/multilingual-e5-small` + similaridade de cosseno; threshold 0.83
  para sugerir match; matches são SEMPRE confirmados pelo usuário na UI antes
  de entrar na conta (human-in-the-loop).
- **Frontend:** React + Vite + Framer Motion. A UI premium já existe como mock
  (gerado no Claude Design) — portar os componentes e ligar nos endpoints.
- **Testes:** pytest; cada milestone fecha com testes verdes.

## 4. APIs do PNCP (VERIFICADAS — usar exatamente assim)
Todas públicas, sem autenticação. Charset UTF-8.

### 4.1 Busca de pregões
```
GET https://pncp.gov.br/api/search/
  ?q={palavras}                  # busca textual
  &tipos_documento=edital
  &status=recebendo_proposta     # ou omitir para todos
  &ufs=SP                        # opcional, aceita lista "SP,RJ"
  &ordenacao=-data
  &pagina=1&tamanhoPagina=50     # máx ~50/página
```
Resposta: `{"items": [...], "total": N}`. Campos por item (reais):
`title, description, orgao_cnpj, orgao_nome, ano, numero_sequencial,
numero_controle_pncp, municipio_nome, uf, modalidade_licitacao_nome,
situacao_nome, data_publicacao_pncp, data_inicio_vigencia,
data_fim_vigencia, valor_global, item_url`.
**Importante:** o detalhe de metadados vem DESTA resposta — persista o JSON do
hit. (O endpoint de detalhe da compra não responde publicamente; não dependa
dele.) Identidade do pregão = `(orgao_cnpj, ano, numero_sequencial)`.

Params adicionais VERIFICADOS empiricamente (11/06/2026):
modalidades=<ids csv> (1 Leilão-Eletr · 2 Diálogo Comp. · 3 Concurso · 4 Concorrência-Eletr · 5 Concorrência-Pres · 6 Pregão-Eletr · 7 Pregão-Pres · 8 Dispensa · 9 Inexigibilidade · 10 Manif. Interesse · 11 Pré-qualificação · 12 Credenciamento · 13 Leilão-Pres)
esferas=<F|E|M|D csv> · ordenacao=-data|data|relevancia
status: só recebendo_proposta|encerradas filtram; todos = sem filtro; OMITIR dá 400
tamanhoPagina: máx. efetivo 10 na busca. municipios/orgaos: formato desconhecido, não usar.

### 4.2 Itens do pregão
```
GET https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens
  ?pagina=1&tamanhoPagina=100
```
Resposta: lista. Campos por item (reais): `numeroItem, descricao,
materialOuServicoNome, quantidade, unidadeMedida, valorUnitarioEstimado,
valorTotal, criterioJulgamentoNome, tipoBeneficioNome ("Participação exclusiva
para ME/EPP"), situacaoCompraItemNome, ncmNbsCodigo, ncmNbsDescricao,
catalogo, catalogoCodigoItem, informacaoComplementar, orcamentoSigiloso`.
**Atenção:** `ncmNbsCodigo` frequentemente vem `null` (órgão não preencheu) —
quando vier, use; quando não, o NCM entra pelo catálogo do usuário.
`orcamentoSigiloso=true` → valores podem vir nulos; exibir como "sigiloso".

### 4.3 Arquivos do pregão (edital, termo de referência, anexos)
```
GET https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos
  ?pagina=1&tamanhoPagina=20
```
Resposta: lista com `titulo, tipoDocumentoNome ("Edital"), url`.
A `url` retorna o binário direto (HTTP 200, `content-disposition` com o nome
`*.pdf`). Baixar para `data/arquivos/{cnpj}_{ano}_{seq}/`, respeitando o nome
do `content-disposition`. Tamanhos típicos: centenas de KB a alguns MB.

## 5. Modelo de dados (SQLite)
```
buscas_salvas(id, nome, termos, ufs, status, ativo, criado_em)
pregoes(id, cnpj, ano, seq, numero_controle, titulo, descricao, orgao,
        municipio, uf, modalidade, situacao, data_fim_vigencia,
        valor_global, json_busca, link_pncp, descoberto_em,
        veredito, lucro_potencial, margem_media)          -- calculados
itens_pregao(id, pregao_id, numero, descricao, qtd, unidade,
             valor_unit_estimado, valor_total, beneficio, criterio,
             ncm_pncp, info_complementar, sigiloso,
             produto_id NULL, match_score NULL, match_confirmado BOOL)
catalogo_produtos(id, nome, custo_unit, ncm, unidade, origem,
                  cst_csosn, aliq_icms, aliq_ipi, ativo)
arquivos(id, pregao_id, titulo, tipo, url, caminho_local, baixado_em)
habilitacao(id, pregao_id, requisito, categoria, pagina, excerto,
            verificada BOOL, status_usuario)  -- ok|pendente|nao_tenho
config(chave, valor)  -- regime_tributario: simples|presumido, uf_origem
```

## 6. Funcionalidades e regras de negócio
### 6.1 Descoberta (buscas salvas)
- CRUD de buscas salvas (ex.: termos="áudio, microfone, caixa de som",
  ufs="SP", status=recebendo_proposta).
- Rotina agendada (APScheduler, 2×/dia) roda cada busca ativa, deduplica por
  `numero_controle_pncp` e insere novos pregões com flag "novo".
- Endpoint manual `POST /buscas/{id}/rodar` para rodar na hora.

### 6.2 Itens, matching e veredito
- Ao abrir um pregão pela primeira vez: buscar itens (4.2) e persistir.
- Matching: embedar `descricao` do item e `nome` dos produtos do catálogo
  (prefixos "query:"/"passage:" do e5); sugerir o melhor match se score ≥0.83;
  o usuário confirma/recusa/troca na UI. Só match confirmado entra na conta.
- Cálculo por item confirmado:
  `margem_% = (valor_unit_estimado - custo_unit) / valor_unit_estimado`
  `lucro_item = (valor_unit_estimado - custo_unit) * qtd`
- Agregados do pregão: lucro_potencial = Σ lucro_item; margem_media ponderada
  pelo valor; cobertura = itens confirmados / total.
- **Veredito (regra simples, configurável em `config`):**
  - "Vale": margem_media ≥ 20% E cobertura ≥ 60% E lucro_potencial ≥ R$ 1.000
  - "Não vale": margem_media < 8% OU lucro_potencial < R$ 300
  - senão "Talvez".
  Mostrar sempre os números junto do veredito; o veredito nunca esconde a conta.

### 6.3 Documentos de habilitação (o extrator — coração com LLM)
- Baixar arquivos (4.3). Extrair texto com pymupdf4llm; se texto/página < 200
  chars em média → fallback OCR (docling).
- Prompt de extração (via instructor) retorna `list[RequisitoHabilitacao]`:
  ```python
  class RequisitoHabilitacao(BaseModel):
      requisito: str            # ex.: "Certidão negativa de débitos federais"
      categoria: Literal["juridica","fiscal","tecnica",
                         "economico_financeira","proposta","outros"]
      obrigatorio: bool
      pagina: int
      excerto: str              # trecho LITERAL do edital que exige
  ```
  Regras do prompt: somente o que está no texto; excerto literal copiado;
  se não houver seção de habilitação, retornar lista vazia (permitido).
- Rodar o **gate de citação** (princípio 2) sobre cada excerto.
- UI: checklist com status do usuário (tenho / pendente / não tenho) e link
  para a página citada.

### 6.4 Fiscal / prontidão NF-e
- NCM do item = `ncm_pncp` se existir; senão o NCM do produto casado do
  catálogo; senão vazio (chip "faltam dados").
- CFOP sugerido por regra local (sem API): mesma UF de `config.uf_origem` →
  5102; UF diferente → 6102. Exibir como sugestão.
- CST/CSOSN conforme `config.regime_tributario` (simples → CSOSN do produto;
  presumido → CST do produto).
- "Pronto para NF-e" = NCM + unidade + CST/CSOSN preenchidos. Selo agregado:
  "X de Y itens cobertos prontos".

### 6.5 Fora de escopo v1 (NÃO construir agora)
Robô de lances; multiusuário/billing; emissão real de NF-e; monitorar diários
oficiais; integração com Compras.gov; scraping de páginas (só APIs acima).

## 7. API do backend (FastAPI)
```
GET  /buscas | POST /buscas | POST /buscas/{id}/rodar
GET  /pregoes?novos=true&uf=SP | GET /pregoes/{id}
POST /pregoes/{id}/sincronizar        # itens + arquivos + habilitacao
GET  /pregoes/{id}/itens
POST /itens/{id}/match {produto_id|null, confirmado}
GET  /pregoes/{id}/habilitacao
PATCH /habilitacao/{id} {status_usuario}
GET  /catalogo | POST /catalogo | PATCH /catalogo/{id}
GET  /config | PATCH /config
```
Respostas sempre com os números crus + campos calculados; nada de esconder a
conta atrás do veredito.

## 8. Milestones (fechar um por vez; testes verdes antes do próximo)
- **M0 — Setup:** estrutura de pastas, FastAPI hello, SQLite + migrações
  simples, `.env.example`, cliente PNCP com rate-limit/backoff/cache + testes
  com respostas gravadas (fixtures JSON reais deste documento).
- **M1 — Descoberta:** buscas salvas, rodar busca, dedup, persistir pregões,
  listar com filtro "novos". Teste: mesma busca 2× não duplica.
- **M2 — Itens + catálogo + veredito:** sincronizar itens, CRUD catálogo,
  matching e5 com confirmação, cálculo margem/lucro/veredito. Teste: conta
  bate com planilha de referência; item sem match não entra na soma.
- **M3 — Arquivos + habilitação:** download dos PDFs, extração, extrator LLM
  com instructor, gate de citação, checklist persistido. Teste: gate derruba
  excerto adulterado; lista vazia é aceita.
- **M4 — Fiscal:** NCM (PNCP→catálogo→vazio), CFOP por regra, CST/CSOSN por
  regime, selo de prontidão. Teste: trocar regime alterna CSOSN↔CST.
- **M5 — Front React:** portar o mock premium do Claude Design e ligar nos
  endpoints; estados de carregando/vazio/erro; reduced-motion respeitado.
- **M6 — Monitoramento:** APScheduler 2×/dia, flag "novo", resumo no dashboard.
- **M7 (opcional, portfólio) — Eval:** ragas/faithfulness no extrator de
  habilitação sobre 3 editais reais baixados.

## 9. Avisos fixos na UI (copiar literalmente)
- "Ferramenta de apoio à decisão. O edital oficial e os valores estão no PNCP.
  Confira antes de dar lance."
- "Sugestões fiscais (NCM, CFOP, CST/CSOSN) são apoio, não orientação
  contábil. Confirme com seu contador antes de emitir a nota."

## 10. Dados reais para fixtures/testes
Use o pregão verificado: cnpj `01613770000172`, ano `2026`, seq `67`
(Município de Imbaú/PR — itens e arquivo confirmados nos endpoints acima) e
um pregão de AV encontrado pela busca `q=áudio&ufs=SP` no dia do setup.
Grave as respostas JSON em `tests/fixtures/` na primeira execução e teste
contra elas (não bater na API a cada teste).
