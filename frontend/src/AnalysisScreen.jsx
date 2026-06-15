// RADAR DE PREGÕES — Tela 2: Análise (abas Itens / Habilitação / Fiscal-NF-e)
// Recálculo client-side instantâneo (analisar/fiscalDoItem); o backend é a
// fonte persistente — a resposta de definirMatch traz os agregados oficiais.
import React from "react";
import { motion } from "framer-motion";
import {
  MotionCtx, Ico, fmtBRL, analisar, statusItem, fiscalDoItem, linkPncp,
  VEREDITO_TXT, Medidor, NumBRL, NumPct, CostInput, Resumo,
  cenarioTexto, fontePrecoTexto,
} from "./helpers.jsx";
import { STATUS_PIPELINE } from "./Kanban.jsx";
import { HabilitacaoTab, FiscalTab } from "./Tabs.jsx";
import { api } from "./api.js";
import DetailPanel from "./DetailPanel.jsx";
import { EstadoCarregando, EstadoErro } from "./FindScreen.jsx";

export const STATUS_TXT = {
  sinal: "Saudável", pico: "Atenção", clip: "Prejuízo",
  fora: "Sem match", sugerido: "Sugerido", sigiloso: "Sigiloso",
};

export default function AnalysisScreen({
  pregao, estado, setCusto, confirmarCusto, limparCusto, definirMargemAlvo,
  setLance, confirmarLance, limparLance, definirDesagio,
  setMatch, setHabil, voltar, scrollRef,
  meterVariant, config, setRegime, catalogo, catalogoPorCod,
  sincronizar, sincronizando, erroDetalhe, recarregarDetalhe,
  mudarPipeline, salvarPregao,
}) {
  const { reduzido, estatico } = React.useContext(MotionCtx);
  const carregandoItens = pregao.itens == null;
  // P4: deságio esperado da config (string do backend → número)
  const desagio = config && config.desagio_esperado != null
    ? parseFloat(config.desagio_esperado) || 0 : 0;
  const margemAlvo = config && config.margem_alvo != null
    ? parseFloat(config.margem_alvo) || 0 : 0;
  const a = analisar(pregao, estado, catalogoPorCod, false, desagio, margemAlvo);
  // manchete do hero = MISTURA (reais digitados + simulados no alvo) sempre que
  // houver item simulado; a simulação só cessa item a item, quando o usuário
  // digita o custo real (decisão do dono 12/06). Sempre rotulada.
  const temBlend = !!a.sim;
  const [aba, setAba] = React.useState("itens");
  const [itemAberto, setItemAberto] = React.useState(null);
  const linhaOrigem = React.useRef(null);
  const tablistRef = React.useRef(null);

  const fiscalItens = a.itens.map((it) => ({ it, f: it.produto || it.ncmPncp ? fiscalDoItem(it, pregao, config) : null }));
  const prontos = fiscalItens.filter((x) => x.f && x.f.pronto).length;
  const fiscalTotal = a.itens.length;
  const habil = pregao.habilitacao || [];
  const habilCarregada = pregao.habilitacao != null;
  const habilStatus = (h) => (estado.habilitacao && estado.habilitacao[h.id]) || h.status;
  const pendentesHabil = habil.filter((h) => habilStatus(h) !== "ok").length;

  const abrirItem = (n, el) => {
    linhaOrigem.current = el || null;
    setItemAberto(n);
  };
  const fecharItem = React.useCallback(() => {
    setItemAberto(null);
    if (linhaOrigem.current) linhaOrigem.current.focus({ preventScroll: true });
  }, []);

  React.useEffect(() => {
    if (itemAberto == null) return;
    const onKey = (e) => { if (e.key === "Escape") fecharItem(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [itemAberto, fecharItem]);

  /* parallax leve no cabeçalho */
  const cabRef = React.useRef(null);
  React.useEffect(() => {
    const sc = scrollRef.current, cab = cabRef.current;
    if (!sc || !cab || reduzido) return;
    let raf = null;
    const onScroll = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = null;
        const y = Math.min(sc.scrollTop, 480);
        cab.style.transform = `translateY(${y * 0.12}px)`;
        cab.style.opacity = String(Math.max(0, 1 - y / 560));
      });
    };
    sc.addEventListener("scroll", onScroll, { passive: true });
    return () => { sc.removeEventListener("scroll", onScroll); if (raf) cancelAnimationFrame(raf); };
  }, [scrollRef, reduzido]);

  const entrada = reduzido
    ? { hidden: { opacity: 0 }, show: { opacity: 1, transition: { duration: 0.15 } } }
    : { hidden: { opacity: 0, y: 16 }, show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 280, damping: 26 } } };
  const pai = { hidden: {}, show: { transition: { staggerChildren: reduzido ? 0 : 0.07, delayChildren: reduzido ? 0 : 0.04 } } };

  const ABAS = [
    { id: "itens", rotulo: "Itens & margem", contador: a.sugeridos > 0 ? a.sugeridos + " a casar" : null, tipo: a.sugeridos > 0 ? "pico" : null },
    { id: "habilitacao", rotulo: "Habilitação", contador: habil.length ? pendentesHabil + "/" + habil.length : "—", tipo: pendentesHabil > 0 ? "pico" : "sinal" },
    { id: "fiscal", rotulo: "Fiscal · NF-e", contador: prontos + "/" + fiscalTotal, tipo: prontos === fiscalTotal ? "sinal" : "pico" },
    { id: "resultados", rotulo: "Resultados", contador: null, tipo: null },
    { id: "capag", rotulo: "CAPAG", contador: null, tipo: null },
    { id: "historico", rotulo: "Histórico", contador: null, tipo: null },
    { id: "perguntar", rotulo: "Perguntar ao edital", contador: null, tipo: null },
  ];

  const linhaSilk = [
    pregao.modalidade,
    typeof pregao.amparo === "string" ? pregao.amparo : null,
    pregao.situacao || pregao.status,
  ].filter(Boolean).join(" · ");

  const conteudo = (
    <motion.div className="screen-inner" variants={pai} initial={estatico ? false : "hidden"} animate="show">
      <div ref={cabRef} style={{ willChange: "transform" }}>
        <motion.div variants={entrada}>
          <div className="cab-acoes">
            <button type="button" className="voltar" onClick={voltar}>{Ico.seta} Voltar</button>
            <a className="btn-relatorio" href={api.relatorioPdfUrl(pregao.id)}
              target="_blank" rel="noopener noreferrer"
              title="Baixar um PDF com o resumo do edital, veredito e itens">
              {Ico.externo} Gerar relatório
            </a>
          </div>
          <div className="cab-info">
            <div className="silk">{linhaSilk}</div>
            <h1>{pregao.titulo}</h1>
            <div className="cab-orgao">{pregao.orgao}{pregao.municipio ? " · " + pregao.municipio + "/" + pregao.uf : ""}</div>
            {pregao.unidadeCompradora && <div className="cab-unidade mono">Unidade compradora: {pregao.unidadeCompradora}</div>}
            {(pregao.prazo || pregao.inicioPropostas) && (
              <div className="cab-prazo">
                {pregao.inicioPropostas
                  ? <React.Fragment>Propostas: {pregao.inicioPropostas} → <strong>{pregao.prazo || "—"}</strong> (horário de Brasília)</React.Fragment>
                  : <React.Fragment>Fim do recebimento de propostas: <strong>{pregao.prazo}</strong></React.Fragment>}
              </div>
            )}
            <a className="link-pncp" href={pregao.linkPncp || linkPncp(pregao)} target="_blank" rel="noopener noreferrer">
              {Ico.externo} Ver no PNCP{pregao.numeroControle ? " · " + pregao.numeroControle : ""}
            </a>
            {pregao.descricao && <p className="cab-obj">{pregao.descricao}</p>}
          </div>
        </motion.div>

        {!carregandoItens && (
          <React.Fragment>
            <motion.section className="hero" variants={entrada} aria-label="Veredito de viabilidade">
              <div className="hero-top">
                <div>
                  <div className="silk">Lucro potencial estimado{temBlend ? " · com simulação" : ""}</div>
                  <div className={"hero-lucro" + (temBlend ? " hero-sim" : "")}>
                    {temBlend ? <NumBRL value={a.sim.lucroTotal} />
                     : a.veredito ? <NumBRL value={a.lucroTotal} />
                     : <span className="mono">—</span>}
                  </div>
                </div>
                <div>
                  <div className="silk">Margem média{temBlend ? " · com simulação" : ""}</div>
                  <div className={"hero-margem" + (temBlend ? " hero-sim" : "")}>
                    {temBlend ? <NumPct value={a.sim.margemAgregada} />
                     : a.veredito ? <NumPct value={a.margemAgregada} />
                     : <span className="mono">—</span>}
                  </div>
                </div>
                <div className="hero-veredito">
                  <div className="silk">Veredito{temBlend ? " · com simulação" : ""}</div>
                  {/* a manchete é a MISTURA: custos reais onde digitados + simulados
                      no alvo para o resto (assume-se o guia correto até ser editado);
                      a linha de cenário abaixo declara a composição — nada escondido */}
                  <div className={"hero-veredito-palavra " + (temBlend ? a.sim.veredito + " hero-sim" : a.veredito || "pendente")} aria-live="polite">
                    {temBlend ? VEREDITO_TXT[a.sim.veredito]
                     : a.veredito ? VEREDITO_TXT[a.veredito]
                     : "A casar"}
                  </div>
                </div>
              </div>
              {/* linha de cenário em LARGURA TOTAL (fora da coluna do veredito —
                  texto longo cobria o hero) */}
              <div className="hero-cenario silk" title="Base do preço usado na conta — o teto oficial do PNCP segue na tabela">
                cenário: {cenarioTexto(a.cenario)}
                {temBlend && a.cobertos > 0 &&
                  ` · ${a.cobertos} ${a.cobertos === 1 ? "custo real" : "custos reais"} + ${a.sim.itens} simulados no alvo de ${Math.round(a.sim.alvo)}% · só com os reais: ${fmtBRL(a.lucroTotal)}${a.veredito ? ` (${VEREDITO_TXT[a.veredito]})` : ""}`}
                {temBlend && a.cobertos === 0 &&
                  ` · SIMULAÇÃO: todos os custos assumidos no alvo de ${Math.round(a.sim.alvo)}% — digite custos reais para refinar`}
              </div>
              {/* sem análise o VU repousa no mínimo; com simulação aponta a margem da mistura */}
              <Medidor valor={temBlend ? a.sim.margemAgregada : a.veredito ? a.margemAgregada : -10} variante={meterVariant} delay={reduzido ? 0 : 0.35} />
              <div className="hero-regra">
                Regra: <strong>Vale</strong> se margem ≥ 20% e cobertura ≥ 60% e lucro ≥ R$ 1.000 · <strong>Não vale</strong> se margem &lt; 8% ou lucro &lt; R$ 300 · senão <strong>Talvez</strong>. O veredito nunca esconde a conta.
              </div>
            </motion.section>

            <motion.div className="resumo" variants={entrada}>
              <Resumo k="Valor total estimado"
                v={pregao.valorTotal != null ? fmtBRL(pregao.valorTotal)
                   : pregao.valorItens != null ? fmtBRL(pregao.valorItens) : "—"}
                sub={pregao.valorTotal == null && pregao.valorItens != null
                     ? "Σ dos itens do edital" : undefined} />
              {/* cobertura agora é por CUSTO (manual ou catálogo) — rótulo fiel */}
              <Resumo k="Cobertura de custos" v={a.cobertos + " de " + a.total} sub={a.sugeridos > 0 ? a.sugeridos + " sugeridos a confirmar" : "sem pendências"} />
              <Resumo k="Habilitação"
                v={habil.length ? pendentesHabil + " pendentes" : !habilCarregada ? "carregando…" : pregao.sincronizado ? "sem requisitos" : "não sincronizada"}
                sub={habil.length ? "de " + habil.length + " requisitos" : undefined} />
              <Resumo k="Prontidão NF-e" v={prontos + " de " + fiscalTotal + " prontos"} />
            </motion.div>

            <motion.section className="mod disputa-mod" variants={entrada} aria-label="Disputa">
              <div className="disputa-cab">
                <div className="silk">Disputa</div>
                {!pregao.salvo && (
                  <button type="button" className="btn-rodar disputa-salvar"
                    onClick={() => salvarPregao && salvarPregao(pregao.id, true)}>
                    {Ico.raio} Salvar no funil
                  </button>
                )}
              </div>
              {pregao.salvo ? (
                <div className="disputa-campos">
                  <label className="silk disputa-campo">
                    status
                    <select className="filtro-sel" value={pregao.statusPipeline || "cotacao"}
                      onChange={(e) => mudarPipeline(pregao.id, { status_pipeline: e.target.value })}>
                      {STATUS_PIPELINE.map((s) => (
                        <option key={s.id} value={s.id}>{s.rotulo}</option>
                      ))}
                    </select>
                  </label>
                  <label className="silk disputa-campo">
                    data da disputa
                    <input type="datetime-local" className="form-input mono"
                      value={pregao.dataDisputa ? pregao.dataDisputa.replace(" ", "T").slice(0, 16) : ""}
                      onChange={(e) => mudarPipeline(pregao.id, { data_disputa: e.target.value ? e.target.value.replace("T", " ") : null })} />
                  </label>
                  <label className="silk disputa-campo">
                    valor final (R$)
                    <input type="number" step="0.01" min="0" className="form-input mono"
                      defaultValue={pregao.valorFinal ?? ""}
                      key={"vf-" + (pregao.valorFinal ?? "")}
                      onBlur={(e) => mudarPipeline(pregao.id, {
                        valor_final: e.target.value === "" ? null : Number(e.target.value),
                      })} />
                  </label>
                </div>
              ) : (
                <p className="disputa-vazio silk">
                  Salve este pregão no funil para acompanhar status, data da disputa e valor final.
                </p>
              )}
            </motion.section>
          </React.Fragment>
        )}
      </div>

      {carregandoItens ? (
        erroDetalhe
          ? <EstadoErro entrada={entrada} mensagem={erroDetalhe} recarregar={recarregarDetalhe} />
          : <EstadoCarregando entrada={entrada} />
      ) : (
        <React.Fragment>
          {/* ABAS — padrão ARIA tablist + roving tabindex (←/→/Home/End) */}
          <motion.div
            className="abas" variants={entrada} role="tablist" aria-label="Seções da análise"
            ref={tablistRef}
            onKeyDown={(e) => {
              const i = ABAS.findIndex((x) => x.id === aba);
              if (i < 0) return;
              let prox = null;
              if (e.key === "ArrowRight") prox = (i + 1) % ABAS.length;
              else if (e.key === "ArrowLeft") prox = (i - 1 + ABAS.length) % ABAS.length;
              else if (e.key === "Home") prox = 0;
              else if (e.key === "End") prox = ABAS.length - 1;
              else return;
              e.preventDefault();
              setAba(ABAS[prox].id);
              const el = tablistRef.current && tablistRef.current.querySelector("#tab-" + ABAS[prox].id);
              if (el) el.focus();
            }}
          >
            {ABAS.map((ab) => (
              <button
                key={ab.id}
                type="button"
                role="tab"
                id={"tab-" + ab.id}
                aria-selected={aba === ab.id}
                aria-controls={"panel-" + ab.id}
                tabIndex={aba === ab.id ? 0 : -1}
                className={"aba" + (aba === ab.id ? " ativa" : "")}
                onClick={() => setAba(ab.id)}
              >
                {ab.rotulo}
                {ab.contador && <span className={"aba-cont" + (ab.tipo ? " " + ab.tipo : "")}>{ab.contador}</span>}
              </button>
            ))}
          </motion.div>

          <motion.div
            variants={entrada} key={aba} className="aba-painel"
            role="tabpanel" id={"panel-" + aba} aria-labelledby={"tab-" + aba} tabIndex={0}
          >
            {aba === "itens" && (
              <ItensTab a={a} pregao={pregao} abrir={abrirItem} setCusto={setCusto} confirmarCusto={confirmarCusto}
                limparCusto={limparCusto} definirMargemAlvo={definirMargemAlvo} config={config} desagio={desagio}
                setLance={setLance} confirmarLance={confirmarLance} limparLance={limparLance} definirDesagio={definirDesagio}
                setMatch={setMatch} catalogo={catalogo} estatico={estatico} reduzido={reduzido} itemAberto={itemAberto} />
            )}
            {aba === "habilitacao" && (
              <HabilitacaoTab pregao={pregao} habilStatus={habilStatus} setHabil={setHabil}
                sincronizar={sincronizar} sincronizando={sincronizando} />
            )}
            {aba === "fiscal" && (
              <FiscalTab fiscalItens={fiscalItens} prontos={prontos} total={fiscalTotal} config={config} setRegime={setRegime} pregao={pregao} />
            )}
            {aba === "resultados" && (
              <ResultadosTab pregao={pregao} />
            )}
            {aba === "capag" && (
              <CapagTab pregao={pregao} />
            )}
            {aba === "historico" && (
              <HistoricoTab pregao={pregao} />
            )}
            {aba === "perguntar" && (
              <PerguntarTab pregao={pregao} />
            )}
          </motion.div>
        </React.Fragment>
      )}
    </motion.div>
  );

  const aberto = itemAberto != null ? a.itens.find((i) => i.n === itemAberto) : null;

  return (
    <React.Fragment>
      <motion.div
        style={estatico ? { minHeight: "100%", opacity: aberto ? 0.65 : 1, transition: "opacity 0.15s ease" } : { transformOrigin: "50% 30%", minHeight: "100%" }}
        animate={estatico ? undefined : { scale: aberto ? 0.985 : 1, filter: aberto ? "blur(3px)" : "blur(0px)" }}
        transition={{ type: "spring", stiffness: 260, damping: 28 }}
      >
        {conteudo}
      </motion.div>
      <DetailPanel item={aberto} pregao={pregao} fechar={fecharItem} setCusto={setCusto} confirmarCusto={confirmarCusto} limparCusto={limparCusto}
        setLance={setLance} confirmarLance={confirmarLance} limparLance={limparLance} desagio={desagio} setMatch={setMatch} config={config} />
    </React.Fragment>
  );
}

// normalização leve para a busca nos itens (sem acento, caixa baixa) — espelha
// a filosofia do gate de citação / matching de município do backend.
function _normTxt(s) {
  if (!s) return "";
  return String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
}

/* ============ ABA ITENS ============ */
function ItensTab({ a, pregao, abrir, setCusto, confirmarCusto, limparCusto, definirMargemAlvo, config, desagio,
  setLance, confirmarLance, limparLance, definirDesagio, setMatch, catalogo, estatico, reduzido, itemAberto }) {
  const linha = reduzido
    ? { hidden: { opacity: 0 }, show: { opacity: 1, transition: { duration: 0.15 } } }
    : { hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 340, damping: 30 } } };
  const tbl = { hidden: {}, show: { transition: { staggerChildren: reduzido ? 0 : 0.04, delayChildren: reduzido ? 0 : 0.05 } } };

  // Recurso 4b: busca nos itens (frontend-only) — filtra por descrição/spec
  // normalizada. Zero backend.
  const [busca, setBusca] = React.useState("");
  const bNorm = _normTxt(busca);
  const itensFiltrados = bNorm
    ? a.itens.filter((it) => _normTxt((it.nome || "") + " " + (it.spec || "")).includes(bNorm))
    : a.itens;

  return (
    <div className="tbl-wrap">
      {a.sugeridos > 0 && (
        <div className="match-aviso">
          <span className="match-aviso-led" aria-hidden="true"></span>
          <span>
            <strong>{a.sugeridos} {a.sugeridos === 1 ? "item sugerido" : "itens sugeridos"}</strong> aguardando sua confirmação.
            Confirme ou digite o custo para entrar no cálculo de margem e veredito.
          </span>
        </div>
      )}
      <div className="tbl-titulo">
        <span className="silk">Itens do edital — teto × preço esperado × seu custo</span>
        <div className="tbl-controles">
          <BuscaItens valor={busca} setValor={setBusca} />
          <ExportarItens pregaoId={pregao.id} />
          <DesagioControle config={config} definirDesagio={definirDesagio} />
          <MargemAlvoControle config={config} definirMargemAlvo={definirMargemAlvo} />
        </div>
      </div>
      {bNorm && (
        <div className="busca-itens-info silk">
          {itensFiltrados.length} de {a.itens.length} itens com “{busca}”
        </div>
      )}
      <div className="mod tbl" role="table" aria-label="Itens do pregão">
        <div className="tbl-head" role="row">
          <div className="silk" role="columnheader">Nº</div>
          <div className="silk" role="columnheader">Descrição & match</div>
          <div className="silk" role="columnheader">Qtd</div>
          <div className="silk" role="columnheader">Teto × preço esperado</div>
          <div className="silk" role="columnheader">Seu lance previsto</div>
          <div className="silk" role="columnheader">Seu custo unit.</div>
          <div className="silk" role="columnheader">Margem %</div>
          <div className="silk" role="columnheader">Lucro do item</div>
          <div className="silk" role="columnheader">Status</div>
        </div>
        <motion.div variants={tbl} initial={estatico ? false : "hidden"} animate="show" role="rowgroup">
          {itensFiltrados.map((it) => (
            <LinhaItem key={it.n} item={it} variants={linha} ativa={itemAberto === it.n} abrir={abrir}
              setCusto={setCusto} confirmarCusto={confirmarCusto} limparCusto={limparCusto}
              setLance={setLance} confirmarLance={confirmarLance} limparLance={limparLance} desagio={desagio}
              setMatch={setMatch} catalogo={catalogo} />
          ))}
          {a.itens.length === 0 && (
            <div className="tbl-row fora" role="row">
              <div role="cell" style={{ gridColumn: "1 / -1", color: "var(--silk)", padding: "6px 0" }}>
                Nenhum item carregado ainda — sincronize o pregão para buscar os itens no PNCP.
              </div>
            </div>
          )}
          {a.itens.length > 0 && itensFiltrados.length === 0 && (
            <div className="tbl-row fora" role="row">
              <div role="cell" style={{ gridColumn: "1 / -1", color: "var(--silk)", padding: "6px 0" }}>
                Nenhum item corresponde a “{busca}”.
              </div>
            </div>
          )}
          <motion.div className="tbl-total" variants={linha} role="row">
            <div className="t-label" role="cell">
              Total · {a.cobertos} de {a.total} itens com custo
              {a.sim && <span className="total-sim silk"> · com simulação ({a.sim.itens} no alvo): {fmtBRL(a.sim.lucroTotal)}</span>}
            </div>
            <div className="t-resto" role="cell"></div>
            <div className="t-resto" role="cell"></div>
            <div className="t-resto" role="cell"></div>
            <div className="t-margem" role="cell">
              <span className="m-label mobile-only">Margem agregada</span>
              <span className={"margem-pill " + statusItem(a.margemAgregada)}><NumPct value={a.margemAgregada} /></span>
            </div>
            <div className="t-lucro" role="cell">
              <span className="m-label mobile-only">Lucro potencial</span>
              <NumBRL value={a.lucroTotal} />
            </div>
            <div className="t-resto" role="cell"></div>
          </motion.div>
        </motion.div>
      </div>
    </div>
  );
}

/* ---------- controle compacto de margem alvo (cabeçalho da tabela) ---------- */
function MargemAlvoControle({ config, definirMargemAlvo }) {
  const atual = config && config.margem_alvo != null ? Number(config.margem_alvo) : 0.2;
  const pct = Math.round((Number.isFinite(atual) ? atual : 0.2) * 100);
  const [rascunho, setRascunho] = React.useState(String(pct));
  React.useEffect(() => { setRascunho(String(pct)); }, [pct]);
  if (!definirMargemAlvo) return null;
  const aplicar = () => {
    const v = parseInt(rascunho, 10);
    if (!Number.isNaN(v)) definirMargemAlvo(Math.max(0, Math.min(95, v)) / 100);
    else setRascunho(String(pct));
  };
  return (
    <label className="margem-alvo silk" title="Guia da simulação dos itens sem custo — não entra no veredito">
      margem alvo
      <input type="text" inputMode="numeric" className="margem-alvo-input mono" value={rascunho}
        aria-label="Margem alvo da simulação (%)"
        onChange={(e) => setRascunho(e.target.value.replace(/[^\d]/g, ""))}
        onBlur={aplicar}
        onKeyDown={(e) => { if (e.key === "Enter") e.target.blur(); if (e.key === "Escape") { setRascunho(String(pct)); e.target.blur(); } e.stopPropagation(); }}
        onClick={(e) => e.stopPropagation()} />
      %
    </label>
  );
}

/* ---------- controle compacto de deságio esperado (P4 — espelho da margem alvo)
   muda a BASE do preço esperado de todos os itens (e os agregados) ---------- */
function DesagioControle({ config, definirDesagio }) {
  const atual = config && config.desagio_esperado != null ? parseFloat(config.desagio_esperado) : 0;
  const pct = Math.round((Number.isFinite(atual) ? atual : 0) * 100);
  const [rascunho, setRascunho] = React.useState(String(pct));
  React.useEffect(() => { setRascunho(String(pct)); }, [pct]);
  if (!definirDesagio) return null;
  const aplicar = () => {
    const v = parseInt(rascunho, 10);
    if (!Number.isNaN(v)) definirDesagio(Math.max(0, Math.min(90, v)) / 100);
    else setRascunho(String(pct));
  };
  return (
    <label className="margem-alvo silk" title="Preço esperado = teto menos este deságio (entra no veredito). O lance digitado por item vence o deságio.">
      deságio esperado
      <input type="text" inputMode="numeric" className="margem-alvo-input mono" value={rascunho}
        aria-label="Deságio esperado global (%)"
        onChange={(e) => setRascunho(e.target.value.replace(/[^\d]/g, ""))}
        onBlur={aplicar}
        onKeyDown={(e) => { if (e.key === "Enter") e.target.blur(); if (e.key === "Escape") { setRascunho(String(pct)); e.target.blur(); } e.stopPropagation(); }}
        onClick={(e) => e.stopPropagation()} />
      %
    </label>
  );
}

/* ---------- busca nos itens (Recurso 4b — frontend-only) ---------- */
function BuscaItens({ valor, setValor }) {
  return (
    <label className="busca-itens silk" title="Filtra os itens por descrição (sem acento)">
      buscar item
      <input type="search" className="busca-itens-input" value={valor}
        placeholder="ex.: microfone"
        aria-label="Buscar item por descrição"
        onChange={(e) => setValor(e.target.value)}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => { if (e.key === "Escape") setValor(""); e.stopPropagation(); }} />
    </label>
  );
}

/* ---------- exportar itens (Recurso 2 — CSV/XLSX, download direto) ---------- */
function ExportarItens({ pregaoId }) {
  const [aberto, setAberto] = React.useState(false);
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (!aberto) return;
    const onClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setAberto(false); };
    const onKey = (e) => { if (e.key === "Escape") setAberto(false); };
    window.addEventListener("mousedown", onClick);
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("mousedown", onClick); window.removeEventListener("keydown", onKey); };
  }, [aberto]);
  const baixar = (formato) => {
    // download direto: a resposta é binária com content-disposition (o navegador
    // salva o arquivo). window.open evita navegar a SPA para fora.
    window.open(api.exportarItensUrl(pregaoId, formato), "_blank", "noopener");
    setAberto(false);
  };
  return (
    <div className="export-itens" ref={ref}>
      <button type="button" className="export-btn" aria-haspopup="true" aria-expanded={aberto}
        onClick={(e) => { e.stopPropagation(); setAberto((v) => !v); }}>
        {Ico.externo} Exportar itens
      </button>
      {aberto && (
        <div className="export-menu" role="menu">
          <button type="button" role="menuitem" onClick={() => baixar("csv")}>CSV (.csv)</button>
          <button type="button" role="menuitem" onClick={() => baixar("xlsx")}>Excel (.xlsx)</button>
        </div>
      )}
    </div>
  );
}

/* ============ ABA HISTÓRICO — eventos do pregão (PNCP, sem ruído de sync) ============
   Carrega lazy: chama /pregoes/{id}/historico só quando a aba abre. Timeline com
   data, evento, responsável e justificativa. Vazio → "Sem eventos relevantes". */
function HistoricoTab({ pregao }) {
  const [estado, setEstado] = React.useState({ carregando: true, eventos: null, erro: null });

  React.useEffect(() => {
    let vivo = true;
    setEstado({ carregando: true, eventos: null, erro: null });
    api.historico(pregao.id)
      .then((d) => { if (vivo) setEstado({ carregando: false, eventos: (d && d.eventos) || [], erro: null }); })
      .catch((e) => { if (vivo) setEstado({ carregando: false, eventos: null, erro: (e && e.message) || "erro" }); });
    return () => { vivo = false; };
  }, [pregao.id]);

  if (estado.carregando) {
    return (
      <div className="hist-wrap" aria-busy="true">
        <div className="card-pregao mod skel">
          <span className="skel-bar w30"></span>
          <span className="skel-bar w70"></span>
          <span className="skel-bar w90"></span>
        </div>
      </div>
    );
  }

  if (estado.erro) {
    return (
      <div className="hist-wrap">
        <div className="estado-vazio mod">
          <h3>Não foi possível carregar o histórico</h3>
          <p>{estado.erro}</p>
        </div>
      </div>
    );
  }

  const eventos = estado.eventos || [];
  return (
    <div className="hist-wrap">
      <div className="tbl-titulo">
        <span className="silk">Histórico do pregão — marcos no PNCP (sem o ruído de sincronização)</span>
      </div>
      {eventos.length === 0 ? (
        <div className="capag-card mod capag-vazio">
          <div className="capag-vazio-tit silk">Sem eventos relevantes</div>
          <p className="capag-vazio-txt silk">
            O PNCP não registrou marcos para este pregão (inclusões, retificações,
            documentos). Eventos de sincronização automática são filtrados.
          </p>
        </div>
      ) : (
        <ol className="hist-timeline mod">
          {eventos.map((ev, i) => (
            <li className="hist-item" key={i}>
              <span className="hist-ponto" aria-hidden="true"></span>
              <div className="hist-conteudo">
                <div className="hist-linha-topo">
                  <strong className="hist-evento">{ev.evento || "Evento"}</strong>
                  <span className="hist-data mono silk">{dataHist(ev.data)}</span>
                </div>
                {ev.responsavel && <div className="hist-resp silk">por {ev.responsavel}</div>}
                {ev.justificativa && <div className="hist-just">{ev.justificativa}</div>}
                {ev.documento && <div className="hist-doc silk">{Ico.externo} {ev.documento}</div>}
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

// data ISO do histórico → pt-BR curto (dd/mm/aaaa hh:mm). Mantém o cru se inválida.
function dataHist(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${dd}/${mm}/${d.getFullYear()} ${hh}:${mi}`;
}

/* ============ ABA RESULTADOS — homologação do pregão (PNCP) ============
   Dados REAIS do PNCP item a item (operação LENTA — timeout 120s no api.js).
   Carrega lazy: só chama /pregoes/{id}/resultados quando a aba abre. Princípio 1
   (nunca inventar): item sem vencedor publicado mostra "—", nunca um chute. */

// deságio em fração 0..1 → "30%" (inteiro, espelha o estilo dos controles)
function fmtPctReal(frac) {
  if (frac == null || Number.isNaN(frac)) return "—";
  return Math.round(Number(frac) * 100) + "%";
}

function ResultadosTab({ pregao }) {
  const [estado, setEstado] = React.useState({ carregando: true, dados: null, erro: null });

  React.useEffect(() => {
    let vivo = true;
    setEstado({ carregando: true, dados: null, erro: null });
    api.resultadosPregao(pregao.id)
      .then((d) => { if (vivo) setEstado({ carregando: false, dados: d, erro: null }); })
      .catch((e) => { if (vivo) setEstado({ carregando: false, dados: null, erro: (e && e.message) || "erro" }); });
    return () => { vivo = false; };
  }, [pregao.id]);

  if (estado.carregando) {
    return (
      <div className="result-wrap" aria-busy="true">
        <div className="card-pregao mod skel">
          <span className="skel-bar w30"></span>
          <span className="skel-bar w70"></span>
          <span className="skel-bar w90"></span>
        </div>
        <p className="result-loading silk">Buscando resultados item a item no PNCP — pode demorar.</p>
      </div>
    );
  }

  if (estado.erro) {
    return (
      <div className="result-wrap">
        <div className="estado-vazio mod">
          <h3>Não foi possível carregar os resultados</h3>
          <p>{estado.erro}</p>
        </div>
      </div>
    );
  }

  const d = estado.dados || {};

  // ainda sem resultado publicado no PNCP — vazio honesto (princípio 1)
  if (!d.homologado) {
    return (
      <div className="result-wrap">
        <div className="tbl-titulo">
          <span className="silk">Resultados — homologação no PNCP</span>
        </div>
        <div className="capag-card mod capag-vazio">
          <div className="capag-vazio-tit silk">Sem resultado publicado</div>
          <p className="capag-vazio-txt silk">
            Este pregão ainda não tem resultado publicado no PNCP.
          </p>
        </div>
      </div>
    );
  }

  const itens = d.itens || [];
  const r = d.resumo || {};
  return (
    <div className="result-wrap">
      <div className="tbl-titulo">
        <span className="silk">Resultados — homologação no PNCP</span>
      </div>

      <div className="capag-card mod result-resumo">
        <div className="result-resumo-linha">
          Deságio real médio <strong>{fmtPctReal(r.desagio_medio_real)}</strong>
          {" · "}Economia <strong>{r.economia_total != null ? fmtBRL(r.economia_total) : "—"}</strong>
          {" · "}<strong>{r.n_homologados ?? 0}</strong> {r.n_homologados === 1 ? "item homologado" : "itens homologados"}
        </div>
        <div className="result-resumo-nota silk">Compare com seu deságio esperado (config).</div>
      </div>

      <div className="mod tbl result-tbl" role="table" aria-label="Resultados por item">
        <div className="tbl-head result-head" role="row">
          <div className="silk" role="columnheader">Nº</div>
          <div className="silk" role="columnheader">Descrição</div>
          <div className="silk" role="columnheader">Valor estimado (unit)</div>
          <div className="silk" role="columnheader">Vencedor</div>
          <div className="silk" role="columnheader">Homologado (unit)</div>
          <div className="silk" role="columnheader">Deságio real</div>
        </div>
        {itens.map((it) => (
          <div className="tbl-row result-row" role="row" key={it.numero}>
            <div className="c-num" role="cell">{String(it.numero).padStart(2, "0")}</div>
            <div className="c-desc" role="cell">
              <div className="d-nome">{it.descricao}</div>
            </div>
            <div role="cell">
              <span className="m-label mobile-only">Valor estimado (unit)</span>
              {it.valor_estimado_unit != null ? fmtBRL(it.valor_estimado_unit) : "—"}
            </div>
            <div role="cell">
              <span className="m-label mobile-only">Vencedor</span>
              {it.homologado && it.vencedor_nome ? (
                <span className="result-venc">
                  {it.vencedor_nome}
                  {it.porte && <span className="result-porte">{it.porte}</span>}
                </span>
              ) : (
                <span style={{ color: "var(--silk)" }}>—</span>
              )}
            </div>
            <div role="cell">
              <span className="m-label mobile-only">Homologado (unit)</span>
              {it.homologado && it.valor_homologado_unit != null
                ? fmtBRL(it.valor_homologado_unit)
                : <span style={{ color: "var(--silk)" }}>—</span>}
            </div>
            <div role="cell">
              <span className="m-label mobile-only">Deságio real</span>
              {it.homologado && it.desagio_real_pct != null
                ? <span className="result-desagio">{fmtPctReal(it.desagio_real_pct)}</span>
                : <span style={{ color: "var(--silk)" }}>—</span>}
            </div>
          </div>
        ))}
        {itens.length === 0 && (
          <div className="tbl-row fora" role="row">
            <div role="cell" style={{ gridColumn: "1 / -1", color: "var(--silk)", padding: "6px 0" }}>
              Nenhum item retornado para este pregão.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ============ ABA PERGUNTAR AO EDITAL — RAG Fase 1 (extrativo, 100% local) ============
   Honestidade (princípio 1 — nunca inventar): a resposta é o TEXTO LITERAL do
   edital (trechos verbatim com página + similaridade); o sistema nunca redige
   uma resposta. Fluxo: ragStatus na abertura → se não indexado, oferece indexar
   (operação lenta: roda o e5 local + extrai PDFs); se indexado, caixa de
   pergunta → ragPerguntar devolve trechos ou um motivo neutro. */
const RAG_EXEMPLOS = [
  "qual o prazo de entrega?",
  "exige atestado de capacidade técnica?",
  "qual a garantia?",
];

// similaridade 0..1 → "0,88" (vírgula, 2 casas) — espelha o NumPct do projeto
function fmtScore(s) {
  if (s == null || Number.isNaN(s)) return "—";
  return Number(s).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function PerguntarTab({ pregao }) {
  // status: null=carregando · {indexado:bool,...}
  const [status, setStatus] = React.useState(null);
  const [erroStatus, setErroStatus] = React.useState(null);
  const [indexando, setIndexando] = React.useState(false);
  const [erroIndex, setErroIndex] = React.useState(null);
  const [semArquivos, setSemArquivos] = React.useState(false);

  const [pergunta, setPergunta] = React.useState("");
  const [perguntando, setPerguntando] = React.useState(false);
  const [resposta, setResposta] = React.useState(null);   // {disponivel, motivo?, trechos?, sintese?, pergunta}
  const [erroPergunta, setErroPergunta] = React.useState(null);
  // Fase 2 (opt-in): resumir os trechos em prosa com o Claude CLI local. OFF por
  // padrão — quando ligado a espera é maior (CLI lento). `sintetizandoAtivo`
  // congela o estado do toggle DURANTE a requisição para o loading não trocar
  // de texto se o usuário mexer no checkbox no meio da espera.
  const [sintetizar, setSintetizar] = React.useState(false);
  const [sintetizandoAtivo, setSintetizandoAtivo] = React.useState(false);

  const carregarStatus = React.useCallback(() => {
    setStatus(null);
    setErroStatus(null);
    let vivo = true;
    api.ragStatus(pregao.id)
      .then((d) => { if (vivo) setStatus(d || { indexado: false }); })
      .catch((e) => { if (vivo) setErroStatus((e && e.message) || "erro"); });
    return () => { vivo = false; };
  }, [pregao.id]);

  React.useEffect(() => carregarStatus(), [carregarStatus]);

  const indexar = () => {
    setIndexando(true);
    setErroIndex(null);
    setSemArquivos(false);
    api.ragIndexar(pregao.id)
      .then((d) => {
        if (d && d.motivo === "sem_arquivos") {
          setSemArquivos(true);
        } else {
          // sucesso: refaz o status (mostra "{n_chunks} trechos de {n_paginas} páginas")
          carregarStatus();
        }
      })
      .catch((e) => setErroIndex((e && e.message) || "erro"))
      .finally(() => setIndexando(false));
  };

  const enviar = (texto) => {
    const q = (texto != null ? texto : pergunta).trim();
    if (!q || perguntando) return;
    if (texto != null) setPergunta(texto);
    const comSintese = sintetizar;
    setSintetizandoAtivo(comSintese);
    setPerguntando(true);
    setErroPergunta(null);
    setResposta(null);
    api.ragPerguntar(pregao.id, q, undefined, comSintese)
      .then((d) => {
        setResposta(d || { disponivel: false });
        // se o backend diz que nada está indexado, volta ao passo de indexar
        if (d && d.motivo === "nao_indexado") {
          setStatus({ indexado: false });
        }
      })
      .catch((e) => setErroPergunta((e && e.message) || "erro"))
      .finally(() => setPerguntando(false));
  };

  // ---- carregando o status inicial ----
  if (status == null && !erroStatus) {
    return (
      <div className="rag-wrap" aria-busy="true">
        <div className="card-pregao mod skel">
          <span className="skel-bar w30"></span>
          <span className="skel-bar w70"></span>
          <span className="skel-bar w90"></span>
        </div>
      </div>
    );
  }

  if (erroStatus) {
    return (
      <div className="rag-wrap">
        <div className="estado-vazio mod">
          <h3>Não foi possível verificar a indexação</h3>
          <p>{erroStatus}</p>
          <button type="button" className="rag-btn" onClick={carregarStatus}>Tentar de novo</button>
        </div>
      </div>
    );
  }

  const indexado = !!(status && status.indexado);

  return (
    <div className="rag-wrap">
      <div className="tbl-titulo">
        <span className="silk">Perguntar ao edital — respostas extrativas (trechos verbatim do PDF)</span>
      </div>

      {!indexado ? (
        /* ---- passo 1: não indexado → oferece indexar ---- */
        <div className="rag-card mod rag-indexar">
          <p className="rag-explica">
            Indexe os documentos deste edital para poder perguntar — roda 100%
            local, sem enviar nada para fora.
          </p>
          {semArquivos ? (
            <div className="rag-aviso rag-aviso-alerta">
              {Ico.alerta} Nenhum PDF de edital baixado. Faça a sincronização
              completa do pregão primeiro.
            </div>
          ) : indexando ? (
            <div className="rag-indexando">
              <span className="rag-spinner" aria-hidden="true"></span>
              <span>Indexando… roda o modelo local, pode levar um tempo.</span>
            </div>
          ) : (
            <button type="button" className="rag-btn rag-btn-primario" onClick={indexar}>
              {Ico.raio} Indexar documentos
            </button>
          )}
          {erroIndex && <div className="rag-aviso rag-aviso-erro">Falha ao indexar: {erroIndex}</div>}
        </div>
      ) : (
        /* ---- passo 2: indexado → perguntar ---- */
        <React.Fragment>
          <div className="rag-card mod">
            {(status.n_chunks != null || status.n_paginas != null) && (
              <div className="rag-meta silk">
                {Ico.check} {status.n_chunks ?? "?"} trechos indexados
                {status.n_paginas != null ? ` de ${status.n_paginas} páginas` : ""}
                {status.modelo ? ` · ${status.modelo}` : ""}
              </div>
            )}
            <div className="rag-form">
              <textarea
                className="rag-input"
                rows={2}
                value={pergunta}
                placeholder="ex.: qual o prazo de entrega?"
                aria-label="Sua pergunta sobre o edital"
                disabled={perguntando}
                onChange={(e) => setPergunta(e.target.value)}
                onKeyDown={(e) => {
                  // Enter envia; Shift+Enter quebra linha
                  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(); }
                }}
              />
              <button
                type="button"
                className="rag-btn rag-btn-primario"
                disabled={perguntando || !pergunta.trim()}
                onClick={() => enviar()}
              >
                {Ico.busca} {perguntando ? (sintetizandoAtivo ? "Resumindo…" : "Buscando…") : "Perguntar"}
              </button>
            </div>

            {/* Fase 2 (opt-in): resumir os trechos em prosa com a IA local */}
            <label className="rag-toggle">
              <input
                type="checkbox"
                checked={sintetizar}
                disabled={perguntando}
                onChange={(e) => setSintetizar(e.target.checked)}
              />
              <span className="rag-toggle-corpo">
                <span className="rag-toggle-rotulo">Resumir com IA local</span>
                <span className="rag-toggle-legenda silk">
                  roda o Claude local, sem custo de API — mais lento
                </span>
              </span>
            </label>

            <div className="rag-exemplos">
              <span className="silk rag-exemplos-rotulo">Exemplos:</span>
              {RAG_EXEMPLOS.map((ex) => (
                <button key={ex} type="button" className="rag-exemplo" disabled={perguntando}
                  onClick={() => enviar(ex)}>
                  {ex}
                </button>
              ))}
            </div>

            {/* loading dedicado quando a síntese está ligada (espera maior) */}
            {perguntando && sintetizandoAtivo && (
              <div className="rag-indexando rag-sintetizando">
                <span className="rag-spinner" aria-hidden="true"></span>
                <span>Resumindo com IA local… pode levar um tempo.</span>
              </div>
            )}
          </div>

          {erroPergunta && (
            <div className="rag-aviso rag-aviso-erro">Não foi possível perguntar: {erroPergunta}</div>
          )}

          {resposta && <RagResposta resposta={resposta} indexar={indexar} indexando={indexando} />}
        </React.Fragment>
      )}

      <p className="rag-rodape silk">
        Respostas extrativas — trechos verbatim do edital, com página e
        similaridade. Quando ligado, o resumo é gerado SÓ a partir dos trechos
        acima, nada é inventado. Confira sempre no PDF oficial.
      </p>
    </div>
  );
}

/* ---------- bloco de resposta do RAG (trechos OU motivo neutro) ---------- */
function RagResposta({ resposta, indexar, indexando }) {
  // motivo "nao_indexado" → o índice sumiu; oferece reindexar
  if (resposta.motivo === "nao_indexado" && !resposta.disponivel) {
    return (
      <div className="rag-card mod rag-resposta-neutra">
        <p>Os documentos ainda não estão indexados.</p>
        {indexando ? (
          <div className="rag-indexando">
            <span className="rag-spinner" aria-hidden="true"></span>
            <span>Indexando… roda o modelo local, pode levar um tempo.</span>
          </div>
        ) : (
          <button type="button" className="rag-btn rag-btn-primario" onClick={indexar}>
            {Ico.raio} Indexar documentos
          </button>
        )}
      </div>
    );
  }

  // motivo "nao_encontrado" → nada acima do limiar; bloco neutro, sem chute
  if (!resposta.disponivel || resposta.motivo === "nao_encontrado") {
    return (
      <div className="rag-card mod rag-resposta-neutra">
        <p>
          Não encontrei isso nos documentos deste edital (abaixo do limite de
          confiança). Pode estar escrito de outra forma — tente reformular a
          pergunta.
        </p>
      </div>
    );
  }

  const trechos = resposta.trechos || [];
  if (trechos.length === 0) {
    return (
      <div className="rag-card mod rag-resposta-neutra">
        <p>Nenhum trecho retornado para esta pergunta. Tente reformular.</p>
      </div>
    );
  }

  // maior score em destaque sutil (o backend devolve ordenado, mas calculamos
  // o topo aqui para não depender da ordem)
  const topo = trechos.reduce((m, t) => (t.score != null && (m == null || t.score > m) ? t.score : m), null);

  // Fase 2 (opt-in): bloco de síntese em prosa. Pode vir disponível (prosa
  // fundamentada) OU indisponível (motivo neutro). Em ambos os casos os trechos
  // verbatim seguem renderizados abaixo — a fonte/citação nunca some.
  const sintese = resposta.sintese || null;
  const citados = sintese && sintese.sintese_disponivel
    ? new Set((sintese.trechos_citados || []).filter((n) => Number.isInteger(n)))
    : null;

  return (
    <div className="rag-respostas">
      {sintese && <RagResumo sintese={sintese} />}

      <div className="rag-respostas-cab">
        Trechos do edital que respondem (a resposta é o texto literal do edital):
      </div>
      {trechos.map((t, i) => {
        const destaque = topo != null && t.score === topo;
        // índice 1-based para casar com trechos_citados da síntese
        const citado = citados ? citados.has(i + 1) : false;
        const cls = "rag-trecho mod"
          + (destaque ? " rag-trecho-topo" : "")
          + (citado ? " rag-trecho-citado" : "");
        return (
          <div key={i} className={cls}>
            {citado && <span className="rag-trecho-citado-tag">citado no resumo</span>}
            <p className="rag-trecho-texto">{t.texto}</p>
            <div className="rag-trecho-rodape">
              {t.pagina != null && <span className="rag-chip">pág. {t.pagina}</span>}
              {t.arquivo_titulo && <span className="rag-chip rag-chip-arq">{t.arquivo_titulo}</span>}
              {t.score != null && (
                <span className="rag-chip rag-chip-score">similaridade {fmtScore(t.score)}</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ---------- Fase 2: bloco de resumo em prosa (IA local) ----------
   Honestidade: o resumo é gerado SÓ a partir dos trechos abaixo. Quando o
   backend não consegue fundamentar (nao_encontrado/nao_fundamentado) ou a IA
   local não está acessível (erro_sintese), mostra um aviso neutro e os trechos
   extrativos seguem visíveis (degradação graciosa). */
function RagResumo({ sintese }) {
  if (sintese.sintese_disponivel) {
    const citados = (sintese.trechos_citados || []).filter((n) => Number.isInteger(n));
    return (
      <div className="rag-resumo">
        <div className="rag-resumo-cab">
          {Ico.raio}
          <span>
            Resumo — IA local
            {citados.length > 0
              ? ` (fundamentado nos trechos ${citados.join(", ")})`
              : " (fundamentado nos trechos abaixo)"}
          </span>
        </div>
        <p className="rag-resumo-texto">{sintese.resposta}</p>
      </div>
    );
  }

  // indisponível: mensagem neutra conforme o motivo (sempre seguida dos trechos)
  const erro = sintese.motivo === "erro_sintese";
  const msg = erro
    ? "Resumo indisponível (IA local não acessível agora). Mostrando os trechos."
    : "A IA local não encontrou uma resposta fundamentada nos trechos. Veja os trechos recuperados abaixo.";
  return (
    <div className={"rag-resumo rag-resumo-neutro" + (erro ? " rag-resumo-erro" : "")}>
      <p className="rag-resumo-neutro-texto">{msg}</p>
    </div>
  );
}

/* ---------- linha (com sub-barra de match quando sugerido/sem match) ---------- */
function LinhaItem({ item, variants, ativa, abrir, setCusto, confirmarCusto, limparCusto,
  setLance, confirmarLance, limparLance, desagio, setMatch, catalogo }) {
  const ref = React.useRef(null);
  const sigiloso = item.status === "sigiloso";
  const podeAbrir = () => abrir(item.n, ref.current);
  const cls = item.status;
  // tag "manual" + limpar (×) quando custo manual coexiste com produto confirmado
  const manualSobreCatalogo = item.custoManual != null && !!item.produto && item.status !== "sigiloso";
  // placeholder de simulação para item sem custo: "máx R$ X"
  const ph = item.custo == null && item.simulacaoCustoMax != null
    ? "máx " + fmtBRL(item.simulacaoCustoMax) : "";
  // P4: preço esperado ≠ teto quando há lance ou deságio aplicado
  const temPreco = item.preco != null;
  const precoDifereTeto = temPreco && (item.unit == null || Math.abs(item.preco - item.unit) > 0.005);

  return (
    <motion.div className="tbl-item" variants={variants}>
      <div
        ref={ref}
        className={"tbl-row mark-" + cls + (ativa ? " ativa" : "") + (sigiloso ? " fora" : "")}
        role="row"
      >
        <div className="c-num" role="cell">
          {/* gatilho real de abertura: botão nativo (Tab/Enter/Espaço de
              graça), estilizado como overlay transparente cobrindo a linha;
              os controles aninhados ficam acima e param a propagação */}
          <button type="button" className="tbl-row-abrir"
            aria-label={"Item " + item.n + " — " + item.nome}
            onClick={podeAbrir}></button>
          {String(item.n).padStart(2, "0")}
        </div>
        <div className="c-desc" role="cell">
          <div className="d-nome">{item.nome}</div>
          <div className="d-spec">{item.spec}</div>
        </div>
        <div className="c-qtd" role="cell"><span className="m-label mobile-only">Qtd</span>×{item.qtd}</div>
        {/* P4: teto oficial do PNCP SEMPRE visível; preço esperado em destaque
            quando difere (com a fonte: lance / −N%), o teto vira referência */}
        <div className="c-unit" role="cell">
          <span className="m-label mobile-only">Teto × preço esperado</span>
          {sigiloso ? (
            temPreco
              ? <span className="preco-esperado">{fmtBRL(item.preco)}<em className="preco-fonte">lance</em></span>
              : <span className="sigilo-tag">sigiloso</span>
          ) : precoDifereTeto ? (
            <React.Fragment>
              <span className="preco-esperado">{fmtBRL(item.preco)}
                <em className="preco-fonte">{fontePrecoTexto(item.fontePreco, desagio)}</em></span>
              <span className="teto-ref">teto {item.unit != null ? fmtBRL(item.unit) : "—"}</span>
            </React.Fragment>
          ) : (
            item.unit != null ? fmtBRL(item.unit) : "—"
          )}
        </div>
        {/* P4: seu lance previsto (editável) — vence o deságio global */}
        <div className="c-lance" role="cell">
          <span className="m-label mobile-only">Seu lance previsto</span>
          {sigiloso && item.preco == null ? (
            <div className="custo-cel">
              <CostInput valor={item.lancePrevisto} placeholder="lance"
                aoEditar={(v) => setLance(item.n, v)}
                aoConfirmar={(v) => confirmarLance(item, v)}
                rotulo={"Seu lance previsto do item " + item.n + " — editável"} />
            </div>
          ) : (
            <div className="custo-cel">
              {/* placeholder = preço esperado vigente (deságio/teto): já abre
                  num valor de disputa realista em vez da palavra "teto" */}
              <CostInput valor={item.lancePrevisto}
                placeholder={item.preco != null ? fmtBRL(item.preco) : item.unit != null ? "teto" : ""}
                aoEditar={(v) => setLance(item.n, v)}
                aoConfirmar={(v) => confirmarLance(item, v)}
                rotulo={"Seu lance previsto do item " + item.n + " — editável"} />
              {item.lancePrevisto != null && (
                <span className="custo-tags">
                  <button type="button" className="custo-limpar" title="Limpar lance (volta ao deságio/teto)"
                    aria-label={"Limpar lance previsto do item " + item.n}
                    onClick={(e) => { e.stopPropagation(); limparLance && limparLance(item); }}>{Ico.fechar}</button>
                </span>
              )}
            </div>
          )}
        </div>
        <div className="c-custo" role="cell">
          <span className="m-label mobile-only">Seu custo unit.</span>
          {sigiloso ? (
            <span style={{ paddingRight: "8px", color: "var(--silk)" }}>—</span>
          ) : (
            <div className="custo-cel">
              <CostInput valor={item.custo} placeholder={ph}
                aoEditar={(v) => setCusto(item.n, v)}
                aoConfirmar={(v) => confirmarCusto(item, v)}
                rotulo={"Seu custo unitário do item " + item.n + " — editável"} />
              {manualSobreCatalogo && (
                <span className="custo-tags">
                  <em className="custo-tag-manual">manual</em>
                  <button type="button" className="custo-limpar" title="Limpar custo manual (volta ao catálogo)"
                    aria-label={"Limpar custo manual do item " + item.n}
                    onClick={(e) => { e.stopPropagation(); limparCusto && limparCusto(item); }}>{Ico.fechar}</button>
                </span>
              )}
            </div>
          )}
        </div>
        <div className="c-margem" role="cell">
          <span className="m-label mobile-only">Margem</span>
          {/* item com custo real mostra margem; sem custo mostra a SIMULADA
              (custo assumido no alvo), sempre com a tag "sim." */}
          {item.coberto && item.margemPct != null
            ? <span className={"margem-pill " + item.status}><NumPct value={item.margemPct} /></span>
            : item.simulado
              ? <span className="margem-pill sim" title={"Simulação: custo assumido em " + fmtBRL(item.custoSim)}><NumPct value={item.margemSim} /> <em>sim.</em></span>
              : <span style={{ color: "var(--silk)" }}>—</span>}
        </div>
        <div className="c-lucro" role="cell">
          <span className="m-label mobile-only">Lucro do item</span>
          {sigiloso && item.lucro == null && item.lucroSim == null
            ? <span style={{ color: "var(--silk)" }}>valor sigiloso</span>
            : item.lucro != null
              ? <span style={item.coberto ? undefined : { color: "var(--silk)" }}><NumBRL value={item.lucro} /></span>
              : item.simulado
                ? <span className="lucro-sim" title="Simulação — custo assumido na margem alvo"><NumBRL value={item.lucroSim} /> <em>sim.</em></span>
                : <span style={{ color: "var(--silk)" }}>—</span>}
        </div>
        <div className="c-status" role="cell">
          <span className={"st-led " + (item.coberto ? item.status : item.status === "sugerido" ? "pico" : "off")} aria-hidden="true"></span>
          <span className="st-txt">{STATUS_TXT[item.status]}</span>
        </div>
      </div>

      {/* sub-barra de matching (human-in-the-loop) */}
      {!sigiloso && (item.status === "sugerido" || item.status === "fora") && (
        <MatchBar item={item} setMatch={setMatch} catalogo={catalogo} />
      )}
    </motion.div>
  );
}

/* ---------- barra de confirmação de match ---------- */
function MatchBar({ item, setMatch, catalogo }) {
  const [trocando, setTrocando] = React.useState(false);
  const cat = catalogo || [];
  const m = item.matchAtual;

  if (item.status === "fora" && !m) {
    return (
      <div className="match-bar sem">
        <span className="match-ico" aria-hidden="true">{Ico.link}</span>
        <span className="match-txt">Nenhum produto do catálogo casou automaticamente.</span>
        {!trocando ? (
          <button type="button" className="match-btn neutro" onClick={() => setTrocando(true)}>Casar manualmente</button>
        ) : (
          <SeletorProduto cat={cat} onPick={(cod) => { setMatch(item, { cod, score: null, confirmado: true }); setTrocando(false); }} onCancel={() => setTrocando(false)} />
        )}
      </div>
    );
  }
  if (!m) return null;

  return (
    <div className="match-bar sugerido">
      <span className="match-ico" aria-hidden="true">{Ico.link}</span>
      <span className="match-txt">
        Sugestão: <strong>{item.produto ? item.produto.nome : m.cod}</strong>
        {m.score != null && <span className="match-score">similaridade {(m.score * 100).toFixed(0)}%</span>}
      </span>
      {!trocando ? (
        <div className="match-acoes">
          <button type="button" className="match-btn ok" onClick={() => setMatch(item, { ...m, confirmado: true })}>{Ico.check} Confirmar</button>
          <button type="button" className="match-btn trocar" onClick={() => setTrocando(true)}>Trocar</button>
          <button type="button" className="match-btn nao" onClick={() => setMatch(item, null)}>{Ico.fechar} Recusar</button>
        </div>
      ) : (
        <SeletorProduto cat={cat} atual={m.cod} onPick={(cod) => { setMatch(item, { cod, score: null, confirmado: true }); setTrocando(false); }} onCancel={() => setTrocando(false)} />
      )}
    </div>
  );
}

/* ============ ABA CAPAG — risco de pagamento do comprador ============
   Dados REAIS do Tesouro Nacional / SICONFI (nunca inventa nota — princípio 1).
   Carrega lazy: só chama /pregoes/{id}/capag quando a aba abre. Cor por nota:
   A=--sinal (verde), B=--pico (âmbar), C/D=--clip (vermelho). */
const CAPAG_COR_VAR = { ok: "var(--sinal)", atencao: "var(--pico)", ruim: "var(--clip)" };

function CapagTab({ pregao }) {
  const [estado, setEstado] = React.useState({ carregando: true, dados: null, erro: null });

  React.useEffect(() => {
    let vivo = true;
    setEstado({ carregando: true, dados: null, erro: null });
    api.capag(pregao.id)
      .then((d) => { if (vivo) setEstado({ carregando: false, dados: d, erro: null }); })
      .catch((e) => { if (vivo) setEstado({ carregando: false, dados: null, erro: (e && e.message) || "erro" }); });
    return () => { vivo = false; };
  }, [pregao.id]);

  if (estado.carregando) {
    return (
      <div className="capag-wrap" aria-busy="true">
        <div className="card-pregao mod skel">
          <span className="skel-bar w30"></span>
          <span className="skel-bar w70 big"></span>
          <span className="skel-bar w90"></span>
        </div>
      </div>
    );
  }

  if (estado.erro) {
    return (
      <div className="capag-wrap">
        <div className="estado-vazio mod">
          <h3>Não foi possível carregar a CAPAG</h3>
          <p>{estado.erro}</p>
        </div>
      </div>
    );
  }

  const d = estado.dados || {};

  // Federal: bloco honesto — a CAPAG só avalia municípios e estados.
  if (!d.disponivel && d.motivo === "federal") {
    return (
      <div className="capag-wrap">
        <div className="tbl-titulo">
          <span className="silk">CAPAG — capacidade de pagamento do comprador</span>
        </div>
        <div className="capag-card mod capag-federal">
          <div className="capag-federal-tit">Órgão federal — pagamento pela União (risco baixo)</div>
          <p className="capag-federal-txt">
            A CAPAG do Tesouro avalia apenas municípios e estados. Entes
            federais (União, autarquias, institutos e universidades federais)
            não recebem nota — o pagamento corre pela União, de risco
            historicamente baixo.
          </p>
          <span className="capag-fonte silk">{Ico.escudo} {d.fonte || "Tesouro Nacional / SICONFI"}</span>
        </div>
      </div>
    );
  }

  // Sem dados: cinza, honesto — nunca um chute.
  if (!d.disponivel) {
    return (
      <div className="capag-wrap">
        <div className="tbl-titulo">
          <span className="silk">CAPAG — capacidade de pagamento do comprador</span>
        </div>
        <div className="capag-card mod capag-vazio">
          <div className="capag-vazio-tit silk">CAPAG não disponível para este órgão</div>
          <p className="capag-vazio-txt silk">
            A CAPAG (Tesouro Nacional) avalia prefeituras e governos estaduais
            por CNPJ; sub-órgãos com CNPJ próprio podem não ter nota. Nada foi
            estimado — sem dado, sem nota.
          </p>
          <span className="capag-fonte silk">{d.fonte || "Tesouro Nacional / SICONFI"}</span>
        </div>
      </div>
    );
  }

  // Disponível: nota grande colorida + 3 indicadores + ICF + selo de fonte.
  const cor = CAPAG_COR_VAR[d.cor] || "var(--silk)";
  return (
    <div className="capag-wrap">
      <div className="tbl-titulo">
        <span className="silk">CAPAG — capacidade de pagamento do comprador</span>
      </div>

      <div className="capag-card mod">
        <div className="capag-topo">
          <div className="capag-nota-bloco">
            <div className="silk">Nota CAPAG</div>
            <div className="capag-nota" style={{ color: cor }}>{d.nota}</div>
          </div>
          <div className="capag-ente">
            <div className="capag-ente-nome">{d.ente || d.municipio || "—"}{d.uf ? " / " + d.uf : ""}</div>
            <div className="silk">
              {d.esfera === "E" ? "Estado" : "Município"}
              {d.icf ? " · ranking ICF " + d.icf : ""}
            </div>
          </div>
        </div>

        <div className="capag-inds">
          {(d.indicadores || []).map((ind, i) => (
            <div className="capag-ind" key={i}>
              <div className="silk capag-ind-rotulo">{ind.rotulo}</div>
              <div className="capag-ind-linha">
                <span className="capag-ind-nota" style={{ color: CAPAG_COR_VAR[corDaNota(ind.nota)] || "var(--silk)" }}>
                  {ind.nota || "—"}
                </span>
                <span className="capag-ind-pct mono">
                  {ind.valor_pct != null ? ind.valor_pct.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + "%" : "—"}
                </span>
              </div>
            </div>
          ))}
        </div>

        <div className="capag-rodape">
          <span className="capag-fonte silk">{Ico.escudo} Fonte: {d.fonte || "Tesouro Nacional / SICONFI"}{d.origem ? " · " + d.origem : ""}</span>
        </div>
      </div>
    </div>
  );
}

// cor da nota de um indicador (espelha o helper do backend: A→ok, B→atenção, C/D→ruim)
function corDaNota(nota) {
  if (!nota) return null;
  const n = String(nota).trim().toUpperCase()[0];
  if (n === "A") return "ok";
  if (n === "B") return "atencao";
  if (n === "C" || n === "D") return "ruim";
  return null;
}

function SeletorProduto({ cat, atual, onPick, onCancel }) {
  const [sel, setSel] = React.useState(atual || "");
  return (
    <div className="match-seletor">
      <select className="filtro-sel" value={sel} onChange={(e) => setSel(e.target.value)} aria-label="Escolher produto do catálogo">
        <option value="">Escolher produto…</option>
        {cat.map((c) => <option key={c.cod} value={c.cod}>{c.cod} · {c.nome}</option>)}
      </select>
      <button type="button" className="match-btn ok" disabled={!sel} onClick={() => sel && onPick(sel)}>{Ico.check} Casar</button>
      <button type="button" className="match-btn neutro" onClick={onCancel}>Cancelar</button>
    </div>
  );
}
