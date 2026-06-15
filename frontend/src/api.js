// Camada de API REAL (FastAPI) + adaptadores para o shape que a UI usa.
// Nada de mock: todo dado vem dos endpoints do CLAUDE.md §7.
const BASE = import.meta.env.VITE_API_URL || "/api";

async function req(caminho, opcoes = {}) {
  // timeoutMs: backend zumbi deixava a requisição pendurada e a UI em
  // skeleton eterno — com timeout ela cai no estado de erro com retry.
  // Só usado onde a espera legítima tem teto conhecido (ex.: descobrir).
  const { timeoutMs, ...resto } = opcoes;
  const ctrl = timeoutMs ? new AbortController() : null;
  const timer = ctrl ? setTimeout(() => ctrl.abort(), timeoutMs) : null;
  let r;
  try {
    r = await fetch(BASE + caminho, {
      headers: { "Content-Type": "application/json" },
      ...(ctrl ? { signal: ctrl.signal } : {}),
      ...resto,
    });
  } catch (e) {
    if (e.name === "AbortError") {
      throw new Error("o servidor não respondeu — confira se o backend está rodando");
    }
    throw e;
  } finally {
    if (timer) clearTimeout(timer);
  }
  if (!r.ok) {
    let detalhe = "";
    try {
      detalhe = (await r.json()).detail || "";
    } catch {
      /* corpo não-JSON */
    }
    const erro = new Error(detalhe || `Erro ${r.status}`);
    erro.status = r.status;
    throw erro;
  }
  return r.json();
}

// ---------- formatação de datas ISO → pt-BR ----------
function dataBr(iso, comHora = true) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const aaaa = d.getFullYear();
  if (!comHora) return `${dd}/${mm}/${aaaa}`;
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${dd}/${mm}/${aaaa} ${hh}:${mi}`;
}

// ---------- adaptadores backend → shape da UI (mesmo do protótipo) ----------
export function adaptarProduto(p) {
  return {
    id: p.id,
    cod: p.codigo || `PROD-${p.id}`,
    nome: p.nome,
    cat: p.categoria || "",
    custo: p.custo_unit,
    ncm: p.ncm,
    unidade: p.unidade,
    origem: p.origem,
    csosn: p.csosn,
    cst: p.cst,
    ativo: !!p.ativo,
  };
}

export function adaptarItem(i, produtosPorId) {
  const produto = i.produto_id ? produtosPorId[i.produto_id] : null;
  return {
    id: i.id,
    n: i.numero,
    nome: i.descricao || "",
    spec: i.info_complementar
      ? `${i.descricao}\n\nInformação complementar: ${i.info_complementar}`
      : i.descricao || "",
    qtd: i.qtd,
    unidade: i.unidade,
    unit: i.sigiloso ? null : i.valor_unit_estimado,   // TETO oficial do PNCP
    sigiloso: !!i.sigiloso,
    ncmPncp: i.ncm_pncp,
    beneficio: i.beneficio,
    criterio: i.criterio,
    // P3: custo efetivo (manual ▸ catálogo) e simulação por margem alvo
    custoManual: i.custo_manual ?? null,
    custoEfetivo: i.custo_efetivo ?? null,
    fonteCusto: i.fonte_custo ?? null,             // "manual" | "catalogo" | null
    simulacaoCustoMax: i.simulacao_custo_max ?? null,
    simulacaoLucro: i.simulacao_lucro ?? null,
    // P4: preço esperado de disputa (lance ▸ teto×(1−deságio) ▸ teto) e pisos
    lancePrevisto: i.lance_previsto ?? null,
    precoEsperado: i.preco_esperado ?? null,
    fontePreco: i.fonte_preco ?? null,             // "lance" | "desagio" | "teto" | null
    lanceMinimoAlvo: i.lance_minimo_alvo ?? null,
    empate: i.empate ?? null,
    match: produto
      ? { cod: produto.cod, score: i.match_score, confirmado: !!i.match_confirmado }
      : null,
  };
}

export function adaptarHabilitacao(h) {
  return {
    id: h.id,
    requisito: h.requisito,
    categoria: h.categoria,
    obrigatorio: !!h.obrigatorio,
    pagina: h.pagina,
    excerto: h.excerto,
    verificada: !!h.verificada,
    status: h.status_usuario,
  };
}

export function adaptarPregao(p) {
  const jb = p.json_busca || {};
  return {
    id: p.id,
    cnpj: p.cnpj,
    ano: p.ano,
    seq: p.seq,
    numeroControle: p.numero_controle,
    titulo: p.titulo || `${p.modalidade || "Edital"} ${p.seq}/${p.ano}`,
    orgao: p.orgao,
    unidadeCompradora: p.unidade || jb.unidade_nome || null,
    municipio: p.municipio,
    uf: p.uf,
    modalidade: p.modalidade,
    amparo: jb.fundamentacao_legal || null,
    beneficio: null, // por item no PNCP; o agregado aparece na tabela de itens
    valorTotal: p.valor_global,
    valorItens: p.valor_itens,   // Σ valor_total dos itens (oficial; fallback rotulado)
    // P5: potencial aderente — itens do meu ramo (sugeridos/confirmados) com
    // preço esperado. receitaAderente é a Σ persistida; o potencial exibido =
    // receitaAderente × margem_alvo da config (sempre rotulado "sim.").
    receitaAderente: p.receita_aderente,
    itensAderentes: p.itens_aderentes,
    prazo: dataBr(p.data_fim_vigencia),
    inicioPropostas: dataBr(p.data_inicio_vigencia),
    divulgacao: dataBr(jb.data_publicacao_pncp),
    situacao: p.situacao,
    status: p.situacao,
    descricao: p.descricao,
    linkPncp: p.link_pncp,
    salvo: !!p.salvo,
    novo: !!p.novo,
    statusPipeline: p.status_pipeline || null,
    dataDisputa: p.data_disputa || null,
    valorFinal: p.valor_final,
    buscaId: p.busca_id,
    sincronizado: !!p.sincronizado,
    arquivos: (p.arquivos || []).map((a) => ({
      titulo: a.titulo,
      tipo: a.tipo,
      url: a.url,
    })),
    // agregados crus do backend (a UI recalcula ao vivo nas edições)
    agregados: {
      veredito: p.veredito,
      lucroPotencial: p.lucro_potencial,
      margemMedia: p.margem_media,
      cobertura: p.cobertura,
      itensTotal: p.itens_total,
      itensConfirmados: p.itens_confirmados,
      itensSugeridos: p.itens_sugeridos,
      habilitacaoTotal: p.habilitacao_total,
      habilitacaoPendentes: p.habilitacao_pendentes,
      habilitacaoNaoVerificadas: p.habilitacao_nao_verificadas,
    },
    itens: null,        // carregados sob demanda via carregarItens
    habilitacao: null,  // idem via carregarHabilitacao
  };
}

// item da busca AO VIVO do PNCP (GET /descobrir) → shape de cartão.
// Sem agregados (não está no radar): veredito/itens ficam vazios na UI.
// Carrega o hit cru (para reenviar no importar), jaNoRadar e pregaoId.
// `extra` (P6): campos da avaliação sob demanda mesclados sobre o item (o
// front chama /descobrir/avaliar e mescla o resultado nos cartões pela
// numeroControle, sem refazer a busca).
export function adaptarDescoberto(d, extra = null) {
  const base = {
    id: d.numero_controle,        // chave estável da lista ao vivo
    numeroControle: d.numero_controle,
    cnpj: d.cnpj,
    ano: d.ano,
    seq: d.seq,
    titulo: d.titulo || `${d.modalidade || "Edital"} ${d.seq}/${d.ano}`,
    orgao: d.orgao,
    municipio: d.municipio,
    uf: d.uf,
    modalidade: d.modalidade,
    situacao: d.situacao,
    status: d.situacao,
    descricao: d.descricao,
    valorTotal: d.valor_global,
    prazo: dataBr(d.data_fim_vigencia),
    aoVivo: true,
    jaNoRadar: !!d.ja_no_radar,
    pregaoId: d.pregao_id,
    hit: d.hit,
    agregados: {},
    novo: false,
    // P6: avaliação sob demanda (preenchida ao mesclar; default não avaliado)
    avaliado: false,
    valorItens: null,
    itensTotal: null,
    itensAderentes: null,
    receitaAderente: null,
  };
  return extra ? { ...base, ...extra } : base;
}

export function adaptarBusca(b) {
  return {
    id: b.id,
    nome: b.nome,
    termos: b.termos,
    ufs: b.ufs,
    status: b.status,
    ativo: !!b.ativo,
    ultimaExec: dataBr(b.ultima_exec),
    novos: b.novos || 0,
  };
}

// ---------- chamadas ----------
let _checklistBaseCache = null;

export const api = {
  // descoberta
  listarBuscas: () => req("/buscas").then((bs) => bs.map(adaptarBusca)),
  criarBusca: (corpo) => req("/buscas", { method: "POST", body: JSON.stringify(corpo) }),
  atualizarBusca: (id, corpo) =>
    req(`/buscas/${id}`, { method: "PATCH", body: JSON.stringify(corpo) }),
  rodarBusca: (id) => req(`/buscas/${id}/rodar`, { method: "POST" }),

  // pregões
  listarPregoes: (filtros = {}) => {
    const q = new URLSearchParams();
    if (filtros.novos != null) q.set("novos", filtros.novos);
    if (filtros.salvos != null) q.set("salvos", filtros.salvos);
    if (filtros.uf) q.set("uf", filtros.uf);
    // P5: faixa de valor (mín/máx sobre o valor efetivo) e ordenação
    if (filtros.valorMin != null) q.set("valor_min", filtros.valorMin);
    if (filtros.valorMax != null) q.set("valor_max", filtros.valorMax);
    if (filtros.ordem && filtros.ordem !== "recente") q.set("ordem", filtros.ordem);
    const s = q.toString();
    return req("/pregoes" + (s ? `?${s}` : "")).then((ps) => ps.map(adaptarPregao));
  },
  pregao: (id) => req(`/pregoes/${id}`).then(adaptarPregao),
  atualizarPregao: (id, corpo) =>
    req(`/pregoes/${id}`, { method: "PATCH", body: JSON.stringify(corpo) }).then(adaptarPregao),
  // descartar pregão do radar (soft-delete no backend: some da lista e não
  // volta; PATCH {descartado:false} desfaz). DELETE responde 204 sem corpo →
  // req() faz r.json() e estoura; 204 = ok (mesmo padrão de removerCertidao).
  descartarPregao: (id) =>
    req(`/pregoes/${id}`, { method: "DELETE" }).catch((e) => {
      if (e instanceof SyntaxError) return null;
      throw e;
    }),
  sincronizar: (id) => req(`/pregoes/${id}/sincronizar`, { method: "POST" }),
  sincronizarItens: (id) => req(`/pregoes/${id}/sincronizar-itens`, { method: "POST" }),
  pipelineResumo: () => req("/pipeline/resumo"),
  // PATCH genérico já existe: atualizarPregao(id, {status_pipeline, data_disputa, valor_final, salvo})
  carregarItens: (pregaoId, produtosPorId) =>
    req(`/pregoes/${pregaoId}/itens`).then((is) =>
      is.map((i) => adaptarItem(i, produtosPorId))),
  carregarHabilitacao: (pregaoId) =>
    req(`/pregoes/${pregaoId}/habilitacao`).then((hs) => hs.map(adaptarHabilitacao)),
  carregarArquivos: (pregaoId) =>
    req(`/pregoes/${pregaoId}/arquivos`).then((as) =>
      as.map((a) => ({ titulo: a.titulo, tipo: a.tipo, url: a.url }))),
  fiscal: (pregaoId) => req(`/pregoes/${pregaoId}/fiscal`),
  // CAPAG — risco de pagamento do comprador (Tesouro/SICONFI). Lazy: chamado
  // só quando a aba CAPAG abre. Devolve o dict cru do backend (disponivel,
  // nota, cor, icf, origem, indicadores[], ente, uf, esfera, fonte, motivo).
  capag: (pregaoId) => req(`/pregoes/${pregaoId}/capag`),

  // histórico do pregão (PNCP) — só os marcos, sem o ruído de sync. Lazy: a aba
  // Histórico chama na abertura. Devolve {eventos:[{data,evento,responsavel,
  // justificativa,documento}]}.
  historico: (pregaoId) => req(`/pregoes/${pregaoId}/historico`),

  // resultados/homologação do pregão (PNCP). Lazy: a aba Resultados chama na
  // abertura. Bate item a item no PNCP → LENTO; timeout generoso (120s, espelha
  // o /descobrir e o rag/indexar). Devolve {homologado, itens:[...], resumo|null}.
  resultadosPregao: (pregaoId) =>
    req(`/pregoes/${pregaoId}/resultados`, { timeoutMs: 120000 }),

  // RAG "Perguntar ao edital" (Fase 1, 100% local). Lazy: a aba Perguntar chama
  // ragStatus na abertura. Respostas são EXTRATIVAS — trechos verbatim do PDF.
  // status → {indexado, n_chunks?, n_paginas?, ingerido_em?, modelo?}.
  ragStatus: (pregaoId) => req(`/pregoes/${pregaoId}/rag/status`),
  // indexar → {n_chunks, n_paginas, motivo?}. Roda o e5 local + extrai PDFs:
  // operação LENTA — timeout generoso (espelha o /descobrir).
  ragIndexar: (pregaoId) =>
    req(`/pregoes/${pregaoId}/rag/indexar`, { method: "POST", timeoutMs: 120000 }),
  // perguntar → {disponivel, motivo?, pergunta, trechos:[{texto, arquivo_id,
  // arquivo_titulo, pagina, offset_inicio, offset_fim, score}], fonte?}.
  // Fase 2 (opt-in): com sintetizar=true e havendo trechos, a resposta ganha
  // um bloco `sintese` (prosa fundamentada NOS trechos): {sintese_disponivel,
  // resposta?, trechos_citados?:[int 1-based], modo?, fonte?} OU, sem fundamento,
  // {sintese_disponivel:false, motivo:"nao_encontrado"|"nao_fundamentado"|"erro_sintese"}.
  // A síntese roda o Claude CLI local (LENTO) → timeout generoso só quando ligada.
  ragPerguntar: (pregaoId, pergunta, k, sintetizar) => {
    const body = { pergunta };
    if (k != null) body.k = k;
    if (sintetizar) body.sintetizar = true;
    return req(`/pregoes/${pregaoId}/rag/perguntar`, {
      method: "POST",
      body: JSON.stringify(body),
      // CLI local pode levar dezenas de segundos; sem síntese mantém o curto.
      timeoutMs: sintetizar ? 180000 : undefined,
    });
  },

  // URLs de download direto (o navegador baixa via <a> / window.open; não passam
  // pelo req()/fetch porque a resposta é binária com content-disposition).
  exportarItensUrl: (pregaoId, formato = "csv") =>
    `${BASE}/pregoes/${pregaoId}/itens/export?formato=${formato}`,
  relatorioPdfUrl: (pregaoId) => `${BASE}/pregoes/${pregaoId}/relatorio.pdf`,

  // matching (human-in-the-loop)
  definirMatch: (itemId, produtoId, confirmado) =>
    req(`/itens/${itemId}/match`, {
      method: "POST",
      body: JSON.stringify({ produto_id: produtoId, confirmado }),
    }),

  // custo manual por item (override local do pregão, P3) — null limpa
  definirCustoItem: (itemId, valor) =>
    req(`/itens/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify({ custo_manual: valor }),
    }),

  // lance previsto por item (preço esperado de disputa, P4) — null limpa
  // (volta ao deságio/teto). Mesmo endpoint do custo; só o campo enviado muda.
  definirLanceItem: (itemId, valor) =>
    req(`/itens/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify({ lance_previsto: valor }),
    }),

  // catálogo
  listarCatalogo: () => req("/catalogo").then((ps) => ps.map(adaptarProduto)),
  criarProduto: (corpo) =>
    req("/catalogo", { method: "POST", body: JSON.stringify(corpo) }),
  atualizarProduto: (id, corpo) =>
    req(`/catalogo/${id}`, { method: "PATCH", body: JSON.stringify(corpo) }),

  // habilitação
  definirStatusHabilitacao: (id, status) =>
    req(`/habilitacao/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status_usuario: status }),
    }),

  // PNCP ao vivo (explorar a busca nacional sem persistir)
  // termos[]/excluir[] viram params repetidos; ufs/modalidades/esferas viram csv.
  descobrir: ({
    termos = [], excluir = [], ufs = [], uf, status, tipo, ordenacao,
    modalidades = [], esferas = [], soBens = false, pagina, rerank = false,
  } = {}) => {
    const p = new URLSearchParams();
    (termos || []).filter(Boolean).forEach((t) => p.append("q", t));
    (excluir || []).filter(Boolean).forEach((t) => p.append("excluir", t));
    // UF aceita lista (multi) ou um único valor legado; "todas" = sem filtro
    const listaUf = (ufs && ufs.length ? ufs : uf ? [uf] : [])
      .filter((u) => u && u !== "todas");
    if (listaUf.length) p.set("ufs", listaUf.join(","));
    if (status) p.set("status", status);
    if (tipo) p.set("tipos_documento", tipo);
    if (ordenacao) p.set("ordenacao", ordenacao);
    if (modalidades && modalidades.length) p.set("modalidades", modalidades.join(","));
    if (esferas && esferas.length) p.set("esferas", esferas.join(","));
    // "só compra de bens": pós-filtro aquisição-aware no backend (além das
    // modalidades de compra que o front já manda)
    if (soBens) p.set("so_bens", "true");
    // re-rank semântico LOCAL (opt-in): reordena APENAS a página por
    // similaridade e5 aos termos. O backend só aplica quando há termo e a
    // ordenação é relevância/default; senão devolve rerank_aplicado=false.
    if (rerank) p.set("rerank", "true");
    if (pagina != null) p.set("pagina", pagina);
    const s = p.toString();
    // 90s: multi-termo (até 5×1 req/s) + retries do WAF cabem; backend morto
    // não pendura mais a UI em skeleton eterno
    return req("/descobrir" + (s ? `?${s}` : ""), { timeoutMs: 90000 }).then((r) => ({
      total: r.total,
      totalExato: r.total_exato,
      fonte: r.fonte,           // "consulta" (bulk, valores oficiais) | "busca" (textual)
      pagina: r.pagina,
      tamanho: r.tamanho,
      // re-rank semântico local: flag + motivo (quando não aplicado)
      rerankAplicado: r.rerank_aplicado === true,
      rerankMotivo: r.rerank_motivo || null,
      itens: (r.itens || []).map(adaptarDescoberto),
    }));
  },
  importarPregao: (numeroControle, hit) =>
    req("/descobrir/importar", {
      method: "POST",
      body: JSON.stringify({ numero_controle: numeroControle, hit }),
    }).then(adaptarPregao),

  // P6: avaliação sob demanda no modo ao vivo (valor real + potencial aderente)
  // sem importar nada. `alvos`: [{cnpj, ano, seq, numero_controle}] (máx. 40).
  // Devolve {avaliados: {nc: {valor_itens, itens_total, itens_aderentes,
  // receita_aderente}}, erros: {nc: msg}} cru (o FindScreen mescla nos cartões).
  avaliarDescobertos: (alvos) =>
    req("/descobrir/avaliar", {
      method: "POST",
      body: JSON.stringify({ alvos }),
    }),

  // checklist base de habilitação (referência geral — cacheada no módulo)
  checklistBase: () => {
    if (_checklistBaseCache) return Promise.resolve(_checklistBaseCache);
    return req("/habilitacao/base").then((r) => {
      _checklistBaseCache = r;
      return r;
    });
  },

  // minhas certidões — documentos de habilitação reutilizáveis (CND, FGTS,
  // trabalhista etc.) com aviso de vencimento. status/dias_restantes vêm
  // calculados pelo backend a partir de hoje (vencida|vence_em_breve|ok|
  // sem_validade). validade = ISO 'YYYY-MM-DD' ou null = sem validade.
  listarCertidoes: () => req("/certidoes"),
  criarCertidao: (corpo) =>
    req("/certidoes", { method: "POST", body: JSON.stringify(corpo) }),
  atualizarCertidao: (id, corpo) =>
    req(`/certidoes/${id}`, { method: "PATCH", body: JSON.stringify(corpo) }),
  removerCertidao: (id) =>
    req(`/certidoes/${id}`, { method: "DELETE" }).catch((e) => {
      // DELETE responde 204 sem corpo → req() faz r.json() e estoura; 204 = ok
      if (e instanceof SyntaxError) return null;
      throw e;
    }),
  // só vencidas + vence_em_breve (badge/dashboard) → {total, certidoes:[...]}
  alertasCertidoes: () => req("/certidoes/alertas"),

  // minha empresa — cadastro do fornecedor que preenche as minutas de
  // declaração de habilitação (RAG Fase 3). Campos podem vir null. porte ∈
  // {"me_epp","normal",null}. PUT envia o objeto inteiro.
  getEmpresa: () => req("/empresa"),
  salvarEmpresa: (dados) =>
    req("/empresa", { method: "PUT", body: JSON.stringify(dados) }),

  // declarações de habilitação por pregão (minutas renderizadas com os dados
  // da empresa). Lazy: a aba Declarações chama na abertura. Devolve
  // {declaracoes:[{id,titulo,categoria,fundamento_legal,texto_renderizado,
  // completo,faltando:[campos],exigido_no_edital,aviso}], aviso}. Quando
  // completo===false, faltam dados da empresa (lista faltando).
  declaracoesPregao: (pregaoId) => req(`/pregoes/${pregaoId}/declaracoes`),

  // inteligência de mercado — histórico de preços + concorrentes.
  // A amostra reflete SÓ os editais já coletados (não é base nacional); a UI
  // sempre mostra o N. coletar bate no PNCP item a item → LENTO (timeout 180s).
  // coletar → {pregoes_processados, pregoes_homologados, itens_gravados}.
  mercadoColetar: (pregaoIds) =>
    req("/mercado/coletar", {
      method: "POST",
      body: JSON.stringify(pregaoIds && pregaoIds.length ? { pregao_ids: pregaoIds } : {}),
      timeoutMs: 180000,
    }),
  // precos → {amostra, resumo:{preco_unit_min, preco_unit_mediana,
  // preco_unit_max, desagio_medio_pct}|null, itens:[...]}. desagio_*_pct é FRAÇÃO 0..1.
  mercadoPrecos: (q, ncm) => {
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (ncm) p.set("ncm", ncm);
    const s = p.toString();
    return req("/mercado/precos" + (s ? `?${s}` : ""));
  },
  // concorrentes → {amostra_itens, concorrentes:[{cnpj, nome, porte, n_vitorias,
  // desagio_medio_pct, valor_total_homologado, n_orgaos, ufs:[...]}]} (já ordenado por vitórias).
  mercadoConcorrentes: (uf, q) => {
    const p = new URLSearchParams();
    if (uf) p.set("uf", uf);
    if (q) p.set("q", q);
    const s = p.toString();
    return req("/mercado/concorrentes" + (s ? `?${s}` : ""));
  },

  // config
  lerConfig: () => req("/config"),
  atualizarConfig: (corpo) =>
    req("/config", { method: "PATCH", body: JSON.stringify(corpo) }),
};
