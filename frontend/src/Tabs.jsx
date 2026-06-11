// RADAR DE PREGÕES — abas Habilitação (citação verificada) e Fiscal / NF-e
import React from "react";
import { Ico, CATEGORIA_TXT, linkPncp } from "./helpers.jsx";

export const HABIL_STATUS = {
  ok: { rotulo: "Tenho", cls: "sinal" },
  pendente: { rotulo: "Pendente", cls: "pico" },
  nao_tenho: { rotulo: "Não tenho", cls: "clip" },
};
const ORDEM_CAT = ["juridica", "fiscal", "tecnica", "economico_financeira", "proposta", "outros"];

// chip de arquivo: link direto para o binário oficial no PNCP (abre/baixa o PDF)
export function ArquivoChip({ arq }) {
  if (!arq.url) {
    return <span className="arq-chip">{Ico.doc} {arq.titulo}{arq.tipo && <em> · {arq.tipo}</em>}</span>;
  }
  return (
    <a className="arq-chip arq-link" href={arq.url} target="_blank" rel="noopener noreferrer"
       title="Abrir o arquivo oficial no PNCP">
      {Ico.doc} {arq.titulo}{arq.tipo && <em> · {arq.tipo}</em>} {Ico.externo}
    </a>
  );
}

export function HabilitacaoTab({ pregao, habilStatus, setHabil, sincronizar, sincronizando }) {
  const habil = pregao.habilitacao;

  // null = checklist ainda carregando da API
  if (habil == null) {
    return (
      <div className="cards" aria-busy="true" aria-label="Carregando habilitação">
        <div className="card-pregao mod skel">
          <span className="skel-bar w30"></span>
          <span className="skel-bar w70 big"></span>
          <span className="skel-bar w90"></span>
        </div>
      </div>
    );
  }

  // [] sem sincronizar = edital ainda não baixado/extraído → oferecer sincronização
  if (habil.length === 0 && !pregao.sincronizado) {
    return (
      <div className="estado-vazio mod">
        <div className="estado-ico" aria-hidden="true">{Ico.doc}</div>
        <h3>Habilitação ainda não extraída</h3>
        <p>Este pregão ainda não foi sincronizado. Ao sincronizar, baixamos o edital do PNCP e extraímos o checklist de habilitação — cada requisito com a citação literal do trecho que o exige.</p>
        {(pregao.arquivos || []).length > 0 && (
          <div className="estado-arquivos">
            {pregao.arquivos.map((arq) => (
              <ArquivoChip key={arq.titulo} arq={arq} />
            ))}
          </div>
        )}
        <button type="button" className={"btn-rodar" + (sincronizando ? " rodando" : "")} disabled={sincronizando} onClick={sincronizar}>
          {sincronizando
            ? <React.Fragment><span className="spin" aria-hidden="true"></span> Sincronizando… (pode levar alguns minutos)</React.Fragment>
            : <React.Fragment>{Ico.raio} Sincronizar agora</React.Fragment>}
        </button>
      </div>
    );
  }

  // [] com pregão sincronizado = o extrator não achou seção de habilitação (permitido)
  if (habil.length === 0) {
    return (
      <div className="estado-vazio mod">
        <div className="estado-ico" aria-hidden="true">{Ico.doc}</div>
        <h3>Sem seção de habilitação</h3>
        <p>O edital foi lido e nenhuma seção de documentos de habilitação foi identificada no texto. Nada foi inventado — confira o edital oficial no PNCP.</p>
        <a className="link-pncp" href={pregao.linkPncp || linkPncp(pregao)} target="_blank" rel="noopener noreferrer">
          {Ico.externo} Ver edital no PNCP
        </a>
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

      {/* o PDF oficial sempre a um clique — a extração é apoio, não substituto */}
      {(pregao.arquivos || []).length > 0 && (
        <div className="estado-arquivos arquivos-inline">
          {pregao.arquivos.map((arq) => (
            <ArquivoChip key={arq.titulo} arq={arq} />
          ))}
        </div>
      )}

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

export function RequisitoCard({ h, pregao, status, setHabil }) {
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
              onClick={() => setHabil(h, k)}
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
          <a className="req-pag" href={pregao.linkPncp || linkPncp(pregao)} target="_blank" rel="noopener noreferrer">
            {Ico.externo} {h.pagina != null ? "pág. " + h.pagina + " · " : ""}ver no PNCP
          </a>
        </footer>
      </blockquote>
    </div>
  );
}

/* ============ ABA FISCAL / NF-e ============ */
export function FiscalTab({ fiscalItens, prontos, total, config, setRegime, pregao }) {
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
          <span className="fiscal-uf mono">UF origem {config.uf_origem || "—"} → destino {pregao.uf || "—"}</span>
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
