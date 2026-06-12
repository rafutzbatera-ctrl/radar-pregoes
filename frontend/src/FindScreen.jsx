// RADAR DE PREGÕES — Telas Encontrar / Meus pregões / Buscas salvas / Catálogo
// Dados reais via props (App carrega da API); estados de carregando/erro reais.
import React from "react";
import { motion } from "framer-motion";
import { api } from "./api.js";
import {
  MotionCtx, Ico, fmtBRL, Etiqueta, VEREDITO_TXT, normalizarVeredito, CostInput, Resumo,
} from "./helpers.jsx";
import { Kanban, STATUS_PIPELINE } from "./Kanban.jsx";

const norm = (s) => String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
const _fmtInt = new Intl.NumberFormat("pt-BR");
const fmtInt = (n) => _fmtInt.format(n || 0);

// tabela oficial de modalidades do PNCP (CLAUDE.md §4.1 — ids 1..13)
const MODALIDADES_PNCP = [
  { id: "1", nome: "Leilão eletrônico" },
  { id: "2", nome: "Diálogo competitivo" },
  { id: "3", nome: "Concurso" },
  { id: "4", nome: "Concorrência eletrônica" },
  { id: "5", nome: "Concorrência presencial" },
  { id: "6", nome: "Pregão eletrônico" },
  { id: "7", nome: "Pregão presencial" },
  { id: "8", nome: "Dispensa" },
  { id: "9", nome: "Inexigibilidade" },
  { id: "10", nome: "Manifestação de interesse" },
  { id: "11", nome: "Pré-qualificação" },
  { id: "12", nome: "Credenciamento" },
  { id: "13", nome: "Leilão presencial" },
];
const ESFERAS_PNCP = [
  { id: "M", nome: "Municipal" },
  { id: "E", nome: "Estadual" },
  { id: "F", nome: "Federal" },
  { id: "D", nome: "Distrital" },
];
// UFs do Brasil (para o multisseletor; no modo radar a lista vem dos pregões)
const UFS_BR = [
  "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
  "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
];

/* ---------- dropdown multisseleção (checkboxes) — visual dos selects ---------- */
function MultiSelect({ rotulo, opcoes, selecionados, aoMudar, larguraMenu }) {
  const [aberto, setAberto] = React.useState(false);
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (!aberto) return;
    const fora = (e) => { if (ref.current && !ref.current.contains(e.target)) setAberto(false); };
    document.addEventListener("mousedown", fora);
    return () => document.removeEventListener("mousedown", fora);
  }, [aberto]);
  const alternar = (id) => {
    aoMudar(selecionados.includes(id)
      ? selecionados.filter((x) => x !== id)
      : [...selecionados, id]);
  };
  const n = selecionados.length;
  const resumo = n === 0 ? `${rotulo} · todas` : `${rotulo} · ${n} selecionada${n === 1 ? "" : "s"}`;
  return (
    <div className="multi-sel" ref={ref}>
      <button type="button" className={"filtro-sel multi-trigger" + (n ? " on" : "")}
        aria-haspopup="true" aria-expanded={aberto} onClick={() => setAberto((a) => !a)}>
        {resumo}
        <span className="multi-caret" aria-hidden="true">▾</span>
      </button>
      {aberto && (
        <div className="multi-menu" role="group" aria-label={rotulo} style={larguraMenu ? { minWidth: larguraMenu } : undefined}>
          {opcoes.map((o) => (
            <label key={o.id} className="multi-opt">
              <input type="checkbox" checked={selecionados.includes(o.id)} onChange={() => alternar(o.id)} />
              <span>{o.nome}</span>
            </label>
          ))}
          {n > 0 && (
            <button type="button" className="multi-limpar" onClick={() => aoMudar([])}>Limpar</button>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------- entrada de chips de palavra-chave (inclusão + exclusão) ---------- */
function ChipsInput({ termos, excluir, aoMudar }) {
  const [texto, setTexto] = React.useState("");
  const commit = (bruto) => {
    const t = bruto.trim();
    if (!t) return;
    if (t.startsWith("-")) {
      const termo = t.slice(1).trim();
      if (termo && !excluir.includes(termo) && excluir.length < 5) {
        aoMudar(termos, [...excluir, termo]);
      }
    } else if (!termos.includes(t) && termos.length < 5) {
      aoMudar([...termos, t], excluir);
    }
    setTexto("");
  };
  const aoTeclar = (e) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      commit(texto);
    } else if (e.key === "Backspace" && texto === "") {
      // remove o último chip (exclusão tem prioridade visual; remove do que existir por último)
      if (excluir.length) aoMudar(termos, excluir.slice(0, -1));
      else if (termos.length) aoMudar(termos.slice(0, -1), excluir);
    }
  };
  const removerTermo = (t) => aoMudar(termos.filter((x) => x !== t), excluir);
  const removerExcl = (t) => aoMudar(termos, excluir.filter((x) => x !== t));
  return (
    <label className="busca chips-busca">
      {Ico.busca}
      <span className="chips-campo">
        {termos.map((t) => (
          <span key={"i" + t} className="kw-chip">
            {t}
            <button type="button" className="kw-x" aria-label={"Remover " + t} onClick={() => removerTermo(t)}>×</button>
          </span>
        ))}
        {excluir.map((t) => (
          <span key={"e" + t} className="kw-chip excl">
            sem: {t}
            <button type="button" className="kw-x" aria-label={"Remover exclusão " + t} onClick={() => removerExcl(t)}>×</button>
          </span>
        ))}
        <input type="text" value={texto} onChange={(e) => setTexto(e.target.value)}
          onKeyDown={aoTeclar} onBlur={() => commit(texto)}
          placeholder={termos.length || excluir.length ? "" : "Palavra-chave — Enter adiciona; prefixo - exclui"}
          aria-label="Adicionar palavra-chave (Enter ou vírgula; comece com - para excluir)" />
      </span>
    </label>
  );
}

export function FindScreen({ aoAbrir, apenasSalvos, pregoes, erro, recarregar, aoImportar, mudarPipeline, margemAlvo = 0.2 }) {
  const { reduzido, estatico } = React.useContext(MotionCtx);
  const [busca, setBusca] = React.useState("");          // input texto (modo radar)
  const [uf, setUf] = React.useState("todas");
  const [modalidade, setModalidade] = React.useState("todas");
  const [recebendo, setRecebendo] = React.useState(false);
  const [soNovos, setSoNovos] = React.useState(false);
  // fonte: "radar" (pregões já descobertos) | "vivo" (busca ao vivo no PNCP)
  const [fonte, setFonte] = React.useState("radar");
  const aoVivo = !apenasSalvos && fonte === "vivo";

  // ----- P5: faixa de valor + ordenação (radar e Meus pregões; NÃO no ao vivo) -----
  // O App mantém `pregoes` global como fonte do resto do app; aqui, quando algum
  // filtro/ordem ≠ default, buscamos a lista filtrada LOCAL no backend (debounce
  // 400ms) e a usamos no lugar da global. Default → usa a global.
  const [valorMin, setValorMin] = React.useState("");
  const [valorMax, setValorMax] = React.useState("");
  const [ordem, setOrdem] = React.useState("recente");
  const [listaFiltrada, setListaFiltrada] = React.useState(null); // null = usa global
  const filtroValorOuOrdemAtivo =
    valorMin.trim() !== "" || valorMax.trim() !== "" || ordem !== "recente";

  // ----- funil de disputa (Meus pregões): faixa-resumo + alternância Lista | Quadro -----
  const [resumo, setResumo] = React.useState(null);
  const [vista, setVista] = React.useState("lista");     // "lista" | "quadro"
  const carregarResumo = React.useCallback(() => {
    if (!apenasSalvos) return;
    api.pipelineResumo().then(setResumo).catch(() => {});
  }, [apenasSalvos]);
  React.useEffect(() => { carregarResumo(); }, [carregarResumo]);
  // o resumo é calculado no backend; recarrega encadeado ao PATCH (sem timer
  // fixo — achado do review: PATCH lento > timer recarregava dado velho)
  const mudarPipelineEResumo = React.useCallback((id, campos) => {
    if (!mudarPipeline) return;
    mudarPipeline(id, campos).then(carregarResumo).catch(() => {});
  }, [mudarPipeline, carregarResumo]);

  // ----- filtros do modo "PNCP ao vivo" -----
  const [termos, setTermos] = React.useState([]);        // chips de inclusão
  const [excluir, setExcluir] = React.useState([]);      // chips de exclusão
  const [ufsVivo, setUfsVivo] = React.useState([]);      // multisseleção de UF
  const [modVivo, setModVivo] = React.useState([]);      // ids de modalidade
  const [esferasVivo, setEsferasVivo] = React.useState([]);
  const [statusVivo, setStatusVivo] = React.useState("recebendo_proposta");
  const [tipoVivo, setTipoVivo] = React.useState("edital");
  const [ordemVivo, setOrdemVivo] = React.useState("-data");
  // P6: faixa de valor + ordenação CLIENT-SIDE sobre os itens já carregados/avaliados
  const [valorMinVivo, setValorMinVivo] = React.useState("");
  const [valorMaxVivo, setValorMaxVivo] = React.useState("");
  const [ordemVivoLocal, setOrdemVivoLocal] = React.useState("recente");

  // parse pt-BR ("1.234,50" ou "1234.50") → número | null
  const parseValor = (s) => {
    const t = String(s).trim();
    if (t === "") return null;
    const n = parseFloat(t.replace(/\./g, "").replace(",", "."));
    return Number.isFinite(n) && n >= 0 ? n : null;
  };

  // refetch local filtrado/ordenado (debounce 400ms). Só dispara fora do ao vivo.
  React.useEffect(() => {
    if (aoVivo) return;
    if (!filtroValorOuOrdemAtivo) { setListaFiltrada(null); return; }
    const id = setTimeout(() => {
      api.listarPregoes({
        salvos: apenasSalvos ? true : undefined,
        valorMin: parseValor(valorMin),
        valorMax: parseValor(valorMax),
        ordem,
      }).then(setListaFiltrada).catch(() => setListaFiltrada(null));
    }, 400);
    return () => clearTimeout(id);
  }, [aoVivo, apenasSalvos, filtroValorOuOrdemAtivo, valorMin, valorMax, ordem]);

  const carregando = pregoes == null && !erro;
  // fonte da lista do radar/Meus pregões: global (default) ou filtrada (P5)
  const fonteLista = filtroValorOuOrdemAtivo && listaFiltrada ? listaFiltrada : (pregoes || []);
  const base = fonteLista.filter((p) => !apenasSalvos || p.salvo);
  const ufs = Array.from(new Set(base.map((p) => p.uf).filter(Boolean))).sort();
  const modalidades = Array.from(new Set(base.map((p) => p.modalidade).filter(Boolean))).sort();

  const tokens = norm(busca).split(/\s+/).filter((t) => t.length >= 3);
  const lista = base.filter((p) => {
    if (uf !== "todas" && p.uf !== uf) return false;
    if (modalidade !== "todas" && p.modalidade !== modalidade) return false;
    if (recebendo && !norm(p.status).includes("recebendo")) return false;
    if (soNovos && !p.novo) return false;
    if (tokens.length > 0 && !apenasSalvos) {
      const palheiro = norm([p.titulo, p.orgao, p.municipio, p.descricao].join(" "));
      if (!tokens.some((t) => palheiro.includes(t))) return false;
    }
    return true;
  });
  const qtdNovos = base.filter((p) => p.novo).length;

  const entrada = reduzido
    ? { hidden: { opacity: 0 }, show: { opacity: 1, transition: { duration: 0.15 } } }
    : { hidden: { opacity: 0, y: 14 }, show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 320, damping: 28 } } };
  const pai = { hidden: {}, show: { transition: { staggerChildren: reduzido ? 0 : 0.055, delayChildren: reduzido ? 0 : 0.05 } } };

  /* ---------- modo "PNCP ao vivo" (busca na API sem persistir) ---------- */
  const [vivo, setVivo] = React.useState({ itens: [], total: 0, totalExato: true, fonte: "consulta", pagina: 1, carregando: false, erro: null });
  const [importando, setImportando] = React.useState(null); // numero_controle em importação

  // filtros atuais empacotados (mesma página para todos os termos no "carregar mais")
  const filtrosVivo = React.useCallback((pagina) => ({
    termos, excluir, ufs: ufsVivo, modalidades: modVivo, esferas: esferasVivo,
    status: statusVivo, tipo: tipoVivo, ordenacao: ordemVivo, pagina,
  }), [termos, excluir, ufsVivo, modVivo, esferasVivo, statusVivo, tipoVivo, ordemVivo]);

  const buscarVivo = React.useCallback((pagina, concatenar) => {
    setVivo((v) => ({ ...v, carregando: true, erro: null }));
    api.descobrir(filtrosVivo(pagina))
      .then((r) => setVivo((v) => ({
        itens: concatenar ? [...v.itens, ...r.itens] : r.itens,
        total: r.total, totalExato: r.totalExato !== false, fonte: r.fonte || "busca",
        pagina, carregando: false, erro: null,
      })))
      .catch((e) => setVivo((v) => ({ ...v, carregando: false, erro: e.message || "erro" })));
  }, [filtrosVivo]);

  // debounce 500ms ao mudar qualquer filtro (somente no modo ao vivo)
  React.useEffect(() => {
    if (!aoVivo) return;
    const t = setTimeout(() => buscarVivo(1, false), 500);
    return () => clearTimeout(t);
  }, [aoVivo, buscarVivo]);

  const nTermos = termos.length;

  // ----- P6: avaliação sob demanda no modo ao vivo -----
  const [avaliando, setAvaliando] = React.useState(false);
  // quantos itens ainda não foram avaliados (nem deram erro) — alvos do próximo clique
  const naoAvaliados = vivo.itens.filter((i) => !i.avaliado && !i.naoAvaliavel);
  const aValiar = Math.min(naoAvaliados.length, 40);     // cap 40 por clique
  // X ≈ N×1.5s, arredondado em passos de 5s (mínimo 5s)
  const segEstimados = Math.max(5, Math.round((aValiar * 1.5) / 5) * 5);

  const avaliar = () => {
    if (avaliando || aValiar === 0) return;
    const lote = naoAvaliados.slice(0, 40);
    const alvos = lote.map((i) => ({
      cnpj: i.cnpj, ano: i.ano, seq: i.seq, numero_controle: i.numeroControle,
    }));
    setAvaliando(true);
    api.avaliarDescobertos(alvos)
      .then((r) => {
        const av = r.avaliados || {};
        const er = r.erros || {};
        setVivo((v) => ({
          ...v,
          itens: v.itens.map((i) => {
            const dados = av[i.numeroControle];
            if (dados) {
              return {
                ...i, avaliado: true, naoAvaliavel: false,
                valorItens: dados.valor_itens,
                itensTotal: dados.itens_total,
                itensAderentes: dados.itens_aderentes,
                receitaAderente: dados.receita_aderente,
              };
            }
            if (er[i.numeroControle]) return { ...i, naoAvaliavel: true };
            return i;
          }),
        }));
      })
      .catch(() => {})       // erro de rede: silencioso (re-clique tenta de novo)
      .finally(() => setAvaliando(false));
  };

  // P6.1 — avaliação AUTOMÁTICA: o valor real NÃO vem na busca do PNCP
  // (medido: 0 de 20 hits com valor_global), só na API de itens. Então cada
  // página carregada se avalia sozinha ~1,5s após assentar (o debounce da
  // digitação já segura novas buscas); itens com erro não re-disparam
  // (naoAvaliavel sai de aValiar) e o botão segue como retry manual.
  const avaliarRef = React.useRef(avaliar);
  avaliarRef.current = avaliar;
  React.useEffect(() => {
    if (!aoVivo || avaliando || aValiar === 0) return;
    const t = setTimeout(() => avaliarRef.current(), 1500);
    return () => clearTimeout(t);
  }, [aoVivo, avaliando, aValiar]);

  // P6: faixa de valor + ordenação aplicadas CLIENT-SIDE aos itens carregados.
  // valor efetivo do item = valorItens (avaliado) ▸ valorTotal do hit.
  const valorEfetivoVivo = (i) => (i.valorItens != null ? i.valorItens : i.valorTotal);
  const filtroVivoAtivo =
    valorMinVivo.trim() !== "" || valorMaxVivo.trim() !== "" || ordemVivoLocal !== "recente";
  const vivoExibido = React.useMemo(() => {
    if (!filtroVivoAtivo) return vivo;
    const min = parseValor(valorMinVivo);
    const max = parseValor(valorMaxVivo);
    let itens = vivo.itens.filter((i) => {
      const v = valorEfetivoVivo(i);
      if (min != null && (v == null || v < min)) return false;
      if (max != null && (v == null || v > max)) return false;
      return true;
    });
    if (ordemVivoLocal !== "recente") {
      // sort estável (índice como desempate) → não avaliados/nulos vão para o fim
      const chave = ordemVivoLocal === "potencial"
        ? (i) => i.receitaAderente
        : valorEfetivoVivo;     // "valor"
      itens = itens
        .map((i, idx) => [i, idx])
        .sort((a, b) => {
          const va = chave(a[0]); const vb = chave(b[0]);
          if (va == null && vb == null) return a[1] - b[1];
          if (va == null) return 1;       // nulo para o fim
          if (vb == null) return -1;
          return vb - va || a[1] - b[1];  // desc, estável
        })
        .map(([i]) => i);
    }
    return { ...vivo, itens };
  }, [vivo, filtroVivoAtivo, valorMinVivo, valorMaxVivo, ordemVivoLocal]);

  const importar = (item) => {
    if (importando) return;
    setImportando(item.numeroControle);
    aoImportar(item.numeroControle, item.hit)
      .then((pregao) => {
        // marca o item da lista ao vivo como "no radar" (link p/ análise local)
        setVivo((v) => ({
          ...v,
          itens: v.itens.map((i) => (i.numeroControle === item.numeroControle
            ? { ...i, jaNoRadar: true, pregaoId: pregao.id } : i)),
        }));
        aoAbrir(pregao.id);
      })
      .catch(() => {})
      .finally(() => setImportando(null));
  };

  return (
    <motion.div className="screen-inner" variants={pai} initial={estatico ? false : "hidden"} animate="show">
      <motion.div variants={entrada}>
        <div className="silk">{apenasSalvos ? "Acompanhamento" : "Oportunidades · PNCP"}</div>
        <h1 className="pg-titulo">{apenasSalvos ? "Meus pregões" : "Encontrar pregões"}</h1>
        <p className="pg-sub">
          {apenasSalvos
            ? "Pregões que você salvou para acompanhar. O monitoramento marca os novos automaticamente."
            : "Busque por palavra-chave e veja o veredito prévio antes de abrir a análise."}
        </p>
      </motion.div>

      {!apenasSalvos && (
        <motion.div className="seg fonte-seg" role="group" aria-label="Fonte dos pregões" variants={entrada}>
          <button type="button" className={"seg-btn" + (fonte === "radar" ? " on" : "")}
            aria-pressed={fonte === "radar"} onClick={() => setFonte("radar")}>
            No meu radar
          </button>
          <button type="button" className={"seg-btn" + (fonte === "vivo" ? " on" : "")}
            aria-pressed={fonte === "vivo"} onClick={() => setFonte("vivo")}>
            PNCP ao vivo
          </button>
        </motion.div>
      )}

      {apenasSalvos && resumo && (
        <motion.div className="resumo pipeline-resumo" variants={entrada}>
          {STATUS_PIPELINE.map((s) => (
            <Resumo key={s.id} k={s.rotulo} v={String(resumo.por_status[s.id] || 0)} />
          ))}
          <Resumo k="Taxa de ganho"
            v={resumo.taxa_ganho != null ? Math.round(resumo.taxa_ganho * 100) + "%" : "—"}
            sub={resumo.ganhos + " ganhos · " + resumo.perdidos + " perdidos"} />
          <Resumo k="Valor ganho"
            v={resumo.valor_ganho != null ? fmtBRL(resumo.valor_ganho) : "—"}
            sub={resumo.ganhos_sem_valor > 0 ? resumo.ganhos_sem_valor + " ganho(s) sem valor informado" : undefined} />
        </motion.div>
      )}

      {apenasSalvos && (
        <motion.div className="seg vista-seg" role="group" aria-label="Modo de visualização" variants={entrada}>
          <button type="button" className={"seg-btn" + (vista === "lista" ? " on" : "")}
            aria-pressed={vista === "lista"} onClick={() => setVista("lista")}>
            Lista
          </button>
          <button type="button" className={"seg-btn" + (vista === "quadro" ? " on" : "")}
            aria-pressed={vista === "quadro"} onClick={() => setVista("quadro")}>
            Quadro
          </button>
        </motion.div>
      )}

      {!(apenasSalvos && vista === "quadro") && (
      <motion.div className="filtros" variants={entrada}>
        {!apenasSalvos && !aoVivo && (
          <label className="busca">
            {Ico.busca}
            <input type="text" value={busca} onChange={(e) => setBusca(e.target.value)}
              placeholder="Palavra-chave — ex.: áudio, vídeo, projetor"
              aria-label="Buscar pregões por palavra-chave" />
          </label>
        )}
        {aoVivo && (
          <ChipsInput termos={termos} excluir={excluir}
            aoMudar={(t, e) => { setTermos(t); setExcluir(e); }} />
        )}

        {/* UF: select simples no radar; multisseleção no modo ao vivo */}
        {aoVivo ? (
          <MultiSelect rotulo="UF" opcoes={UFS_BR.map((u) => ({ id: u, nome: u }))}
            selecionados={ufsVivo} aoMudar={setUfsVivo} />
        ) : (
          <select className="filtro-sel" value={uf} onChange={(e) => setUf(e.target.value)} aria-label="Filtrar por UF">
            <option value="todas">UF · todas</option>
            {ufs.map((u) => <option key={u} value={u}>{u}</option>)}
          </select>
        )}

        {aoVivo && (
          <React.Fragment>
            <MultiSelect rotulo="Modalidades" opcoes={MODALIDADES_PNCP}
              selecionados={modVivo} aoMudar={setModVivo} larguraMenu="220px" />
            <MultiSelect rotulo="Esferas" opcoes={ESFERAS_PNCP}
              selecionados={esferasVivo} aoMudar={setEsferasVivo} />
            <select className="filtro-sel" value={statusVivo} onChange={(e) => setStatusVivo(e.target.value)} aria-label="Filtrar por status">
              <option value="recebendo_proposta">Recebendo propostas</option>
              <option value="encerradas">Encerradas</option>
              <option value="todos">Todas</option>
            </select>
            <select className="filtro-sel" value={tipoVivo} onChange={(e) => setTipoVivo(e.target.value)} aria-label="Tipo de documento">
              <option value="edital">Editais e avisos</option>
              <option value="ata">Atas</option>
              <option value="contrato">Contratos</option>
            </select>
            <select className="filtro-sel" value={ordemVivo} onChange={(e) => setOrdemVivo(e.target.value)} aria-label="Ordenação">
              <option value="-data">Mais recentes</option>
              <option value="data">Mais antigos</option>
              <option value="relevancia">Mais relevantes</option>
            </select>
            {/* P6: faixa de valor + ordenação CLIENT-SIDE (aplicam aos carregados) */}
            <div className="filtro-valor mono" role="group" aria-label="Faixa de valor (aplicada aos carregados)">
              <input type="text" inputMode="decimal" className="filtro-valor-input"
                value={valorMinVivo} onChange={(e) => setValorMinVivo(e.target.value)}
                placeholder="valor mín" aria-label="Valor mínimo (carregados)" />
              <span className="filtro-valor-sep" aria-hidden="true">–</span>
              <input type="text" inputMode="decimal" className="filtro-valor-input"
                value={valorMaxVivo} onChange={(e) => setValorMaxVivo(e.target.value)}
                placeholder="valor máx" aria-label="Valor máximo (carregados)" />
            </div>
            <select className="filtro-sel" value={ordemVivoLocal} onChange={(e) => setOrdemVivoLocal(e.target.value)} aria-label="Ordenar carregados">
              <option value="recente">Mais recentes</option>
              <option value="potencial">Potencial p/ você</option>
              <option value="valor">Maior valor</option>
            </select>
          </React.Fragment>
        )}

        {!aoVivo && (
          <select className="filtro-sel" value={modalidade} onChange={(e) => setModalidade(e.target.value)} aria-label="Filtrar por modalidade">
            <option value="todas">Modalidade · todas</option>
            {modalidades.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        )}
        {!aoVivo && (
          <button type="button" className={"filtro-status" + (recebendo ? " on" : "")} aria-pressed={recebendo} onClick={() => setRecebendo(!recebendo)}>
            <span className="led" aria-hidden="true"></span>Recebendo propostas
          </button>
        )}
        {!aoVivo && (
          <button type="button" className={"filtro-status" + (soNovos ? " on" : "")} aria-pressed={soNovos} onClick={() => setSoNovos(!soNovos)}>
            <span className="led" aria-hidden="true"></span>Só novos {qtdNovos > 0 && <em className="filtro-badge">{qtdNovos}</em>}
          </button>
        )}
        {/* P5: faixa de valor + ordenação (radar e Meus pregões) */}
        {!aoVivo && (
          <div className="filtro-valor mono" role="group" aria-label="Faixa de valor">
            <input type="text" inputMode="decimal" className="filtro-valor-input"
              value={valorMin} onChange={(e) => setValorMin(e.target.value)}
              placeholder="valor mín" aria-label="Valor mínimo" />
            <span className="filtro-valor-sep" aria-hidden="true">–</span>
            <input type="text" inputMode="decimal" className="filtro-valor-input"
              value={valorMax} onChange={(e) => setValorMax(e.target.value)}
              placeholder="valor máx" aria-label="Valor máximo" />
          </div>
        )}
        {!aoVivo && (
          <select className="filtro-sel" value={ordem} onChange={(e) => setOrdem(e.target.value)} aria-label="Ordenar pregões">
            <option value="recente">Mais recentes</option>
            <option value="potencial">Potencial p/ você</option>
            <option value="valor">Maior valor</option>
            <option value="prazo">Prazo</option>
          </select>
        )}
      </motion.div>
      )}

      {aoVivo && nTermos > 1 && (
        <motion.div className="vivo-multi-aviso silk" variants={entrada}>
          {nTermos} termos = {nTermos} consultas (1 req/s) — o total pode ter sobreposição.
        </motion.div>
      )}

      {apenasSalvos && vista === "quadro" ? (
        carregando ? (
          <EstadoCarregando entrada={entrada} />
        ) : erro ? (
          <EstadoErro entrada={entrada} mensagem={erro} recarregar={recarregar} />
        ) : (
          <Kanban pregoes={base} aoAbrir={aoAbrir} mudarPipeline={mudarPipelineEResumo} />
        )
      ) : aoVivo ? (
        <ListaVivo
          vivo={vivoExibido} entrada={entrada} importar={importar} importando={importando}
          nTermos={nTermos} aoAbrir={aoAbrir} recarregar={() => buscarVivo(1, false)}
          carregarMais={() => buscarVivo(vivo.pagina + 1, true)}
          margemAlvo={margemAlvo} avaliar={avaliar} avaliando={avaliando}
          aValiar={aValiar} segEstimados={segEstimados} filtroLocalAtivo={filtroVivoAtivo}
          nCarregados={vivo.itens.length}
        />
      ) : carregando ? (
        <EstadoCarregando entrada={entrada} />
      ) : erro ? (
        <EstadoErro entrada={entrada} mensagem={erro} recarregar={recarregar} />
      ) : (
        <div className="cards">
          <motion.div variants={entrada} className="silk" style={{ marginBottom: "2px" }}>
            {lista.length === 1 ? "1 oportunidade" : lista.length + " oportunidades"}
            {apenasSalvos ? " salvas" : " encontradas"}
          </motion.div>
          {lista.map((p) => (
            <CartaoPregao key={p.id} pregao={p} variants={entrada} margemAlvo={margemAlvo} onClick={() => aoAbrir(p.id)} />
          ))}
          {lista.length === 0 && (
            <motion.div variants={entrada} className="estado-vazio mod">
              <div className="estado-ico" aria-hidden="true">{Ico.radar}</div>
              <h3>Nenhum pregão com esses filtros</h3>
              <p>Tente afrouxar a UF, a modalidade ou a palavra-chave. As buscas salvas rodam 2×/dia e trazem novos pregões automaticamente.</p>
            </motion.div>
          )}
        </div>
      )}
    </motion.div>
  );
}

/* ---------- lista do modo "PNCP ao vivo" ---------- */
function ListaVivo({ vivo, entrada, importar, importando, nTermos, aoAbrir, recarregar,
  carregarMais, margemAlvo, avaliar, avaliando, aValiar, segEstimados,
  filtroLocalAtivo, nCarregados }) {
  const { itens, total, totalExato, fonte, carregando, erro } = vivo;
  // primeira carga (sem itens ainda) mostra skeleton; cargas seguintes mantêm a lista
  if (carregando && itens.length === 0) return <EstadoCarregando entrada={entrada} />;
  if (erro && itens.length === 0) return <EstadoErro entrada={entrada} mensagem={erro} recarregar={recarregar} />;

  // fonte EM MASSA (§4.4): valores oficiais já vêm embutidos em cada cartão
  const bulk = fonte === "consulta";
  // total_exato → "N oportunidades"; senão → "até N (somando M termos)"
  const contador = totalExato
    ? (bulk
        ? `${fmtInt(total)} ${total === 1 ? "oportunidade no PNCP · valor oficial embutido" : "oportunidades no PNCP · valores oficiais embutidos"}`
        : `${fmtInt(total)} ${total === 1 ? "oportunidade no PNCP" : "oportunidades no PNCP"}`)
    : `até ${fmtInt(total)} oportunidades (somando ${nTermos} termo${nTermos === 1 ? "" : "s"})`;

  return (
    <div className="cards">
      <motion.div variants={entrada} className="vivo-topo" style={{ marginBottom: "2px" }}>
        <span className="silk">{contador}</span>
        {/* P6: avaliar sob demanda — N = carregados ainda não avaliados (cap 40) */}
        <button type="button" className={"btn-avaliar" + (avaliando ? " rodando" : "")}
          disabled={avaliando || aValiar === 0} onClick={avaliar}
          aria-label={aValiar > 0 ? `Avaliar ${aValiar} pregões carregados` : "Tudo avaliado"}>
          {avaliando
            ? <React.Fragment><span className="spin" aria-hidden="true"></span> avaliando {aValiar} pregões — itens vêm da API do PNCP a 1 req/s…</React.Fragment>
            : aValiar > 0
              ? <React.Fragment>{Ico.raio} Avaliar resultados ({aValiar} · ~{segEstimados}s)</React.Fragment>
              : <React.Fragment>{Ico.check} tudo avaliado</React.Fragment>}
        </button>
      </motion.div>
      {bulk && (
        <motion.div variants={entrada} className="silk vivo-fonte-aviso">
          navegação sem palavra-chave usa a API de consulta — valor oficial instantâneo; digite termos para busca textual
        </motion.div>
      )}
      {filtroLocalAtivo && (
        <motion.div variants={entrada} className="silk vivo-filtro-aviso">
          filtros e ordem aplicam aos {fmtInt(nCarregados)} carregados/avaliados
        </motion.div>
      )}
      {erro && (
        <motion.div variants={entrada} className="vivo-erro-inline">
          {Ico.alerta} Não foi possível atualizar — {" "}
          <button type="button" className="vivo-retry" onClick={recarregar}>tentar de novo</button>
        </motion.div>
      )}
      {itens.map((p) => (
        <CartaoPregaoVivo key={p.numeroControle} pregao={p} margemAlvo={margemAlvo}
          variants={entrada} importar={importar} importando={importando} aoAbrir={aoAbrir} />
      ))}
      {itens.length === 0 && !carregando && (
        <motion.div variants={entrada} className="estado-vazio mod">
          <div className="estado-ico" aria-hidden="true">{Ico.radar}</div>
          <h3>Nenhum edital com esses filtros</h3>
          <p>Remova chips de palavra-chave para ver o total nacional, ou afrouxe UF, modalidade e esfera. Os dados vêm direto da busca oficial do PNCP.</p>
        </motion.div>
      )}
      {itens.length > 0 && itens.length < total && (
        <button type="button" className={"btn-rodar vivo-mais" + (carregando ? " rodando" : "")}
          disabled={carregando} onClick={carregarMais}>
          {carregando
            ? <React.Fragment><span className="spin" aria-hidden="true"></span> Carregando…</React.Fragment>
            : <React.Fragment>{Ico.raio} Carregar mais ({fmtInt(total - itens.length)} restantes)</React.Fragment>}
        </button>
      )}
    </div>
  );
}

export function CartaoPregaoVivo({ pregao, variants, importar, importando, aoAbrir, margemAlvo = 0.2 }) {
  const linhaSilk = [
    pregao.modalidade,
    pregao.municipio ? pregao.municipio + "/" + pregao.uf : pregao.uf,
    pregao.status,
  ].filter(Boolean).join(" · ");
  const noRadar = pregao.jaNoRadar;
  const importandoEste = importando === pregao.numeroControle;
  const abrir = () => { if (noRadar && pregao.pregaoId != null) aoAbrir(pregao.pregaoId); };
  // P6: avaliação sob demanda — valor real (Σ itens) e potencial aderente.
  // valor exibido: valorItens (avaliado) ▸ valorTotal do hit (estimado oficial).
  const temSomaItens = pregao.valorItens != null;
  const nAderentes = pregao.itensAderentes || 0;
  const potencial = nAderentes > 0 && pregao.receitaAderente != null
    ? pregao.receitaAderente * margemAlvo : null;
  return (
    <motion.div className="card-pregao mod card-vivo" variants={variants}>
      <span className="card-edital silk">
        {noRadar && <em className="card-noradar">no radar</em>}
        {pregao.naoAvaliavel && <em className="card-naoaval">não avaliável</em>}
        {linhaSilk}
      </span>
      <span className="card-titulo">{pregao.titulo}</span>
      <span className="card-orgao">{pregao.orgao}</span>
      {pregao.descricao && <span className="card-desc">{pregao.descricao}</span>}
      <span className="card-meta mono">
        <span><span className="k">{temSomaItens ? "Σ itens" : "Valor estimado"}</span>
          {temSomaItens ? fmtBRL(pregao.valorItens)
           : pregao.valorTotal != null ? fmtBRL(pregao.valorTotal) : "—"}</span>
        <span><span className="k">Propostas até</span>{pregao.prazo || "—"}</span>
        <span className="desktop-only"><span className="k">Itens</span>{pregao.itensTotal != null ? pregao.itensTotal : "—"}</span>
      </span>
      {potencial != null ? (
        <span className="card-potencial">
          {nAderentes} {nAderentes === 1 ? "item seu" : "itens seus"} · potencial{" "}
          {fmtBRL(potencial)} <em className="margem-pill sim">sim.</em>
        </span>
      ) : pregao.avaliado ? (
        <span className="card-potencial vazio silk">nenhum item do seu ramo</span>
      ) : null}
      <span className="card-vered">
        {noRadar ? (
          <button type="button" className="btn-rodar btn-vivo-abrir" onClick={abrir}>
            {Ico.radar} Abrir análise
          </button>
        ) : (
          <button type="button" className={"btn-rodar btn-vivo-add" + (importandoEste ? " rodando" : "")}
            disabled={importandoEste} onClick={() => importar(pregao)}>
            {importandoEste
              ? <React.Fragment><span className="spin" aria-hidden="true"></span> Adicionando…</React.Fragment>
              : <React.Fragment>{Ico.raio} Adicionar ao radar</React.Fragment>}
          </button>
        )}
      </span>
    </motion.div>
  );
}

export function CartaoPregao({ pregao, variants, onClick, margemAlvo = 0.2 }) {
  const ag = pregao.agregados || {};
  const veredito = normalizarVeredito(ag.veredito);
  const linhaSilk = [
    pregao.modalidade,
    pregao.municipio ? pregao.municipio + "/" + pregao.uf : pregao.uf,
    pregao.status,
  ].filter(Boolean).join(" · ");
  // P5: potencial aderente (cenário, nunca promessa). Com itens do meu ramo →
  // chip âmbar "N itens seus · potencial R$ X sim."; enriquecido mas sem item
  // do ramo → chip silk; sem itens ainda → nada.
  const nAderentes = pregao.itensAderentes || 0;
  const potencial = nAderentes > 0 && pregao.receitaAderente != null
    ? pregao.receitaAderente * margemAlvo : null;
  return (
    <motion.button type="button" className="card-pregao mod" variants={variants} onClick={onClick}
      aria-label={"Abrir análise de " + pregao.titulo + (veredito ? " — veredito prévio: " + VEREDITO_TXT[veredito] : "")}>
      <span className="card-edital silk">
        {pregao.novo && <em className="card-novo">novo</em>}
        {linhaSilk}
      </span>
      <span className="card-titulo">{pregao.titulo}</span>
      <span className="card-orgao">{pregao.orgao}</span>
      {pregao.descricao && <span className="card-desc">{pregao.descricao}</span>}
      <span className="card-meta mono">
        <span><span className="k">Valor estimado</span>
          {pregao.valorTotal != null ? fmtBRL(pregao.valorTotal)
           : pregao.valorItens != null ? fmtBRL(pregao.valorItens) + " (Σ itens)" : "—"}</span>
        <span><span className="k">Propostas até</span>{pregao.prazo || "—"}</span>
        <span><span className="k">Itens</span>{ag.itensTotal > 0 ? ag.itensTotal : "—"}</span>
        <span className="desktop-only"><span className="k">Cobertura</span>{ag.itensTotal > 0 ? ag.itensConfirmados + "/" + ag.itensTotal + " no catálogo" : "—"}</span>
      </span>
      {potencial != null ? (
        <span className="card-potencial">
          {nAderentes} {nAderentes === 1 ? "item seu" : "itens seus"} · potencial{" "}
          {fmtBRL(potencial)} <em className="margem-pill sim">sim.</em>
        </span>
      ) : ag.itensTotal > 0 && nAderentes === 0 ? (
        <span className="card-potencial vazio silk">nenhum item do seu ramo</span>
      ) : null}
      <span className="card-vered">
        {veredito
          ? <Etiqueta veredito={veredito} />
          : <span className="card-sync silk">{pregao.sincronizado ? "sem matches confirmados" : "abrir para analisar"}</span>}
        {!pregao.sincronizado && <span className="card-sync silk">sincronizar p/ habilitação</span>}
      </span>
    </motion.button>
  );
}

/* ---------- Buscas salvas (CRUD real + rodar agora) ---------- */
export function BuscasScreen({ buscas, erro, recarregar, rodar, criar, alternar }) {
  const { reduzido, estatico } = React.useContext(MotionCtx);
  const [rodando, setRodando] = React.useState(null);
  const [form, setForm] = React.useState({ nome: "", termos: "", ufs: "" });
  const [salvando, setSalvando] = React.useState(false);

  const carregando = buscas == null && !erro;

  const aoRodar = (id) => {
    if (rodando != null) return;
    setRodando(id);
    rodar(id).finally(() => setRodando(null));
  };

  const aoCriar = (e) => {
    e.preventDefault();
    if (!form.nome.trim() || !form.termos.trim() || salvando) return;
    setSalvando(true);
    criar({ nome: form.nome.trim(), termos: form.termos.trim(), ufs: form.ufs.trim() })
      .then(() => setForm({ nome: "", termos: "", ufs: "" }))
      .catch(() => {})
      .finally(() => setSalvando(false));
  };

  const entrada = reduzido
    ? { hidden: { opacity: 0 }, show: { opacity: 1, transition: { duration: 0.15 } } }
    : { hidden: { opacity: 0, y: 14 }, show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 320, damping: 28 } } };
  const pai = { hidden: {}, show: { transition: { staggerChildren: reduzido ? 0 : 0.05 } } };

  return (
    <motion.div className="screen-inner" variants={pai} initial={estatico ? false : "hidden"} animate="show">
      <motion.div variants={entrada}>
        <div className="silk">Monitoramento · 2×/dia</div>
        <h1 className="pg-titulo">Buscas salvas</h1>
        <p className="pg-sub">Cada busca roda automaticamente e marca os pregões novos. Rode na hora quando quiser.</p>
      </motion.div>

      <motion.div className="mod form-mod" variants={entrada}>
        <div className="silk">Nova busca</div>
        <form className="form-linhas" onSubmit={aoCriar}>
          <input className="form-input" value={form.nome} required
            onChange={(e) => setForm((f) => ({ ...f, nome: e.target.value }))}
            placeholder="Nome — ex.: Áudio & vídeo SP" aria-label="Nome da busca" />
          <input className="form-input longa" value={form.termos} required
            onChange={(e) => setForm((f) => ({ ...f, termos: e.target.value }))}
            placeholder="Termos separados por vírgula — ex.: áudio, microfone, caixa de som" aria-label="Termos da busca" />
          <input className="form-input curta" value={form.ufs}
            onChange={(e) => setForm((f) => ({ ...f, ufs: e.target.value.toUpperCase() }))}
            placeholder="UFs — ex.: SP,RJ" aria-label="UFs (vazio = todas)" />
          <button type="submit" className="btn-rodar" disabled={salvando}>
            {salvando
              ? <React.Fragment><span className="spin" aria-hidden="true"></span> Salvando…</React.Fragment>
              : <React.Fragment>{Ico.raio} Salvar busca</React.Fragment>}
          </button>
        </form>
      </motion.div>

      {carregando ? (
        <EstadoCarregando entrada={entrada} />
      ) : erro ? (
        <EstadoErro entrada={entrada} mensagem={erro} recarregar={recarregar} />
      ) : (
        <div className="cards">
          {(buscas || []).map((b) => (
            <motion.div key={b.id} className="busca-card mod" variants={entrada}>
              <div className="busca-card-main">
                <div className="busca-card-top">
                  <span className="busca-card-nome">{b.nome}</span>
                  <button type="button" className={"busca-card-status" + (b.ativo ? " on" : "")}
                    aria-pressed={b.ativo} onClick={() => alternar(b)}
                    title={b.ativo ? "Pausar monitoramento" : "Reativar monitoramento"}>
                    <span className="led" aria-hidden="true"></span>{b.ativo ? "Ativa" : "Pausada"}
                  </button>
                </div>
                <div className="busca-termos">
                  {b.termos.split(",").map((t) => <span key={t} className="termo-chip">{t.trim()}</span>)}
                </div>
                <div className="busca-meta mono">
                  <span><span className="k">UFs</span>{b.ufs || "todas"}</span>
                  <span><span className="k">Status</span>{b.status === "recebendo_proposta" ? "Recebendo propostas" : b.status || "todos"}</span>
                  <span><span className="k">Última execução</span>{b.ultimaExec || "nunca"}</span>
                  {b.novos > 0 && <span className="busca-novos">{b.novos} {b.novos === 1 ? "novo" : "novos"}</span>}
                </div>
              </div>
              <div className="busca-card-acao">
                <button type="button" className={"btn-rodar" + (rodando === b.id ? " rodando" : "")}
                  disabled={rodando != null} onClick={() => aoRodar(b.id)}>
                  {rodando === b.id
                    ? <React.Fragment><span className="spin" aria-hidden="true"></span> buscando e analisando itens (pode levar ~1 min)…</React.Fragment>
                    : <React.Fragment>{Ico.raio} Rodar agora</React.Fragment>}
                </button>
              </div>
            </motion.div>
          ))}
          {(buscas || []).length === 0 && (
            <motion.div variants={entrada} className="estado-vazio mod">
              <div className="estado-ico" aria-hidden="true">{Ico.raio}</div>
              <h3>Nenhuma busca salva</h3>
              <p>Crie a primeira busca acima — ela roda 2×/dia no PNCP e marca os pregões novos automaticamente.</p>
            </motion.div>
          )}
        </div>
      )}
    </motion.div>
  );
}

/* ---------- Meu catálogo (custos + fiscal) ---------- */
const FORM_PRODUTO_VAZIO = { nome: "", custo: "", codigo: "", categoria: "", ncm: "", unidade: "UN", csosn: "", cst: "" };

export function CatalogScreen({ catalogo, erro, recarregar, salvarCusto, criar }) {
  const { reduzido, estatico } = React.useContext(MotionCtx);
  const [form, setForm] = React.useState(FORM_PRODUTO_VAZIO);
  const [salvando, setSalvando] = React.useState(false);

  const carregando = catalogo == null && !erro;
  const itens = catalogo || [];
  const campo = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const aoCriar = (e) => {
    e.preventDefault();
    const custo = parseFloat(String(form.custo).replace(/\./g, "").replace(",", "."));
    if (!form.nome.trim() || isNaN(custo) || custo < 0 || salvando) return;
    setSalvando(true);
    criar({
      nome: form.nome.trim(),
      custo_unit: Math.round(custo * 100) / 100,
      codigo: form.codigo.trim() || null,
      categoria: form.categoria.trim() || null,
      ncm: form.ncm.trim() || null,
      unidade: form.unidade.trim() || "UN",
      csosn: form.csosn.trim() || null,
      cst: form.cst.trim() || null,
    })
      .then(() => setForm(FORM_PRODUTO_VAZIO))
      .catch(() => {})
      .finally(() => setSalvando(false));
  };

  return (
    <motion.div className="screen-inner"
      initial={estatico ? false : reduzido ? { opacity: 0 } : { opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reduzido ? { duration: 0.15 } : { type: "spring", stiffness: 300, damping: 30 }}>
      <div className="silk">Base de custos</div>
      <h1 className="pg-titulo">Meu catálogo</h1>
      <p className="pg-sub">Custos e dados fiscais usados para calcular margem, veredito e prontidão de NF-e. O custo é editável direto na tabela.</p>

      {carregando ? (
        <EstadoCarregando />
      ) : erro ? (
        <EstadoErro mensagem={erro} recarregar={recarregar} />
      ) : (
        <React.Fragment>
          <div className="mod tbl" style={{ overflow: "hidden" }}>
            <div className="cat-head">
              <div className="silk">Código</div>
              <div className="silk">Produto</div>
              <div className="silk">NCM</div>
              <div className="silk">Custo unit.</div>
            </div>
            {itens.map((c) => (
              <div className="cat-row" key={c.id}>
                <div className="cat-cod">{c.cod}</div>
                <div>{c.nome}{c.cat && <em className="cat-cat"> · {c.cat}</em>}</div>
                <div className="mono" style={{ color: c.ncm ? "var(--tinta-2)" : "var(--silk)", fontSize: "12.5px" }}>{c.ncm || "faltam dados"}</div>
                <div className="cat-custo">
                  <CostInput valor={c.custo} aoConfirmar={(v) => salvarCusto(c, v)}
                    rotulo={"Custo unitário de " + c.nome + " — editável"} />
                </div>
              </div>
            ))}
            {itens.length === 0 && (
              <div className="cat-row"><div></div><div style={{ color: "var(--silk)" }}>Catálogo vazio — adicione o primeiro produto abaixo.</div><div></div><div></div></div>
            )}
          </div>

          <div className="mod form-mod" style={{ marginTop: "14px" }}>
            <div className="silk">Adicionar produto</div>
            <form className="form-linhas" onSubmit={aoCriar}>
              <input className="form-input longa" value={form.nome} required onChange={campo("nome")}
                placeholder="Nome — ex.: Microfone sem fio duplo UHF" aria-label="Nome do produto" />
              <input className="form-input curta" value={form.custo} required inputMode="decimal" onChange={campo("custo")}
                placeholder="Custo — 690,00" aria-label="Custo unitário" />
              <input className="form-input curta" value={form.codigo} onChange={campo("codigo")}
                placeholder="Código" aria-label="Código interno" />
              <input className="form-input" value={form.categoria} onChange={campo("categoria")}
                placeholder="Categoria — ex.: Áudio › Microfones" aria-label="Categoria" />
              <input className="form-input curta" value={form.ncm} onChange={campo("ncm")}
                placeholder="NCM" aria-label="NCM" />
              <input className="form-input curta" value={form.unidade} onChange={campo("unidade")}
                placeholder="Unidade — UN" aria-label="Unidade" />
              <input className="form-input curta" value={form.csosn} onChange={campo("csosn")}
                placeholder="CSOSN" aria-label="CSOSN (Simples)" />
              <input className="form-input curta" value={form.cst} onChange={campo("cst")}
                placeholder="CST" aria-label="CST (Presumido)" />
              <button type="submit" className="btn-rodar" disabled={salvando}>
                {salvando
                  ? <React.Fragment><span className="spin" aria-hidden="true"></span> Salvando…</React.Fragment>
                  : <React.Fragment>{Ico.check} Adicionar</React.Fragment>}
              </button>
            </form>
          </div>
        </React.Fragment>
      )}
    </motion.div>
  );
}

/* ---------- estados de carregando / erro (agora derivados do fetch real) ---------- */
export function EstadoCarregando({ entrada }) {
  const Tag = entrada ? motion.div : "div";
  return (
    <Tag {...(entrada ? { variants: entrada } : {})} className="cards" aria-busy="true" aria-label="Carregando">
      {[0, 1, 2].map((i) => (
        <div key={i} className="card-pregao mod skel">
          <span className="skel-bar w30"></span>
          <span className="skel-bar w70 big"></span>
          <span className="skel-bar w50"></span>
          <span className="skel-bar w90"></span>
        </div>
      ))}
    </Tag>
  );
}

export function EstadoErro({ entrada, mensagem, recarregar }) {
  const Tag = entrada ? motion.div : "div";
  return (
    <Tag {...(entrada ? { variants: entrada } : {})} className="estado-vazio mod erro">
      <div className="estado-ico" aria-hidden="true">{Ico.alerta}</div>
      <h3>Não foi possível carregar</h3>
      <p>{mensagem && mensagem !== "Failed to fetch"
        ? mensagem
        : "A API não respondeu (backend fora do ar, rate limit ou instabilidade do PNCP). Tente novamente em instantes."}</p>
      <button type="button" className="btn-rodar" onClick={recarregar}>{Ico.raio} Tentar de novo</button>
    </Tag>
  );
}
