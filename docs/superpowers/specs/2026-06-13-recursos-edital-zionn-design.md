# Recursos de detalhe do edital (estilo Zionn) — spec aprovada

Data: 2026-06-13 · Status: aprovada pelo dono ("tudo se faz necessário, pode adicionar")
Escopo: 4 recursos no detalhe do pregão (AnalysisScreen), todos com dados REAIS
e fonte oficial (princípio nº 1 — nunca inventar). Backend Python/FastAPI +
React. Não toca landing nem o re-skin.

## Recurso 1 — CAPAG (risco de pagamento do comprador)

**Por quê:** saber se o ente comprador é fiscalmente saudável ("vai me pagar?")
entra na decisão junto com margem/veredito. Diferencial do Zionn.

**Fonte oficial (verificada 13/06/2026):**
- Nota/indicadores CAPAG: XLSX anual do Tesouro Transparente (CKAN). NÃO há
  API JSON. Datasets: `capag-municipios` e `capag-estados`. Resolver o XLSX
  mais recente via CKAN API: `GET https://www.tesourotransparente.gov.br/ckan/
  api/3/action/package_show?id=capag-municipios` → pegar o `resource.url` mais
  novo. Aba `Prévia da CAPAG`, colunas: `Código Município Completo` (cod_ibge
  7díg), `Nome_Município`, `UF`, `CAPAG` (nota A/B/C/D), `Indicador 1`+`Nota 1`,
  `Indicador 2`+`Nota 2`, `Indicador 3`+`Nota 3`, `ICF` (ranking, ex. "Bicf"),
  `Origem da Nota Final`.
- Casamento CNPJ→IBGE: `GET https://apidatalake.tesouro.gov.br/ords/siconfi/
  tt/entes` (JSON, público, ~5.570 entes, 5000/pág; baixar tudo e cachear).
  Campos: `cod_ibge, cnpj, ente, uf, esfera` (M/E; federais NÃO aparecem).
- **Federais não têm CAPAG** (oficial): autarquias federais (IFs, universidades),
  ministérios, União → exibir "Federal — pagamento pela União (risco baixo)".

**Arquitetura:**
- Migração v6: tabelas `capag_entes(cnpj PK, cod_ibge, ente, uf, esfera)` e
  `capag_notas(cod_ibge PK, municipio, uf, nota, ind1, nota1, ind2, nota2,
  ind3, nota3, icf, origem, esfera)`. (Estados entram em capag_notas com
  cod_ibge da UF e esfera 'E'.)
- Seed `scripts/seed_capag.py`: resolve XLSX mais recente (CKAN), baixa
  municípios + estados + /entes, parseia (openpyxl), popula as tabelas.
  User-Agent `RadarPregoes/0.1 (uso pessoal)`, 1 req/s. Idempotente (REPLACE).
  Rodar manual/mensal (não no request).
- Serviço `services/capag.py`: `capag_do_pregao(con, cnpj, uf, municipio) ->
  dict`. Pipeline: cnpj→capag_entes→cod_ibge→capag_notas. Federal/sem match →
  `{disponivel: False, motivo: "federal"|"sem_dados", ...}`. Nunca inventa nota.
- Endpoint `GET /pregoes/{id}/capag` → `{disponivel, nota, icf, origem,
  indicadores:[{rotulo,nota,valor_pct}], ente, uf, esfera, federal, motivo,
  fonte:"Tesouro Nacional / SICONFI"}`. Lazy (só quando a aba abre).
- Dep nova: `openpyxl` (parse XLSX; usada no seed e no export XLSX do recurso 2).

**UI (AnalysisScreen):** card/aba "CAPAG" com nota grande (cor por faixa:
A=sinal, B=pico, C/D=clip), 3 indicadores (rótulo, nota, %), ranking ICF, e
o selo de fonte "Tesouro Nacional · ano-base". Federal → bloco honesto
"Pagamento pela União — risco baixo; CAPAG só avalia municípios/estados".
Sem dados → "CAPAG não disponível para este ente" (cinza, nunca um chute).

## Recurso 2 — Exportar itens (CSV / XLSX)

**Por quê:** virar a lista de itens do edital em planilha pra montar a cotação.

**Arquitetura:** `GET /pregoes/{id}/itens/export?formato=csv|xlsx` → StreamingResponse
com `content-disposition` (`itens_{cnpj}_{ano}_{seq}.csv/.xlsx`). Colunas:
número, descrição, qtd, unidade, valor_unit_estimado, valor_total, material/serviço,
benefício, critério, NCM, custo_efetivo, preço_esperado, margem%, lucro
(os calculados saem do mesmo `_itens_calculados` que a tabela já usa — a
planilha leva a SUA conta junto, não só o cru do PNCP). CSV sem dependência
(módulo `csv`); XLSX via openpyxl.

**UI:** botão "Exportar itens" no topo da tabela de itens com menu CSV/XLSX.

## Recurso 3 — Gerar Relatório PDF

**Por quê:** guardar/compartilhar/levar pra reunião um resumo do edital.

**Arquitetura:** `GET /pregoes/{id}/relatorio.pdf` → PDF gerado no backend
(dep `fpdf2`, leve, pura). Conteúdo: cabeçalho (edital nº, órgão, município/UF,
modalidade, situação, datas, valor total, link PNCP), DESCRIÇÃO, o VEREDITO +
números (lucro potencial, margem média, cobertura — a nossa análise, que o
Zionn não tem), CAPAG (se houver), tabela de itens (com custo/margem quando
houver), e os 2 avisos fixos do §9 do CLAUDE.md no rodapé. Marca "Radar de
Pregões — dados do PNCP". StreamingResponse, `content-disposition`.

**UI:** botão "Gerar relatório" no cabeçalho da AnalysisScreen (ao lado de
voltar), baixa o PDF.

## Recurso 4 — Histórico + busca nos itens

**Histórico (PNCP, verificado 13/06/2026):**
`GET https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/historico`
→ array com `logManutencaoDataInclusao, tipoLogManutencaoNome ("Inclusão"),
categoriaLogManutencaoNome ("Contratação"/"Documento"/"Item"...), usuarioNome,
justificativa, documentoTitulo`. **Ruído:** este endpoint repete um evento de
"Sincronizacao automatica (scheduler 5min)" a cada 5 min (um pregão tinha 2166
eventos!). Filtrar: descartar entradas cuja `justificativa` contenha
"sincroniza" (normalizado) E que sejam recorrência do mesmo (tipo,categoria);
manter os marcos (inclusões, alterações com justificativa real, retificações,
documentos). Cap defensivo de ~50 eventos exibidos.
- Cliente: `pncp.historico(cnpj, ano, seq)` (pista interativa, cache 6h).
- Endpoint: `GET /pregoes/{id}/historico` → eventos filtrados
  `[{data, evento, categoria, responsavel, justificativa, documento}]`.

**UI:** aba "Histórico" na AnalysisScreen — timeline (data, evento, responsável,
justificativa). Vazio → "Sem eventos relevantes".

**Busca nos itens (frontend-only):** campo "Buscar item" acima da tabela de
itens que filtra por descrição (normalizada). Útil em editais grandes. Zero
backend.

## Não-escopo
Multi-seleção de itens para exportar parcial (exporta todos); detalhe-modal por
item (a tabela já expande/casa); CAPAG em tempo real no card da lista ao vivo
(só no detalhe pós-abertura); recálculo da nota CAPAG (o XLSX já traz pronta).

## Aceite
1. `seed_capag.py` roda e popula as tabelas; `GET /pregoes/{id}/capag` de um
   pregão municipal de São Paulo retorna nota B / A 32,75% / B 93,78% / B 4,86%
   / "Bicf" (bate com o Zionn); um pregão federal retorna `federal=true`.
2. Export CSV e XLSX baixam com as colunas certas; PDF abre com veredito+itens.
3. Histórico filtra o ruído de sync (2166 → punhado); busca em itens filtra.
4. `npm run build` verde; pytest verde (com fixtures pequenas de CAPAG/histórico,
   sem baixar 22MB no teste); screenshots no preview; reviewer aprova.
