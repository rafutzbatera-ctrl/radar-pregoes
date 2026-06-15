// RADAR DE PREGÕES — Tela "Inteligência de mercado"
// Histórico de preços homologados + perfil dos concorrentes, derivado dos
// RESULTADOS que o usuário já coletou do PNCP.
// HONESTIDADE (princípio nº1): a amostra reflete SÓ os editais já coletados —
// não é uma base nacional. O N. da amostra aparece sempre, em todo bloco.
// Dados reais via API (/mercado/*). desagio_*_pct vêm como FRAÇÃO 0..1.
import React from "react";
import { motion } from "framer-motion";
import { api } from "./api.js";
import { MotionCtx, Ico, fmtBRL } from "./helpers.jsx";
import { EstadoCarregando, EstadoErro } from "./FindScreen.jsx";

// fração 0..1 → "30%" (inteiro; espelha fmtPctReal da aba Resultados)
function fmtPctFrac(frac) {
  if (frac == null || Number.isNaN(Number(frac))) return "—";
  return Math.round(Number(frac) * 100) + "%";
}

const ABAS = [
  { id: "precos", rotulo: "Preços" },
  { id: "concorrentes", rotulo: "Concorrentes" },
];

export default function MercadoScreen({ avisar }) {
  const { reduzido, estatico } = React.useContext(MotionCtx);
  const [aba, setAba] = React.useState("precos");
  const [coletando, setColetando] = React.useState(false);

  // estado por aba: cada uma faz suas próprias buscas
  const precosRef = React.useRef(null);
  const concorrentesRef = React.useRef(null);

  const coletar = () => {
    if (coletando) return;
    setColetando(true);
    avisar && avisar("Coletando resultados no PNCP — pode demorar (item a item)…", "aviso");
    api.mercadoColetar()
      .then((r) => {
        const n = (r && r.itens_gravados) || 0;
        avisar && avisar(
          `${n} ${n === 1 ? "item coletado" : "itens coletados"} (${(r && r.pregoes_homologados) || 0} pregões homologados)`,
          "ok"
        );
        // recarrega a aba ativa (se já tinha feito uma busca)
        if (aba === "precos" && precosRef.current) precosRef.current();
        if (aba === "concorrentes" && concorrentesRef.current) concorrentesRef.current();
      })
      .catch((e) => avisar && avisar((e && e.message) || "falha ao coletar resultados", "erro"))
      .finally(() => setColetando(false));
  };

  return (
    <motion.div className="screen-inner"
      initial={estatico ? false : reduzido ? { opacity: 0 } : { opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reduzido ? { duration: 0.15 } : { type: "spring", stiffness: 300, damping: 30 }}>
      <div className="silk">Histórico de preços e concorrência</div>
      <h1 className="pg-titulo">Inteligência de mercado</h1>
      <p className="pg-sub">
        Preços homologados e perfil dos concorrentes a partir dos resultados que
        você já coletou do PNCP. Apoio à decisão — confira sempre o edital oficial.
      </p>

      <div className="cert-aviso" role="note" style={{ marginBottom: "16px" }}>
        {Ico.alerta}
        <span>
          A amostra reflete <strong>só os editais que você já coletou</strong> —
          não é uma base nacional. O número da amostra (N) aparece em cada bloco.
        </span>
      </div>

      <div className="mercado-acoes">
        <button type="button" className="btn-rodar" onClick={coletar} disabled={coletando}
          style={{ color: "var(--fundo)" }}>
          {coletando
            ? <React.Fragment><span className="spin" aria-hidden="true"></span> Coletando… pode demorar</React.Fragment>
            : <React.Fragment>{Ico.raio} Coletar resultados</React.Fragment>}
        </button>
        <span className="silk mercado-acoes-nota">
          Busca os resultados item a item no PNCP (operação lenta) e atualiza a amostra.
        </span>
      </div>

      <div className="abas" role="tablist" aria-label="Inteligência de mercado">
        {ABAS.map((ab) => (
          <button key={ab.id} type="button" role="tab"
            id={`mercado-tab-${ab.id}`}
            aria-selected={aba === ab.id}
            aria-controls={`mercado-painel-${ab.id}`}
            className={"aba" + (aba === ab.id ? " ativa" : "")}
            style={{ color: aba === ab.id ? "var(--tinta)" : "var(--silk)" }}
            onClick={() => setAba(ab.id)}>
            {ab.rotulo}
          </button>
        ))}
      </div>

      <div className="aba-painel" role="tabpanel"
        id={`mercado-painel-${aba}`} aria-labelledby={`mercado-tab-${aba}`}>
        {aba === "precos"
          ? <PrecosAba registrarBuscar={(fn) => { precosRef.current = fn; }} />
          : <ConcorrentesAba registrarBuscar={(fn) => { concorrentesRef.current = fn; }} />}
      </div>
    </motion.div>
  );
}

/* ============ ABA PREÇOS — histórico de preços homologados ============ */
function PrecosAba({ registrarBuscar }) {
  const [q, setQ] = React.useState("");
  const [ncm, setNcm] = React.useState("");
  const [estado, setEstado] = React.useState({ carregando: false, dados: null, erro: null, buscou: false });
  // refs com o termo atual para o re-buscar disparado pela coleta
  const qRef = React.useRef("");
  const ncmRef = React.useRef("");
  React.useEffect(() => { qRef.current = q; }, [q]);
  React.useEffect(() => { ncmRef.current = ncm; }, [ncm]);

  const buscar = React.useCallback(() => {
    setEstado({ carregando: true, dados: null, erro: null, buscou: true });
    api.mercadoPrecos(qRef.current.trim(), ncmRef.current.trim())
      .then((d) => setEstado({ carregando: false, dados: d, erro: null, buscou: true }))
      .catch((e) => setEstado({ carregando: false, dados: null, erro: (e && e.message) || "erro", buscou: true }));
  }, []);

  React.useEffect(() => { registrarBuscar && registrarBuscar(buscar); }, [buscar, registrarBuscar]);

  const aoSubmeter = (e) => { e.preventDefault(); buscar(); };

  const d = estado.dados || {};
  const r = d.resumo || null;
  const itens = d.itens || [];
  const amostra = d.amostra ?? 0;

  return (
    <div className="mercado-aba">
      <form className="mercado-filtros" onSubmit={aoSubmeter}>
        <input className="form-input longa" value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="Termo — ex.: microfone, caixa de som" aria-label="Termo de busca" />
        <input className="form-input curta" value={ncm} onChange={(e) => setNcm(e.target.value)}
          placeholder="NCM (opcional)" aria-label="NCM (opcional)" />
        <button type="submit" className="btn-rodar" disabled={estado.carregando}
          style={{ color: "var(--fundo)" }}>
          {estado.carregando
            ? <React.Fragment><span className="spin" aria-hidden="true"></span> Buscando…</React.Fragment>
            : <React.Fragment>{Ico.busca} Buscar</React.Fragment>}
        </button>
      </form>

      {estado.carregando ? (
        <EstadoCarregando />
      ) : estado.erro ? (
        <EstadoErro mensagem={estado.erro} recarregar={buscar} />
      ) : !estado.buscou ? (
        <div className="estado-vazio mod">
          <h3>Consulte o histórico de preços</h3>
          <p>Digite um termo (e opcionalmente um NCM) e clique em Buscar para ver os preços homologados na sua amostra.</p>
        </div>
      ) : amostra === 0 ? (
        <div className="estado-vazio mod">
          <h3>Amostra 0</h3>
          <p>Nenhum item homologado na sua amostra para esse filtro. Colete resultados ou refine o termo. (A amostra reflete só os editais já coletados.)</p>
        </div>
      ) : (
        <React.Fragment>
          {r && (
            <div className="capag-card mod result-resumo">
              <div className="result-resumo-linha">
                Preço unit. mín <strong>{r.preco_unit_min != null ? fmtBRL(r.preco_unit_min) : "—"}</strong>
                {" · "}mediana <strong>{r.preco_unit_mediana != null ? fmtBRL(r.preco_unit_mediana) : "—"}</strong>
                {" · "}máx <strong>{r.preco_unit_max != null ? fmtBRL(r.preco_unit_max) : "—"}</strong>
                {" · "}deságio médio{" "}
                {(r.amostra_desagio ?? 0) > 0
                  ? <strong>{fmtPctFrac(r.desagio_medio_pct)} <span className="silk">(em {r.amostra_desagio} {r.amostra_desagio === 1 ? "item" : "itens"})</span></strong>
                  : <strong title="sem deságio na amostra">—</strong>}
              </div>
              {Array.isArray(r.unidades) && r.unidades.length > 1 ? (
                <div className="cert-aviso mercado-unidades-aviso" role="note">
                  {Ico.alerta}
                  <span>
                    Preço unitário mistura unidades: {r.unidades.map((u) => `${u.unidade || "?"}(${u.n})`).join(", ")} — compare dentro da mesma unidade.
                  </span>
                </div>
              ) : Array.isArray(r.unidades) && r.unidades.length === 1 ? (
                <div className="result-resumo-nota silk">
                  Unidade: <strong>{r.unidades[0].unidade || "—"}</strong>
                </div>
              ) : null}
              <div className="result-resumo-nota silk">
                Amostra: <strong>{amostra}</strong> {amostra === 1 ? "item homologado" : "itens homologados"} — só dos editais que você coletou.
              </div>
            </div>
          )}

          <div className="mod tbl mercado-precos-tbl" role="table" aria-label="Preços homologados">
            <div className="tbl-head mercado-precos-head" role="row">
              <div className="silk" role="columnheader">Descrição</div>
              <div className="silk" role="columnheader">Homologado (unit)</div>
              <div className="silk" role="columnheader">Deságio</div>
              <div className="silk" role="columnheader">Vencedor</div>
              <div className="silk" role="columnheader">Órgão / UF</div>
              <div className="silk" role="columnheader">Ano</div>
            </div>
            {itens.map((it, i) => (
              <div className="tbl-row mercado-precos-row" role="row" key={i}>
                <div className="c-desc" role="cell">
                  <div className="d-nome">{it.descricao || "—"}</div>
                  {it.ncm && <small className="silk mono">NCM {it.ncm}</small>}
                </div>
                <div role="cell">
                  <span className="m-label mobile-only">Homologado (unit)</span>
                  {it.valor_homologado_unit != null ? fmtBRL(it.valor_homologado_unit)
                    : <span style={{ color: "var(--silk)" }}>—</span>}
                </div>
                <div role="cell">
                  <span className="m-label mobile-only">Deságio</span>
                  {it.desagio_real_pct != null
                    ? <span className="result-desagio">{fmtPctFrac(it.desagio_real_pct)}</span>
                    : <span style={{ color: "var(--silk)" }}>—</span>}
                </div>
                <div role="cell">
                  <span className="m-label mobile-only">Vencedor</span>
                  {it.vencedor_nome ? (
                    <span className="result-venc">
                      {it.vencedor_nome}
                      {it.vencedor_porte && <span className="result-porte">{it.vencedor_porte}</span>}
                    </span>
                  ) : <span style={{ color: "var(--silk)" }}>—</span>}
                </div>
                <div role="cell">
                  <span className="m-label mobile-only">Órgão / UF</span>
                  <span className="mercado-orgao">
                    {it.orgao_nome || "—"}{it.uf ? <em className="silk"> · {it.uf}</em> : null}
                  </span>
                </div>
                <div role="cell">
                  <span className="m-label mobile-only">Ano</span>
                  {it.ano || "—"}
                </div>
              </div>
            ))}
          </div>
        </React.Fragment>
      )}
    </div>
  );
}

/* ============ ABA CONCORRENTES — perfil dos vencedores ============ */
function ConcorrentesAba({ registrarBuscar }) {
  const [uf, setUf] = React.useState("");
  const [q, setQ] = React.useState("");
  const [estado, setEstado] = React.useState({ carregando: false, dados: null, erro: null, buscou: false });
  const ufRef = React.useRef("");
  const qRef = React.useRef("");
  React.useEffect(() => { ufRef.current = uf; }, [uf]);
  React.useEffect(() => { qRef.current = q; }, [q]);

  const buscar = React.useCallback(() => {
    setEstado({ carregando: true, dados: null, erro: null, buscou: true });
    api.mercadoConcorrentes(ufRef.current.trim().toUpperCase(), qRef.current.trim())
      .then((d) => setEstado({ carregando: false, dados: d, erro: null, buscou: true }))
      .catch((e) => setEstado({ carregando: false, dados: null, erro: (e && e.message) || "erro", buscou: true }));
  }, []);

  React.useEffect(() => { registrarBuscar && registrarBuscar(buscar); }, [buscar, registrarBuscar]);

  const aoSubmeter = (e) => { e.preventDefault(); buscar(); };

  const d = estado.dados || {};
  const concorrentes = d.concorrentes || [];
  const amostra = d.amostra_itens ?? 0;

  return (
    <div className="mercado-aba">
      <form className="mercado-filtros" onSubmit={aoSubmeter}>
        <input className="form-input curta" value={uf} onChange={(e) => setUf(e.target.value)}
          placeholder="UF (opcional)" maxLength={2} aria-label="UF (opcional)"
          style={{ textTransform: "uppercase" }} />
        <input className="form-input longa" value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="Termo (opcional) — ex.: áudio" aria-label="Termo de busca (opcional)" />
        <button type="submit" className="btn-rodar" disabled={estado.carregando}
          style={{ color: "var(--fundo)" }}>
          {estado.carregando
            ? <React.Fragment><span className="spin" aria-hidden="true"></span> Buscando…</React.Fragment>
            : <React.Fragment>{Ico.busca} Buscar</React.Fragment>}
        </button>
      </form>

      {estado.carregando ? (
        <EstadoCarregando />
      ) : estado.erro ? (
        <EstadoErro mensagem={estado.erro} recarregar={buscar} />
      ) : !estado.buscou ? (
        <div className="estado-vazio mod">
          <h3>Conheça seus concorrentes</h3>
          <p>Filtre por UF e/ou termo (ambos opcionais) e clique em Buscar para ver quem mais venceu na sua amostra.</p>
        </div>
      ) : amostra === 0 ? (
        <div className="estado-vazio mod">
          <h3>Amostra 0</h3>
          <p>Nenhum item homologado na sua amostra para esse filtro. Colete resultados ou refine o termo. (A amostra reflete só os editais já coletados.)</p>
        </div>
      ) : (
        <React.Fragment>
          <div className="capag-card mod result-resumo">
            <div className="result-resumo-nota silk">
              Amostra: <strong>{amostra}</strong> {amostra === 1 ? "item considerado" : "itens considerados"} — só dos editais que você coletou. Ordenado por nº de vitórias.
            </div>
          </div>

          <div className="mod tbl mercado-conc-tbl" role="table" aria-label="Concorrentes">
            <div className="tbl-head mercado-conc-head" role="row">
              <div className="silk" role="columnheader">Vencedor</div>
              <div className="silk" role="columnheader">Vitórias</div>
              <div className="silk" role="columnheader">Deságio médio</div>
              <div className="silk" role="columnheader">Total homologado</div>
              <div className="silk" role="columnheader">Órgãos</div>
              <div className="silk" role="columnheader">UFs</div>
            </div>
            {concorrentes.map((c, i) => (
              <div className="tbl-row mercado-conc-row" role="row" key={c.cnpj || i}>
                <div role="cell">
                  <span className="result-venc" style={{ justifyContent: "flex-start" }}>
                    {c.nome || "—"}
                    {c.porte && <span className="result-porte">{c.porte}</span>}
                  </span>
                </div>
                <div role="cell">
                  <span className="m-label mobile-only">Vitórias</span>
                  <strong>{c.n_vitorias ?? 0}</strong>
                </div>
                <div role="cell">
                  <span className="m-label mobile-only">Deságio médio</span>
                  {(c.n_com_desagio ?? 0) > 0 ? (
                    <span className="result-desagio">
                      {fmtPctFrac(c.desagio_medio_pct)}
                      {c.n_com_desagio < (c.n_vitorias ?? 0) && (
                        <small className="silk"> (em {c.n_com_desagio}/{c.n_vitorias})</small>
                      )}
                    </span>
                  ) : <span style={{ color: "var(--silk)" }}>—</span>}
                </div>
                <div role="cell">
                  <span className="m-label mobile-only">Total homologado</span>
                  {c.valor_total_homologado != null ? (
                    <React.Fragment>
                      {fmtBRL(c.valor_total_homologado)}
                      {(c.n_com_valor ?? 0) < (c.n_vitorias ?? 0) && (
                        <small className="silk"> (em {c.n_com_valor ?? 0}/{c.n_vitorias})</small>
                      )}
                    </React.Fragment>
                  ) : <span style={{ color: "var(--silk)" }}>—</span>}
                </div>
                <div role="cell">
                  <span className="m-label mobile-only">Órgãos</span>
                  {c.n_orgaos ?? 0}
                </div>
                <div role="cell">
                  <span className="m-label mobile-only">UFs</span>
                  <span className="mono">{(c.ufs && c.ufs.length) ? c.ufs.join(", ") : "—"}</span>
                </div>
              </div>
            ))}
          </div>
        </React.Fragment>
      )}
    </div>
  );
}
