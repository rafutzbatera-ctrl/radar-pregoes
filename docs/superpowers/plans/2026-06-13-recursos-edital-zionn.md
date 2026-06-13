# Recursos de detalhe do edital (Zionn) — Implementation Plan

> **For agentic workers:** execução via subagentes Opus (MODO MAX). Verificação por build + pytest + preview DevTools. NÃO matar processos 8000/5173; não tocar landing/.

**Goal:** Adicionar 4 recursos ao detalhe do pregão: CAPAG, exportar itens, relatório PDF, histórico+busca — todos com dados reais/fonte oficial.

**Spec:** `docs/superpowers/specs/2026-06-13-recursos-edital-zionn-design.md` (fontes verificadas, shapes, caveats).

**Execução SEQUENCIAL** (Stream A e B compartilham pregoes.py/AnalysisScreen.jsx/api.js/requirements.txt → paralelo causaria conflito).

---

### Stream A — CAPAG (a peça mais pesada, verificar ao vivo antes de seguir)

**Files:** `backend/app/db.py` (migração v6), `backend/scripts/seed_capag.py` (novo),
`backend/app/services/capag.py` (novo), `backend/app/routers/pregoes.py` (+/capag),
`backend/requirements.txt` (+openpyxl), `backend/tests/test_capag.py` (novo),
`backend/tests/fixtures/capag_amostra.*` (fixture pequena), `frontend/src/AnalysisScreen.jsx`,
`frontend/src/api.js`.

- Migração v6: `capag_entes(cnpj PK, cod_ibge, ente, uf, esfera)`,
  `capag_notas(cod_ibge PK, municipio, uf, nota, ind1, nota1, ind2, nota2, ind3,
  nota3, icf, origem, esfera)`.
- `seed_capag.py`: CKAN `package_show` → XLSX mais novo (municípios + estados);
  baixa `/entes`; parseia (openpyxl, aba "Prévia da CAPAG"); popula tabelas
  (INSERT OR REPLACE). UA `RadarPregoes/0.1`, 1 req/s. Tolerante a coluna
  ausente. `--help`/log de progresso.
- `services/capag.py`: `capag_do_pregao(con, cnpj, uf, municipio)`. cnpj→entes→
  cod_ibge→notas. esfera federal ou sem match → `{disponivel:False,
  motivo:"federal"|"sem_dados"}`. Mapear ind. para % (valor×100, 2 casas) +
  faixa de cor por nota. Nunca inventa.
- `GET /pregoes/{id}/capag` (lazy).
- Frontend: aba/card CAPAG (nota grande colorida, 3 indicadores, ICF, fonte;
  federal honesto; sem-dados cinza). api.js `capag(id)`.
- **Testes**: usar fixture pequena (montar capag_entes/notas direto no `con`),
  asserir: São Paulo→B/A/B/B/Bicf; federal→disponivel False motivo federal;
  desconhecido→sem_dados. NÃO baixar 22MB no teste.
- Verde: `pytest tests/test_capag.py`, `npm run build`.
- Commit: `Recurso CAPAG: risco de pagamento do comprador (Tesouro/SICONFI)`.
- **GATE**: o orquestrador roda `seed_capag.py` de verdade e valida ao vivo
  (São Paulo = B) ANTES do Stream B.

### Stream B — Export + PDF + Histórico + Busca

**Files:** `backend/app/pncp.py` (+historico), `backend/app/routers/pregoes.py`
(+/itens/export, /relatorio.pdf, /historico), `backend/requirements.txt` (+fpdf2),
`backend/app/services/relatorio.py` (novo, monta o PDF), `backend/tests/*`,
`frontend/src/AnalysisScreen.jsx`, `frontend/src/api.js`.

- `pncp.historico(cnpj, ano, seq)`: GET .../historico, pista interativa, cache 6h.
- Filtro de ruído (`services` ou no router): descartar `justificativa` com
  "sincroniza" (normalizado) recorrente; manter marcos; cap 50.
- `GET /pregoes/{id}/historico` → eventos `[{data,evento,categoria,responsavel,
  justificativa,documento}]`.
- `GET /pregoes/{id}/itens/export?formato=csv|xlsx` → StreamingResponse +
  content-disposition; colunas crus + calculados (reusar a análise dos itens).
- `services/relatorio.py` + `GET /pregoes/{id}/relatorio.pdf` (fpdf2): cabeçalho,
  descrição, veredito+números, CAPAG, tabela de itens, 2 avisos §9.
- Frontend: aba "Histórico" (timeline), botão "Exportar itens" (CSV/XLSX) na
  tabela, botão "Gerar relatório" no cabeçalho, campo "Buscar item".
- **Testes**: histórico filtra ruído (fixture com sync + marcos → só marcos);
  export CSV tem cabeçalho+linhas; pdf retorna 200 `application/pdf`.
- Verde: pytest, npm run build.
- Commits separados por recurso.

### Verificação final
- pytest tudo verde; `npm run build` verde.
- Preview DevTools: abrir um pregão importado → aba CAPAG (município e federal),
  Histórico (sem spam), Exportar (baixa), Relatório (abre PDF), Busca em itens.
  Screenshots. Console limpo.
- opus-reviewer nos novos módulos (capag, relatorio, historico, endpoints).
- COMO_RODAR.md: nota sobre `seed_capag.py` (passo opcional mensal).
