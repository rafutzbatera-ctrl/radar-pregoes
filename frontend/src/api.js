// Camada de API REAL (FastAPI) + adaptadores para o shape que a UI usa.
// Nada de mock: todo dado vem dos endpoints do CLAUDE.md §7.
const BASE = import.meta.env.VITE_API_URL || "/api";

async function req(caminho, opcoes = {}) {
  const r = await fetch(BASE + caminho, {
    headers: { "Content-Type": "application/json" },
    ...opcoes,
  });
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
    unit: i.sigiloso ? null : i.valor_unit_estimado,
    sigiloso: !!i.sigiloso,
    ncmPncp: i.ncm_pncp,
    beneficio: i.beneficio,
    criterio: i.criterio,
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
    prazo: dataBr(p.data_fim_vigencia),
    inicioPropostas: dataBr(p.data_inicio_vigencia),
    divulgacao: dataBr(jb.data_publicacao_pncp),
    situacao: p.situacao,
    status: p.situacao,
    descricao: p.descricao,
    linkPncp: p.link_pncp,
    salvo: !!p.salvo,
    novo: !!p.novo,
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
    const s = q.toString();
    return req("/pregoes" + (s ? `?${s}` : "")).then((ps) => ps.map(adaptarPregao));
  },
  pregao: (id) => req(`/pregoes/${id}`).then(adaptarPregao),
  atualizarPregao: (id, corpo) =>
    req(`/pregoes/${id}`, { method: "PATCH", body: JSON.stringify(corpo) }).then(adaptarPregao),
  sincronizar: (id) => req(`/pregoes/${id}/sincronizar`, { method: "POST" }),
  carregarItens: (pregaoId, produtosPorId) =>
    req(`/pregoes/${pregaoId}/itens`).then((is) =>
      is.map((i) => adaptarItem(i, produtosPorId))),
  carregarHabilitacao: (pregaoId) =>
    req(`/pregoes/${pregaoId}/habilitacao`).then((hs) => hs.map(adaptarHabilitacao)),
  fiscal: (pregaoId) => req(`/pregoes/${pregaoId}/fiscal`),

  // matching (human-in-the-loop)
  definirMatch: (itemId, produtoId, confirmado) =>
    req(`/itens/${itemId}/match`, {
      method: "POST",
      body: JSON.stringify({ produto_id: produtoId, confirmado }),
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

  // config
  lerConfig: () => req("/config"),
  atualizarConfig: (corpo) =>
    req("/config", { method: "PATCH", body: JSON.stringify(corpo) }),
};
