// RADAR DE PREGÕES — shell: sidebar (channel strip), navegação, aviso fixo, tweaks
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "medidor": "LED segmentado",
  "densidade": "Confortável",
  "estado": "Dados",
  "chassi": "#E4E7E1"
}/*EDITMODE-END*/;

const NAV = [
  { id: "find", rotulo: "Encontrar pregões", ico: "radar" },
  { id: "meus", rotulo: "Meus pregões", ico: "pasta" },
  { id: "buscas", rotulo: "Buscas salvas", ico: "raio" },
  { id: "catalogo", rotulo: "Meu catálogo (custos)", ico: "fader" },
];

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const sistemaReduzido = useReducedMotion();
  // estático pode começar false e virar true se os frames congelarem depois do boot (watchdog)
  const [estatico, setEstatico] = React.useState(window.__RAF_OK === false);
  const reduzido = !!sistemaReduzido || estatico;
  // Sob PRM, o framer v10 UMD não completa mounts em forma de objeto nem exits do
  // AnimatePresence (mesmo com rAF ativo) — então reduzido usa o MESMO caminho
  // estático do framer; os "fades curtos" de reduced-motion são CSS (confiável).
  const semFramer = reduzido;
  const modo = React.useMemo(() => ({ reduzido, estatico: semFramer }), [reduzido, semFramer]);

  // watchdog: heartbeat de rAF; se os frames pararem (>900ms), troca para modo estático
  React.useEffect(() => {
    if (estatico) return;
    let ultimo = performance.now();
    let parado = false;
    const loop = () => {
      if (parado) return;
      ultimo = performance.now();
      requestAnimationFrame(loop);
    };
    const raf = requestAnimationFrame(loop);
    const onVis = () => {
      ultimo = performance.now();
    };
    document.addEventListener("visibilitychange", onVis);
    const iv = setInterval(() => {
      // aba oculta tem rAF pausado por design — só conta como congelado se visível
      if (!document.hidden && performance.now() - ultimo > 900) {
        window.__RAF_OK = false;
        setEstatico(true);
      }
    }, 450);
    return () => {
      parado = true;
      cancelAnimationFrame(raf);
      clearInterval(iv);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [estatico]);

  const [tela, setTela] = React.useState({ nome: "find" });
  // estado por pregão: { custos:{n:v}, matches:{n:match|null}, habilitacao:{id:status} }
  const [estadoPregoes, setEstadoPregoes] = React.useState({});
  // config fiscal (regime alterna CSOSN↔CST)
  const [config, setConfig] = React.useState(window.RADAR_DATA.config);
  const scrollRef = React.useRef(null);

  React.useEffect(() => {
    document.documentElement.style.setProperty("--aluminio", t.chassi);
    document.documentElement.style.setProperty("--row-pad", t.densidade === "Compacta" ? "8px" : "13px");
    document.body.style.background = t.chassi;
  }, [t.chassi, t.densidade]);

  const abrirPregao = (id) => setTela({ nome: "analise", pregaoId: id, origem: tela.nome });
  const pregaoAtivo = tela.nome === "analise" ? window.RADAR_DATA.pregoes.find((p) => p.id === tela.pregaoId) : null;
  const estadoAtivo = (pregaoAtivo && estadoPregoes[pregaoAtivo.id]) || {};

  const mutarEstado = (campo, chave, valor) => {
    if (!pregaoAtivo) return;
    setEstadoPregoes((o) => {
      const ep = o[pregaoAtivo.id] || {};
      return { ...o, [pregaoAtivo.id]: { ...ep, [campo]: { ...(ep[campo] || {}), [chave]: valor } } };
    });
  };
  const setCusto = (n, valor) => mutarEstado("custos", n, valor);
  const setMatch = (n, match) => mutarEstado("matches", n, match);
  const setHabil = (id, status) => mutarEstado("habilitacao", id, status);
  const setRegime = (regime) => setConfig((c) => ({ ...c, regime_tributario: regime }));

  const meterVariant = t.medidor === "Barra contínua" ? "continua" : "led";
  const estadoUI = t.estado === "Carregando" ? "carregando" : t.estado === "Erro" ? "erro" : "dados";

  const chaveTela = tela.nome === "analise" ? "analise-" + tela.pregaoId : tela.nome;
  const transTela = semFramer
    ? {}
    : {
        initial: { opacity: 0, x: 18 },
        animate: { opacity: 1, x: 0 },
        exit: { opacity: 0, x: -14 },
        transition: { type: "spring", stiffness: 300, damping: 32 },
      };

  const telaConteudo = (
    <motion.div
      key={chaveTela}
      className="screen"
      ref={scrollRef}
      data-screen-label={
        tela.nome === "analise"
          ? "Análise — " + (pregaoAtivo ? pregaoAtivo.titulo : "")
          : NAV.find((n) => n.id === tela.nome)?.rotulo || tela.nome
      }
      {...transTela}
    >
      {tela.nome === "find" && <FindScreen aoAbrir={abrirPregao} apenasSalvos={false} estadoUI={estadoUI} />}
      {tela.nome === "meus" && <FindScreen aoAbrir={abrirPregao} apenasSalvos={true} estadoUI={estadoUI} />}
      {tela.nome === "buscas" && <BuscasScreen aoAbrir={abrirPregao} />}
      {tela.nome === "catalogo" && <CatalogScreen />}
      {tela.nome === "analise" && pregaoAtivo && (
        <AnalysisScreen
          pregao={pregaoAtivo}
          estado={estadoAtivo}
          setCusto={setCusto}
          setMatch={setMatch}
          setHabil={setHabil}
          config={config}
          setRegime={setRegime}
          voltar={() => setTela({ nome: tela.origem && tela.origem !== "analise" ? tela.origem : "find" })}
          scrollRef={scrollRef}
          meterVariant={meterVariant}
        />
      )}
    </motion.div>
  );

  return (
    <MotionCtx.Provider value={modo}>
      {/* key força remount ao trocar de modo — limpa estilos inline pendentes do framer */}
      <div className="app" key={semFramer ? "estatico" : "animado"}>
        <Sidebar tela={tela} irPara={(id) => setTela({ nome: id })} semFramer={semFramer} />
        <main className="main">
          {semFramer ? (
            telaConteudo
          ) : (
            <AnimatePresence mode="wait" initial={false}>
              {telaConteudo}
            </AnimatePresence>
          )}
        </main>

        <div className="aviso" role="note" aria-label="Aviso de validação">
          <span className="aviso-led" aria-hidden="true"></span>
          <span>
            <strong>Ferramenta de apoio à decisão. Não é consultoria.</strong> Os valores e o edital oficial
            estão sempre no PNCP. Confira antes de dar lance.
          </span>
        </div>

        <TweaksPanel>
          <TweakSection label="Assinatura" />
          <TweakRadio label="Medidor" value={t.medidor} options={["LED segmentado", "Barra contínua"]} onChange={(v) => setTweak("medidor", v)} />
          <TweakSection label="Console" />
          <TweakRadio label="Densidade da tabela" value={t.densidade} options={["Confortável", "Compacta"]} onChange={(v) => setTweak("densidade", v)} />
          <TweakColor label="Chassi (fundo)" value={t.chassi} options={["#E4E7E1", "#E8E6E0", "#DEE3E4"]} onChange={(v) => setTweak("chassi", v)} />
          <TweakSection label="Estado das listas" />
          <TweakRadio label="Demonstrar" value={t.estado} options={["Dados", "Carregando", "Erro"]} onChange={(v) => setTweak("estado", v)} />
        </TweaksPanel>
      </div>
    </MotionCtx.Provider>
  );
}

function Sidebar({ tela, irPara, semFramer }) {
  const entrada = semFramer
    ? {}
    : {
        initial: { opacity: 0, x: -22 },
        animate: { opacity: 1, x: 0 },
        transition: { type: "spring", stiffness: 260, damping: 26 },
      };
  return (
    <motion.aside className="sidebar" {...entrada} aria-label="Navegação principal">
      <div className="brand">
        <span className="brand-name">
          Radar de
          <br className="desktop-only" /> Pregões
        </span>
        <span className="brand-sub">
          <span className="brand-led" aria-hidden="true"></span>
          PNCP · Lei 14.133
        </span>
      </div>
      <nav style={{ display: "flex", flexDirection: "inherit", gap: "inherit", flex: "none" }} aria-label="Seções">
        {NAV.map((n) => (
          <button
            key={n.id}
            type="button"
            className={"nav-item" + (tela.nome === n.id || (tela.nome === "analise" && tela.origem === n.id) ? " ativa" : "")}
            aria-disabled={n.desabilitado ? "true" : undefined}
            aria-current={tela.nome === n.id ? "page" : undefined}
            onClick={() => {
              if (!n.desabilitado) irPara(n.id);
            }}
          >
            {Ico[n.ico]}
            {n.rotulo}
            {n.desabilitado && <span className="chip-breve">EM BREVE</span>}
          </button>
        ))}
      </nav>
      <div className="sidebar-foot">mock · v0.2</div>
    </motion.aside>
  );
}

/* boot: detecta se rAF está disponível antes de renderizar.
   Exige 2 frames consecutivos (iframes ocultos às vezes disparam 1 e congelam);
   o watchdog no App cobre congelamento pós-boot. */
(function boot() {
  const start = () => {
    if (window.__BOOTED) return;
    window.__BOOTED = true;
    if (window.__RAF_OK === undefined) window.__RAF_OK = false;
    ReactDOM.createRoot(document.getElementById("root")).render(<App />);
  };
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      window.__RAF_OK = true;
      start();
    });
  });
  setTimeout(start, 450);
})();
