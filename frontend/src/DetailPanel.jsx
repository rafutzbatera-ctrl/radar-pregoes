// RADAR DE PREGÕES — painel de detalhe do item (spring + drag-to-close)
// Sob modo estático/reduzido: condicional simples, SEM AnimatePresence.
import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { MotionCtx, Ico, fmtBRL, fiscalDoItem, NumBRL, NumPct, CostInput, fontePrecoTexto } from "./helpers.jsx";

export function useIsMobile() {
  const [mob, setMob] = React.useState(() => window.matchMedia("(max-width: 920px)").matches);
  React.useEffect(() => {
    const mq = window.matchMedia("(max-width: 920px)");
    const fn = (e) => setMob(e.matches);
    mq.addEventListener("change", fn);
    return () => mq.removeEventListener("change", fn);
  }, []);
  return mob;
}

function PainelConteudo({ item, pregao, fechar, setCusto, confirmarCusto, limparCusto,
  setLance, confirmarLance, limparLance, desagio, setMatch, config, fecharRef }) {
  const sigiloso = item.status === "sigiloso";
  const temMatch = !!item.produto;
  const m = item.matchAtual;
  const f = temMatch || item.ncmPncp ? fiscalDoItem(item, pregao, config) : null;
  const margemAlvoPct = config && config.margem_alvo != null
    ? Math.round(Number(config.margem_alvo) * 100) : 20;
  const manualSobreCatalogo = item.custoManual != null && temMatch && !sigiloso;
  const phCusto = item.custo == null && item.simulacaoCustoMax != null
    ? "máx " + fmtBRL(item.simulacaoCustoMax) : "";
  // P4: pisos de disputa (só com custo efetivo) — lance mínimo no alvo e empate
  const temPreco = item.preco != null;
  const lanceMinimoAlvo = item.custo != null && margemAlvoPct < 100
    ? item.custo / (1 - margemAlvoPct / 100) : null;
  return (
    <React.Fragment>
      <div className="painel-grip" aria-hidden="true"></div>
      <header className="painel-head">
        <div>
          <div className="silk">
            Item {String(item.n).padStart(2, "0")} · {item.produto ? item.produto.cod : "sem produto casado"}
          </div>
          <h2>{item.nome}</h2>
        </div>
        <button type="button" className="painel-fechar" onClick={fechar} ref={fecharRef} aria-label="Fechar painel (Esc)">
          {Ico.fechar}
        </button>
      </header>

      <div className="painel-corpo">
        <section className="painel-bloco">
          <h3>Especificação completa (edital)</h3>
          <p className="painel-spec">{item.spec}</p>
        </section>

        <section className="painel-bloco">
          <h3>Condições do certame</h3>
          <div className="painel-grid">
            <div className="painel-kv">
              <div className="silk">Critério de julgamento</div>
              <div className="v">{item.criterio || "—"}</div>
            </div>
            <div className="painel-kv">
              <div className="silk">Benefício ME/EPP</div>
              <div className="v">{item.beneficio || "—"}</div>
            </div>
            <div className="painel-kv">
              <div className="silk">Quantidade</div>
              <div className="v">×{item.qtd} · {item.unidade || "—"}</div>
            </div>
            <div className="painel-kv">
              <div className="silk">Valor unit. estimado <em className="chip-fonte">teto oficial</em></div>
              <div className="v">{sigiloso ? "sigiloso" : item.unit != null ? fmtBRL(item.unit) : "—"}</div>
            </div>
          </div>
        </section>

        {/* CUSTO primeiro (P3): dado do usuário entra na conta com ou sem match */}
        {!sigiloso && (
          <section className="painel-bloco">
            <h3>
              Custo & margem
              {manualSobreCatalogo && <span className="custo-tag-manual" style={{ marginLeft: "8px" }}>manual</span>}
            </h3>
            <div className="painel-custo">
              <div className="painel-custo-linha">
                <span className="painel-fonte">
                  Seu custo unitário (editável)
                  {item.fonteCusto === "catalogo" && <em className="chip-fonte"> do catálogo</em>}
                </span>
                <span className="painel-custo-edit">
                  <CostInput valor={item.custo} placeholder={phCusto}
                    aoEditar={(v) => setCusto(item.n, v)} aoConfirmar={(v) => confirmarCusto(item, v)}
                    rotulo={"Seu custo unitário do item " + item.n + " — editável"} />
                  {manualSobreCatalogo && limparCusto && (
                    <button type="button" className="custo-limpar" title="Limpar custo manual (volta ao catálogo)"
                      aria-label="Limpar custo manual" onClick={() => limparCusto(item)}>{Ico.fechar}</button>
                  )}
                </span>
              </div>
              {item.coberto && item.margemPct != null ? (
                <React.Fragment>
                  <div className="painel-custo-linha">
                    <span className="painel-fonte">Margem resultante</span>
                    <span className={"margem-pill " + item.status}><NumPct value={item.margemPct} /></span>
                  </div>
                  <div className="painel-custo-linha">
                    <span className="painel-fonte">Lucro do item (×{item.qtd})</span>
                    <span className="mono" style={{ fontWeight: 600 }}><NumBRL value={item.lucro} /></span>
                  </div>
                </React.Fragment>
              ) : item.simulacaoCustoMax != null ? (
                <div className="painel-custo-linha simulacao">
                  <span className="painel-fonte">
                    Simulação <em className="chip-fonte">margem alvo {margemAlvoPct}%</em>
                  </span>
                  <span className="mono">
                    custo máx {fmtBRL(item.simulacaoCustoMax)} · lucro <NumBRL value={item.simulacaoLucro || 0} />
                  </span>
                </div>
              ) : (
                <p className="painel-spec" style={{ color: "var(--silk)", margin: 0 }}>
                  Digite seu custo para calcular a margem deste item.
                </p>
              )}
            </div>
          </section>
        )}

        {/* P4: disputa do item — lance previsto (editável), preço esperado e
            pisos (guia de disputa, fora do veredito). O teto oficial segue
            visível acima. Sigiloso só vira conta com lance digitado. */}
        <section className="painel-bloco">
          <h3>Disputa do item</h3>
          <div className="painel-custo">
            <div className="painel-custo-linha">
              <span className="painel-fonte">Seu lance previsto (editável)</span>
              <span className="painel-custo-edit">
                <CostInput valor={item.lancePrevisto}
                  placeholder={sigiloso ? "lance" : item.unit != null ? "teto" : ""}
                  aoEditar={(v) => setLance && setLance(item.n, v)}
                  aoConfirmar={(v) => confirmarLance && confirmarLance(item, v)}
                  rotulo={"Seu lance previsto do item " + item.n + " — editável"} />
                {item.lancePrevisto != null && limparLance && (
                  <button type="button" className="custo-limpar" title="Limpar lance (volta ao deságio/teto)"
                    aria-label="Limpar lance previsto" onClick={() => limparLance(item)}>{Ico.fechar}</button>
                )}
              </span>
            </div>
            <div className="painel-custo-linha">
              <span className="painel-fonte">
                Preço esperado de disputa
                {temPreco && item.fontePreco
                  ? <em className="chip-fonte"> {fontePrecoTexto(item.fontePreco, desagio)}</em> : null}
              </span>
              <span className="mono" style={{ fontWeight: 600 }}>
                {temPreco ? fmtBRL(item.preco) : sigiloso ? "digite um lance" : "—"}
              </span>
            </div>
            {item.custo != null ? (
              <div className="painel-custo-linha simulacao">
                <span className="painel-fonte">
                  Guia de disputa <em className="chip-fonte">não entra no veredito</em>
                </span>
                <span className="mono">
                  desce até {lanceMinimoAlvo != null ? fmtBRL(lanceMinimoAlvo) : "—"} no alvo · empate {fmtBRL(item.custo)}
                </span>
              </div>
            ) : (
              <p className="painel-spec" style={{ color: "var(--silk)", margin: 0 }}>
                Digite seu custo para ver até onde pode descer mantendo a margem alvo.
              </p>
            )}
          </div>
        </section>

        {/* match com o catálogo — seção secundária (atalho opcional) */}
        <section className="painel-bloco">
          <h3>Match com o catálogo</h3>
          {temMatch ? (
            <div className="painel-match">
              <div className="painel-match-top">
                <div>
                  <div className="painel-match-nome">{item.produto.nome}</div>
                  <div className="painel-fonte">{item.produto.cod}{item.produto.cat ? " · " + item.produto.cat : ""}</div>
                </div>
                <span className={"match-badge " + (m && m.confirmado ? "ok" : "pend")}>
                  {m && m.confirmado ? "Confirmado" : "Sugerido"}{m && m.score != null ? " · " + (m.score * 100).toFixed(0) + "%" : ""}
                </span>
              </div>
              {!(m && m.confirmado) && setMatch && (
                <div className="painel-match-acoes">
                  <button type="button" className="match-btn ok" onClick={() => setMatch(item, { ...m, confirmado: true })}>{Ico.check} Confirmar match</button>
                  <button type="button" className="match-btn nao" onClick={() => setMatch(item, null)}>{Ico.fechar} Recusar</button>
                </div>
              )}
            </div>
          ) : (
            <p className="painel-spec" style={{ color: "var(--silk)" }}>
              Nenhum produto do catálogo casou com este item. O custo acima já entra no cálculo; casar um produto é opcional (atalho do catálogo).
            </p>
          )}
        </section>

        {/* fiscal */}
        {f && (
          <section className="painel-bloco">
            <h3>Prontidão NF-e <span className={"painel-pronto " + (f.pronto ? "ok" : "pend")}>{f.pronto ? "pronto" : "incompleto"}</span></h3>
            <div className="painel-grid painel-fiscal">
              <div className="painel-kv"><div className="silk">NCM</div><div className="v">{f.ncm || "—"} {f.ncmFonte && <em className="chip-fonte">{f.ncmFonte}</em>}</div></div>
              <div className="painel-kv"><div className="silk">CFOP <em className="chip-fonte">sugestão</em></div><div className="v">{f.cfop}</div></div>
              <div className="painel-kv"><div className="silk">{f.cstRotulo} <em className="chip-fonte">sugestão</em></div><div className="v">{f.cstCsosn || "—"}</div></div>
              <div className="painel-kv"><div className="silk">Unidade</div><div className="v">{item.unidade || "—"}</div></div>
            </div>
          </section>
        )}

        <p className="painel-nota">
          Valores estimados extraídos do edital. Sugestões fiscais são apoio, não orientação contábil. A especificação
          oficial e os anexos estão no PNCP — confira antes de dar lance.
        </p>
      </div>
    </React.Fragment>
  );
}

export default function DetailPanel({ item, pregao, fechar, setCusto, confirmarCusto, limparCusto,
  setLance, confirmarLance, limparLance, desagio, setMatch, config }) {
  const { estatico } = React.useContext(MotionCtx);
  const mobile = useIsMobile();
  const fecharRef = React.useRef(null);

  React.useEffect(() => {
    if (item && fecharRef.current) fecharRef.current.focus({ preventScroll: true });
  }, [item ? item.n : null]);

  /* ---- modo estático/reduzido: render direto, sem framer ---- */
  if (estatico) {
    if (!item) return null;
    return (
      <React.Fragment>
        <div className="overlay" onClick={fechar} aria-hidden="true"></div>
        <aside
          className="painel"
          role="dialog"
          aria-modal="true"
          aria-label={"Detalhe do item " + item.n + " — " + item.nome}
        >
          <PainelConteudo item={item} pregao={pregao} fechar={fechar} setCusto={setCusto} confirmarCusto={confirmarCusto} limparCusto={limparCusto}
            setLance={setLance} confirmarLance={confirmarLance} limparLance={limparLance} desagio={desagio} setMatch={setMatch} config={config} fecharRef={fecharRef} />
        </aside>
      </React.Fragment>
    );
  }

  /* ---- modo completo: spring + drag-to-close ---- */
  const eixo = mobile ? "y" : "x";
  const fora = mobile ? { y: "104%" } : { x: "106%" };
  const dentro = mobile ? { y: 0 } : { x: 0 };
  const springEntrada = { type: "spring", stiffness: 300, damping: 27, mass: 0.9 };

  const aoSoltar = (e, info) => {
    const off = mobile ? info.offset.y : info.offset.x;
    const vel = mobile ? info.velocity.y : info.velocity.x;
    // threshold de drag: passou → fecha com momentum; não passou → snap-back
    if (off > 130 || vel > 480) fechar();
  };

  return (
    <AnimatePresence>
      {item && (
        <React.Fragment key={"painel-" + item.n}>
          <motion.div
            className="overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.22 }}
            onClick={fechar}
            aria-hidden="true"
          ></motion.div>
          <motion.aside
            className="painel"
            role="dialog"
            aria-modal="true"
            aria-label={"Detalhe do item " + item.n + " — " + item.nome}
            initial={{ ...fora, opacity: 1 }}
            animate={{ ...dentro, opacity: 1 }}
            exit={{ ...fora, opacity: 1 }}
            transition={springEntrada}
            drag={eixo}
            dragConstraints={mobile ? { top: 0, bottom: 0 } : { left: 0, right: 0 }}
            dragElastic={mobile ? { top: 0.02, bottom: 0.9 } : { left: 0.02, right: 0.9 }}
            dragSnapToOrigin={true}
            dragTransition={{ bounceStiffness: 420, bounceDamping: 32 }}
            onDragEnd={aoSoltar}
          >
            <PainelConteudo item={item} pregao={pregao} fechar={fechar} setCusto={setCusto} confirmarCusto={confirmarCusto} limparCusto={limparCusto}
              setLance={setLance} confirmarLance={confirmarLance} limparLance={limparLance} desagio={desagio} setMatch={setMatch} config={config} fecharRef={fecharRef} />
          </motion.aside>
        </React.Fragment>
      )}
    </AnimatePresence>
  );
}
