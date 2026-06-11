// RADAR DE PREGÕES — Tela 2: Análise (abas Itens / Habilitação / Fiscal-NF-e)
// Recálculo client-side instantâneo (analisar/fiscalDoItem); o backend é a
// fonte persistente — a resposta de definirMatch traz os agregados oficiais.
import React from "react";
import { motion } from "framer-motion";
import {
  MotionCtx, Ico, fmtBRL, analisar, statusItem, fiscalDoItem, linkPncp,
  VEREDITO_TXT, Medidor, NumBRL, NumPct, CostInput, Resumo,
} from "./helpers.jsx";
import { STATUS_PIPELINE } from "./Kanban.jsx";
import { HabilitacaoTab, FiscalTab } from "./Tabs.jsx";
import DetailPanel from "./DetailPanel.jsx";
import { EstadoCarregando, EstadoErro } from "./FindScreen.jsx";

export const STATUS_TXT = {
  sinal: "Saudável", pico: "Atenção", clip: "Prejuízo",
  fora: "Sem match", sugerido: "Sugerido", sigiloso: "Sigiloso",
};

export default function AnalysisScreen({
  pregao, estado, setCusto, confirmarCusto, setMatch, setHabil, voltar, scrollRef,
  meterVariant, config, setRegime, catalogo, catalogoPorCod,
  sincronizar, sincronizando, erroDetalhe, recarregarDetalhe,
  mudarPipeline, salvarPregao,
}) {
  const { reduzido, estatico } = React.useContext(MotionCtx);
  const carregandoItens = pregao.itens == null;
  const a = analisar(pregao, estado, catalogoPorCod);
  const [aba, setAba] = React.useState("itens");
  const [itemAberto, setItemAberto] = React.useState(null);
  const linhaOrigem = React.useRef(null);

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
          <button type="button" className="voltar" onClick={voltar}>{Ico.seta} Voltar</button>
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
                  <div className="silk">Lucro potencial estimado</div>
                  <div className="hero-lucro">{a.veredito ? <NumBRL value={a.lucroTotal} /> : <span className="mono">—</span>}</div>
                </div>
                <div>
                  <div className="silk">Margem média</div>
                  <div className="hero-margem">{a.veredito ? <NumPct value={a.margemAgregada} /> : <span className="mono">—</span>}</div>
                </div>
                <div className="hero-veredito">
                  <div className="silk">Veredito</div>
                  {/* sem item confirmado não há veredito — mostrar chute é proibido */}
                  <div className={"hero-veredito-palavra " + (a.veredito || "pendente")} aria-live="polite">
                    {a.veredito ? VEREDITO_TXT[a.veredito] : "A casar"}
                  </div>
                </div>
              </div>
              {/* sem análise o VU repousa no mínimo, como aparelho desligado */}
              <Medidor valor={a.veredito ? a.margemAgregada : -10} variante={meterVariant} delay={reduzido ? 0 : 0.35} />
              <div className="hero-regra">
                Regra: <strong>Vale</strong> se margem ≥ 20% e cobertura ≥ 60% e lucro ≥ R$ 1.000 · <strong>Não vale</strong> se margem &lt; 8% ou lucro &lt; R$ 300 · senão <strong>Talvez</strong>. O veredito nunca esconde a conta.
              </div>
            </motion.section>

            <motion.div className="resumo" variants={entrada}>
              <Resumo k="Valor total estimado" v={pregao.valorTotal != null ? fmtBRL(pregao.valorTotal) : "—"} />
              <Resumo k="Cobertura do catálogo" v={a.cobertos + " de " + a.total} sub={a.sugeridos > 0 ? a.sugeridos + " sugeridos a confirmar" : "sem pendências"} />
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
          {/* ABAS */}
          <motion.div className="abas" variants={entrada} role="tablist" aria-label="Seções da análise">
            {ABAS.map((ab) => (
              <button
                key={ab.id}
                type="button"
                role="tab"
                aria-selected={aba === ab.id}
                className={"aba" + (aba === ab.id ? " ativa" : "")}
                onClick={() => setAba(ab.id)}
              >
                {ab.rotulo}
                {ab.contador && <span className={"aba-cont" + (ab.tipo ? " " + ab.tipo : "")}>{ab.contador}</span>}
              </button>
            ))}
          </motion.div>

          <motion.div variants={entrada} key={aba} className="aba-painel">
            {aba === "itens" && (
              <ItensTab a={a} pregao={pregao} abrir={abrirItem} setCusto={setCusto} confirmarCusto={confirmarCusto}
                setMatch={setMatch} catalogo={catalogo} estatico={estatico} reduzido={reduzido} itemAberto={itemAberto} />
            )}
            {aba === "habilitacao" && (
              <HabilitacaoTab pregao={pregao} habilStatus={habilStatus} setHabil={setHabil}
                sincronizar={sincronizar} sincronizando={sincronizando} />
            )}
            {aba === "fiscal" && (
              <FiscalTab fiscalItens={fiscalItens} prontos={prontos} total={fiscalTotal} config={config} setRegime={setRegime} pregao={pregao} />
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
      <DetailPanel item={aberto} pregao={pregao} fechar={fecharItem} setCusto={setCusto} confirmarCusto={confirmarCusto} setMatch={setMatch} config={config} />
    </React.Fragment>
  );
}

/* ============ ABA ITENS ============ */
function ItensTab({ a, pregao, abrir, setCusto, confirmarCusto, setMatch, catalogo, estatico, reduzido, itemAberto }) {
  const linha = reduzido
    ? { hidden: { opacity: 0 }, show: { opacity: 1, transition: { duration: 0.15 } } }
    : { hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 340, damping: 30 } } };
  const tbl = { hidden: {}, show: { transition: { staggerChildren: reduzido ? 0 : 0.04, delayChildren: reduzido ? 0 : 0.05 } } };

  return (
    <div className="tbl-wrap">
      {a.sugeridos > 0 && (
        <div className="match-aviso">
          <span className="match-aviso-led" aria-hidden="true"></span>
          <span>
            <strong>{a.sugeridos} {a.sugeridos === 1 ? "item sugerido" : "itens sugeridos"}</strong> aguardando sua confirmação.
            Só itens confirmados entram no cálculo de margem e veredito.
          </span>
        </div>
      )}
      <div className="tbl-titulo">
        <span className="silk">Itens do edital — estimado × seu custo</span>
        <span className="silk desktop-only">Clique no item para o detalhe</span>
      </div>
      <div className="mod tbl" role="table" aria-label="Itens do pregão">
        <div className="tbl-head" role="row">
          <div className="silk" role="columnheader">Nº</div>
          <div className="silk" role="columnheader">Descrição & match</div>
          <div className="silk" role="columnheader">Qtd</div>
          <div className="silk" role="columnheader">Valor unit. estimado</div>
          <div className="silk" role="columnheader">Seu custo unit.</div>
          <div className="silk" role="columnheader">Margem %</div>
          <div className="silk" role="columnheader">Lucro do item</div>
          <div className="silk" role="columnheader">Status</div>
        </div>
        <motion.div variants={tbl} initial={estatico ? false : "hidden"} animate="show" role="rowgroup">
          {a.itens.map((it) => (
            <LinhaItem key={it.n} item={it} variants={linha} ativa={itemAberto === it.n} abrir={abrir}
              setCusto={setCusto} confirmarCusto={confirmarCusto} setMatch={setMatch} catalogo={catalogo} />
          ))}
          {a.itens.length === 0 && (
            <div className="tbl-row fora" role="row">
              <div role="cell" style={{ gridColumn: "1 / -1", color: "var(--silk)", padding: "6px 0" }}>
                Nenhum item carregado ainda — sincronize o pregão para buscar os itens no PNCP.
              </div>
            </div>
          )}
          <motion.div className="tbl-total" variants={linha} role="row">
            <div className="t-label" role="cell">Total · {a.cobertos} de {a.total} itens confirmados</div>
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

/* ---------- linha (com sub-barra de match quando sugerido/sem match) ---------- */
function LinhaItem({ item, variants, ativa, abrir, setCusto, confirmarCusto, setMatch, catalogo }) {
  const ref = React.useRef(null);
  const sigiloso = item.status === "sigiloso";
  const podeAbrir = () => abrir(item.n, ref.current);
  const cls = item.status;

  return (
    <motion.div className="tbl-item" variants={variants}>
      <div
        ref={ref}
        className={"tbl-row mark-" + cls + (ativa ? " ativa" : "") + (sigiloso ? " fora" : "")}
        role="row"
        tabIndex={0}
        aria-label={"Item " + item.n + " — " + item.nome}
        onClick={(e) => { if (e.target.closest("input,button,select")) return; podeAbrir(); }}
        onKeyDown={(e) => { if ((e.key === "Enter" || e.key === " ") && !e.target.closest("input,button,select")) { e.preventDefault(); podeAbrir(); } }}
      >
        <div className="c-num" role="cell">{String(item.n).padStart(2, "0")}</div>
        <div className="c-desc" role="cell">
          <div className="d-nome">{item.nome}</div>
          <div className="d-spec">{item.spec}</div>
        </div>
        <div className="c-qtd" role="cell"><span className="m-label mobile-only">Qtd</span>×{item.qtd}</div>
        <div className="c-unit" role="cell">
          <span className="m-label mobile-only">Valor unit. estimado</span>
          {sigiloso ? <span className="sigilo-tag">sigiloso</span> : item.unit != null ? fmtBRL(item.unit) : "—"}
        </div>
        <div className="c-custo" role="cell">
          <span className="m-label mobile-only">Seu custo unit.</span>
          {item.produto && !sigiloso
            ? <CostInput valor={item.custo} aoEditar={(v) => setCusto(item.n, v)} aoConfirmar={(v) => confirmarCusto(item, v)}
                rotulo={"Seu custo unitário do item " + item.n + " — editável"} />
            : <span style={{ paddingRight: "8px", color: "var(--silk)" }}>—</span>}
        </div>
        <div className="c-margem" role="cell">
          <span className="m-label mobile-only">Margem</span>
          {item.margemPct == null || sigiloso
            ? <span style={{ color: "var(--silk)" }}>—</span>
            : <span className={"margem-pill " + (item.coberto ? item.status : "previa")}><NumPct value={item.margemPct} />{!item.coberto && <em className="previa-tag"> prévia</em>}</span>}
        </div>
        <div className="c-lucro" role="cell">
          <span className="m-label mobile-only">Lucro do item</span>
          {item.lucro == null || sigiloso
            ? <span style={{ color: "var(--silk)" }}>{sigiloso ? "valor sigiloso" : "—"}</span>
            : <span style={item.coberto ? undefined : { color: "var(--silk)" }}><NumBRL value={item.lucro} /></span>}
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
