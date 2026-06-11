// RADAR DE PREGÕES — abas Habilitação (citação verificada) e Fiscal / NF-e
const HABIL_STATUS = {
  ok: { rotulo: "Tenho", cls: "sinal" },
  pendente: { rotulo: "Pendente", cls: "pico" },
  nao_tenho: { rotulo: "Não tenho", cls: "clip" },
};
const ORDEM_CAT = ["juridica", "fiscal", "tecnica", "economico_financeira", "proposta", "outros"];

function HabilitacaoTab({ pregao, habilStatus, setHabil }) {
  const habil = pregao.habilitacao;

  if (!habil) {
    return (
      <div className="estado-vazio mod">
        <div className="estado-ico" aria-hidden="true">{Ico.doc}</div>
        <h3>Habilitação ainda não extraída</h3>
        <p>Este pregão ainda não foi sincronizado. Ao sincronizar, baixamos o edital do PNCP e extraímos o checklist de habilitação — cada requisito com a citação literal do trecho que o exige.</p>
        <div className="estado-arquivos">
          {pregao.arquivos.map((arq) => (
            <span key={arq.titulo} className="arq-chip">{Ico.doc} {arq.titulo} <em>· {arq.paginas}p</em></span>
          ))}
        </div>
      </div>
    );
  }

  const grupos = ORDEM_CAT
    .map((cat) => ({ cat, itens: habil.filter((h) => h.categoria === cat) }))
    .filter((g) => g.itens.length);

  const naoVerificadas = habil.filter((h) => !h.verificada).length;

  return (
    <div className="habil-wrap">
      <div className="tbl-titulo">
        <span className="silk">Documentos de habilitação — extraídos do edital com citação</span>
      </div>

      <div className="gate-aviso mod">
        <span className="gate-ico" aria-hidden="true">{Ico.escudo}</span>
        <div>
          <strong>Gate de citação ativo.</strong> Cada requisito traz o trecho literal do edital. O verificador confere
          se o excerto existe mesmo no PDF — {naoVerificadas > 0
            ? <React.Fragment>{naoVerificadas} {naoVerificadas === 1 ? "citação não pôde ser confirmada" : "citações não puderam ser confirmadas"} e {naoVerificadas === 1 ? "está marcada" : "estão marcadas"} abaixo.</React.Fragment>
            : "todas as citações foram confirmadas no texto extraído."}
        </div>
      </div>

      {grupos.map((g) => (
        <section key={g.cat} className="habil-grupo">
          <h3 className="habil-cat">{CATEGORIA_TXT[g.cat]} <span className="habil-cat-n">{g.itens.length}</span></h3>
          <div className="habil-itens">
            {g.itens.map((h) => (
              <RequisitoCard key={h.id} h={h} pregao={pregao} status={habilStatus(h)} setHabil={setHabil} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function RequisitoCard({ h, pregao, status, setHabil }) {
  const st = HABIL_STATUS[status] || HABIL_STATUS.pendente;
  return (
    <div className={"req-card mod st-" + st.cls}>
      <div className="req-top">
        <div className="req-tit">
          <span className="req-nome">{h.requisito}</span>
          <span className={"req-obrig " + (h.obrigatorio ? "sim" : "nao")}>{h.obrigatorio ? "Obrigatório" : "Opcional"}</span>
        </div>
        <div className="req-acoes" role="group" aria-label={"Status: " + h.requisito}>
          {Object.entries(HABIL_STATUS).map(([k, v]) => (
            <button
              key={k}
              type="button"
              className={"req-st-btn " + v.cls + (status === k ? " on" : "")}
              aria-pressed={status === k}
              onClick={() => setHabil(h.id, k)}
            >
              {v.rotulo}
            </button>
          ))}
        </div>
      </div>
      <blockquote className="req-cita">
        <span className="req-cita-mark" aria-hidden="true"></span>
        “{h.excerto}”
        <footer className="req-cita-foot">
          <span className={"req-verif " + (h.verificada ? "ok" : "nao")}>
            <span className="req-verif-led" aria-hidden="true"></span>
            {h.verificada ? "Citação verificada no PDF" : "Citação não verificada"}
          </span>
          <a className="req-pag" href={linkPncp(pregao)} target="_blank" rel="noopener noreferrer">
            {Ico.externo} pág. {h.pagina} · ver no PNCP
          </a>
        </footer>
      </blockquote>
    </div>
  );
}

/* ============ ABA FISCAL / NF-e ============ */
function FiscalTab({ fiscalItens, prontos, total, config, setRegime, pregao }) {
  const pct = total > 0 ? prontos / total : 0;
  return (
    <div className="fiscal-wrap">
      <div className="fiscal-selo mod">
        <div className="fiscal-selo-info">
          <div className="silk">Prontidão para NF-e</div>
          <div className="fiscal-selo-num"><strong>{prontos}</strong> de {total} itens prontos</div>
          <div className="fiscal-selo-barra" aria-hidden="true">
            <span style={{ width: (pct * 100).toFixed(0) + "%" }}></span>
          </div>
        </div>
        <div className="fiscal-regime">
          <span className="silk">Regime tributário</span>
          <div className="seg" role="group" aria-label="Regime tributário">
            <button type="button" className={"seg-btn" + (config.regime_tributario === "simples" ? " on" : "")} onClick={() => setRegime("simples")}>Simples (CSOSN)</button>
            <button type="button" className={"seg-btn" + (config.regime_tributario === "presumido" ? " on" : "")} onClick={() => setRegime("presumido")}>Presumido (CST)</button>
          </div>
          <span className="fiscal-uf mono">UF origem {config.uf_origem} → destino {pregao.uf}</span>
        </div>
      </div>

      <div className="mod tbl fiscal-tbl" role="table" aria-label="Prontidão fiscal por item">
        <div className="fiscal-head" role="row">
          <div className="silk" role="columnheader">Nº</div>
          <div className="silk" role="columnheader">Item</div>
          <div className="silk" role="columnheader">NCM</div>
          <div className="silk" role="columnheader">CFOP</div>
          <div className="silk" role="columnheader">{config.regime_tributario === "simples" ? "CSOSN" : "CST"}</div>
          <div className="silk" role="columnheader">Prontidão</div>
        </div>
        {fiscalItens.map(({ it, f }) => (
          <div className="fiscal-row" key={it.n} role="row">
            <div className="c-num" role="cell">{String(it.n).padStart(2, "0")}</div>
            <div className="fiscal-nome" role="cell">{it.nome}</div>
            {f ? (
              <React.Fragment>
                <div role="cell">
                  <span className="m-label mobile-only">NCM</span>
                  {f.ncm ? <span className="fiscal-chip"><span className="mono">{f.ncm}</span><em className="chip-fonte">{f.ncmFonte}</em></span> : <span className="fiscal-falta">faltam dados</span>}
                </div>
                <div role="cell">
                  <span className="m-label mobile-only">CFOP</span>
                  <span className="fiscal-chip sugest"><span className="mono">{f.cfop}</span><em className="chip-fonte">sugestão</em></span>
                </div>
                <div role="cell">
                  <span className="m-label mobile-only">{f.cstRotulo}</span>
                  {f.cstCsosn ? <span className="fiscal-chip sugest"><span className="mono">{f.cstCsosn}</span><em className="chip-fonte">sugestão</em></span> : <span className="fiscal-falta">faltam dados</span>}
                </div>
                <div className="fiscal-pronto" role="cell">
                  <span className="m-label mobile-only">Prontidão</span>
                  <span className={"st-led " + (f.pronto ? "sinal" : "pico")} aria-hidden="true"></span>
                  <span className="st-txt">{f.pronto ? "Pronto" : "Incompleto"}</span>
                </div>
              </React.Fragment>
            ) : (
              <div className="fiscal-semmatch" role="cell" style={{ gridColumn: "3 / -1" }}>
                <span className="st-led off" aria-hidden="true"></span> Sem produto casado — confirme o match na aba Itens para liberar os dados fiscais.
              </div>
            )}
          </div>
        ))}
      </div>

      <p className="fiscal-disclaimer">
        {Ico.alerta} Sugestões fiscais (NCM, CFOP, CST/CSOSN) são apoio, não orientação contábil. Confirme com seu contador antes de emitir a nota.
      </p>
    </div>
  );
}

/* ícones adicionais */
Object.assign(window.Ico, {
  externo: (<svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M5 2H2.5v9.5h9.5V9M8 2h4v4M12 2 6.5 7.5"></path></svg>),
  link: (<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M6.5 9.5 9.5 6.5M7 4.5 8 3.5a2.5 2.5 0 0 1 3.5 3.5l-1 1M9 11.5 8 12.5A2.5 2.5 0 0 1 4.5 9l1-1"></path></svg>),
  check: (<svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2"><path d="M2.5 7.5 6 11l5.5-7.5"></path></svg>),
  doc: (<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"><path d="M4 1.5h5L12.5 5v9.5h-8.5z"></path><path d="M9 1.5V5h3.5M5.5 8h5M5.5 10.5h5"></path></svg>),
  escudo: (<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M8 1.5 13 3v4.5c0 3.2-2.2 5.5-5 7-2.8-1.5-5-3.8-5-7V3z"></path><path d="M5.8 8 7.3 9.5 10.4 6"></path></svg>),
  alerta: (<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ verticalAlign: "-2px", marginRight: "4px" }}><path d="M8 2 1.5 13.5h13z"></path><path d="M8 6.5v3.5M8 12h.01"></path></svg>),
});

Object.assign(window, { HabilitacaoTab, FiscalTab, RequisitoCard, HABIL_STATUS });
