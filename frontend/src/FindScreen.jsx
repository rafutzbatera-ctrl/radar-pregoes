// RADAR DE PREGÕES — Telas Encontrar / Meus pregões / Buscas salvas / Catálogo
// Dados reais via props (App carrega da API); estados de carregando/erro reais.
import React from "react";
import { motion } from "framer-motion";
import {
  MotionCtx, Ico, fmtBRL, Etiqueta, VEREDITO_TXT, normalizarVeredito, CostInput,
} from "./helpers.jsx";

const norm = (s) => String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

export function FindScreen({ aoAbrir, apenasSalvos, pregoes, erro, recarregar }) {
  const { reduzido, estatico } = React.useContext(MotionCtx);
  const [busca, setBusca] = React.useState("");
  const [uf, setUf] = React.useState("todas");
  const [modalidade, setModalidade] = React.useState("todas");
  const [recebendo, setRecebendo] = React.useState(false);
  const [soNovos, setSoNovos] = React.useState(false);

  const carregando = pregoes == null && !erro;
  const base = (pregoes || []).filter((p) => !apenasSalvos || p.salvo);
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

      <motion.div className="filtros" variants={entrada}>
        {!apenasSalvos && (
          <label className="busca">
            {Ico.busca}
            <input type="text" value={busca} onChange={(e) => setBusca(e.target.value)}
              placeholder="Palavra-chave — ex.: áudio, vídeo, projetor" aria-label="Buscar pregões por palavra-chave" />
          </label>
        )}
        <select className="filtro-sel" value={uf} onChange={(e) => setUf(e.target.value)} aria-label="Filtrar por UF">
          <option value="todas">UF · todas</option>
          {ufs.map((u) => <option key={u} value={u}>{u}</option>)}
        </select>
        <select className="filtro-sel" value={modalidade} onChange={(e) => setModalidade(e.target.value)} aria-label="Filtrar por modalidade">
          <option value="todas">Modalidade · todas</option>
          {modalidades.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <button type="button" className={"filtro-status" + (recebendo ? " on" : "")} aria-pressed={recebendo} onClick={() => setRecebendo(!recebendo)}>
          <span className="led" aria-hidden="true"></span>Recebendo propostas
        </button>
        <button type="button" className={"filtro-status" + (soNovos ? " on" : "")} aria-pressed={soNovos} onClick={() => setSoNovos(!soNovos)}>
          <span className="led" aria-hidden="true"></span>Só novos {qtdNovos > 0 && <em className="filtro-badge">{qtdNovos}</em>}
        </button>
      </motion.div>

      {carregando ? (
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
            <CartaoPregao key={p.id} pregao={p} variants={entrada} onClick={() => aoAbrir(p.id)} />
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

export function CartaoPregao({ pregao, variants, onClick }) {
  const ag = pregao.agregados || {};
  const veredito = normalizarVeredito(ag.veredito);
  const linhaSilk = [
    pregao.modalidade,
    pregao.municipio ? pregao.municipio + "/" + pregao.uf : pregao.uf,
    pregao.status,
  ].filter(Boolean).join(" · ");
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
        <span><span className="k">Valor estimado</span>{pregao.valorTotal != null ? fmtBRL(pregao.valorTotal) : "—"}</span>
        <span><span className="k">Propostas até</span>{pregao.prazo || "—"}</span>
        <span><span className="k">Itens</span>{ag.itensTotal > 0 ? ag.itensTotal : "—"}</span>
        <span className="desktop-only"><span className="k">Cobertura</span>{ag.itensTotal > 0 ? ag.itensConfirmados + "/" + ag.itensTotal + " no catálogo" : "—"}</span>
      </span>
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
                    ? <React.Fragment><span className="spin" aria-hidden="true"></span> Rodando…</React.Fragment>
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
