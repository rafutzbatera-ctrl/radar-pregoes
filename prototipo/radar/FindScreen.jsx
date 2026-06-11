// RADAR DE PREGÕES — Tela Encontrar / Meus pregões / Buscas salvas / Catálogo
function FindScreen({ aoAbrir, apenasSalvos, estadoUI }) {
  const { reduzido, estatico } = React.useContext(MotionCtx);
  const [busca, setBusca] = React.useState("áudio vídeo");
  const [uf, setUf] = React.useState("todas");
  const [modalidade, setModalidade] = React.useState("todas");
  const [recebendo, setRecebendo] = React.useState(true);
  const [soNovos, setSoNovos] = React.useState(false);

  const base = window.RADAR_DATA.pregoes.filter((p) => !apenasSalvos || p.salvo);
  const norm = (s) => String(s || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  const tokens = norm(busca).split(/\s+/).filter((t) => t.length >= 3);
  const lista = base.filter((p) => {
    if (uf !== "todas" && p.uf !== uf) return false;
    if (modalidade !== "todas" && p.modalidade !== modalidade) return false;
    if (recebendo && p.status !== "Recebendo propostas") return false;
    if (soNovos && !p.novo) return false;
    if (tokens.length > 0 && !apenasSalvos) {
      const palheiro = norm([p.titulo, p.orgao, p.municipio, p.descricao, p.itens.map((i) => i.nome + " " + i.spec).join(" ")].join(" "));
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
          <option value="todas">UF · todas</option><option value="SP">SP</option><option value="GO">GO</option>
        </select>
        <select className="filtro-sel" value={modalidade} onChange={(e) => setModalidade(e.target.value)} aria-label="Filtrar por modalidade">
          <option value="todas">Modalidade · todas</option><option value="Dispensa">Dispensa</option><option value="Pregão Eletrônico">Pregão Eletrônico</option>
        </select>
        <button type="button" className={"filtro-status" + (recebendo ? " on" : "")} aria-pressed={recebendo} onClick={() => setRecebendo(!recebendo)}>
          <span className="led" aria-hidden="true"></span>Recebendo propostas
        </button>
        <button type="button" className={"filtro-status" + (soNovos ? " on" : "")} aria-pressed={soNovos} onClick={() => setSoNovos(!soNovos)}>
          <span className="led" aria-hidden="true"></span>Só novos {qtdNovos > 0 && <em className="filtro-badge">{qtdNovos}</em>}
        </button>
      </motion.div>

      {/* estados de carregando / erro (demo via Tweaks) */}
      {estadoUI === "carregando" ? (
        <EstadoCarregando entrada={entrada} />
      ) : estadoUI === "erro" ? (
        <EstadoErro entrada={entrada} />
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

function CartaoPregao({ pregao, variants, onClick }) {
  const a = analisar(pregao, {});
  return (
    <motion.button type="button" className="card-pregao mod" variants={variants} onClick={onClick}
      aria-label={"Abrir análise de " + pregao.titulo + " — veredito prévio: " + VEREDITO_TXT[a.veredito]}>
      <span className="card-edital silk">
        {pregao.novo && <em className="card-novo">novo</em>}
        {pregao.modalidade} · {pregao.municipio}/{pregao.uf} · {pregao.status}
      </span>
      <span className="card-titulo">{pregao.titulo}</span>
      <span className="card-orgao">{pregao.orgao}</span>
      {pregao.descricao && <span className="card-desc">{pregao.descricao}</span>}
      <span className="card-meta mono">
        <span><span className="k">Valor estimado</span>{fmtBRL(pregao.valorTotal)}</span>
        <span><span className="k">Propostas até</span>{pregao.prazo}</span>
        <span><span className="k">Itens</span>{pregao.itens.length}</span>
        <span className="desktop-only"><span className="k">Cobertura</span>{a.cobertos}/{a.total} no catálogo</span>
      </span>
      <span className="card-vered">
        <Etiqueta veredito={a.veredito} />
        {!pregao.sincronizado && <span className="card-sync silk">sincronizar p/ habilitação</span>}
      </span>
    </motion.button>
  );
}

/* ---------- Buscas salvas ---------- */
function BuscasScreen({ aoAbrir }) {
  const { reduzido, estatico } = React.useContext(MotionCtx);
  const [buscas, setBuscas] = React.useState(window.RADAR_DATA.buscas);
  const [rodando, setRodando] = React.useState(null);

  const rodarBusca = (id) => {
    setRodando(id);
    setTimeout(() => setRodando(null), 1400);
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

      <div className="cards">
        {buscas.map((b) => (
          <motion.div key={b.id} className="busca-card mod" variants={entrada}>
            <div className="busca-card-main">
              <div className="busca-card-top">
                <span className="busca-card-nome">{b.nome}</span>
                <span className={"busca-card-status" + (b.ativo ? " on" : "")}>
                  <span className="led" aria-hidden="true"></span>{b.ativo ? "Ativa" : "Pausada"}
                </span>
              </div>
              <div className="busca-termos">
                {b.termos.split(",").map((t) => <span key={t} className="termo-chip">{t.trim()}</span>)}
              </div>
              <div className="busca-meta mono">
                <span><span className="k">UFs</span>{b.ufs}</span>
                <span><span className="k">Status</span>{b.status === "recebendo_proposta" ? "Recebendo propostas" : b.status}</span>
                <span><span className="k">Última execução</span>{b.ultimaExec}</span>
                {b.novos > 0 && <span className="busca-novos">{b.novos} {b.novos === 1 ? "novo" : "novos"}</span>}
              </div>
            </div>
            <div className="busca-card-acao">
              <button type="button" className={"btn-rodar" + (rodando === b.id ? " rodando" : "")} disabled={rodando === b.id} onClick={() => rodarBusca(b.id)}>
                {rodando === b.id ? <React.Fragment><span className="spin" aria-hidden="true"></span> Rodando…</React.Fragment> : <React.Fragment>{Ico.raio} Rodar agora</React.Fragment>}
              </button>
            </div>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}

/* ---------- Meu catálogo (custos + fiscal) ---------- */
function CatalogScreen() {
  const { reduzido, estatico } = React.useContext(MotionCtx);
  const itens = window.RADAR_DATA.catalogo;
  return (
    <motion.div className="screen-inner"
      initial={estatico ? false : reduzido ? { opacity: 0 } : { opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reduzido ? { duration: 0.15 } : { type: "spring", stiffness: 300, damping: 30 }}>
      <div className="silk">Base de custos</div>
      <h1 className="pg-titulo">Meu catálogo</h1>
      <p className="pg-sub">Custos e dados fiscais usados para calcular margem, veredito e prontidão de NF-e.</p>
      <div className="mod tbl" style={{ overflow: "hidden" }}>
        <div className="cat-head">
          <div className="silk">Código</div>
          <div className="silk">Produto</div>
          <div className="silk">NCM</div>
          <div className="silk">Custo unit.</div>
        </div>
        {itens.map((c) => (
          <div className="cat-row" key={c.cod}>
            <div className="cat-cod">{c.cod}</div>
            <div>{c.nome}<em className="cat-cat"> · {c.cat}</em></div>
            <div className="mono" style={{ color: c.ncm ? "var(--tinta-2)" : "var(--silk)", fontSize: "12.5px" }}>{c.ncm || "faltam dados"}</div>
            <div className="cat-custo">{fmtBRL(c.custo)}</div>
          </div>
        ))}
      </div>
    </motion.div>
  );
}

/* ---------- estados de carregando / erro ---------- */
function EstadoCarregando({ entrada }) {
  return (
    <motion.div variants={entrada} className="cards" aria-busy="true" aria-label="Carregando oportunidades">
      {[0, 1, 2].map((i) => (
        <div key={i} className="card-pregao mod skel">
          <span className="skel-bar w30"></span>
          <span className="skel-bar w70 big"></span>
          <span className="skel-bar w50"></span>
          <span className="skel-bar w90"></span>
        </div>
      ))}
    </motion.div>
  );
}
function EstadoErro({ entrada }) {
  return (
    <motion.div variants={entrada} className="estado-vazio mod erro">
      <div className="estado-ico" aria-hidden="true">{Ico.alerta}</div>
      <h3>Não foi possível consultar o PNCP</h3>
      <p>A API pública não respondeu (rate limit ou instabilidade). Respeitamos o limite de 1 req/s com backoff — tente novamente em instantes.</p>
      <button type="button" className="btn-rodar" onClick={() => location.reload()}>{Ico.raio} Tentar de novo</button>
    </motion.div>
  );
}

Object.assign(window, { FindScreen, CartaoPregao, BuscasScreen, CatalogScreen, EstadoCarregando, EstadoErro });
