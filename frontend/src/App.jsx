// RADAR DE PREGÕES — shell: sidebar (channel strip), navegação, estado global
// ligado à API real (FastAPI). Mutações com atualização otimista + reversão.
import React from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { api, adaptarItem } from "./api.js";
import { MotionCtx, Ico } from "./helpers.jsx";
import { FindScreen, BuscasScreen, CatalogScreen, EstadoCarregando, EstadoErro } from "./FindScreen.jsx";
import AnalysisScreen from "./AnalysisScreen.jsx";

const NAV = [
  { id: "find", rotulo: "Encontrar pregões", ico: "radar" },
  { id: "meus", rotulo: "Meus pregões", ico: "pasta" },
  { id: "buscas", rotulo: "Buscas salvas", ico: "raio" },
  { id: "catalogo", rotulo: "Meu catálogo (custos)", ico: "fader" },
];

const CONFIG_PADRAO = { regime_tributario: "simples", uf_origem: "" };

export default function App() {
  const sistemaReduzido = useReducedMotion();
  const reduzido = !!sistemaReduzido;
  // sob prefers-reduced-motion usamos o caminho estático (aparição instantânea;
  // fades curtos ficam por conta do CSS) — mesmo contrato do protótipo
  const semFramer = reduzido;
  const modo = React.useMemo(() => ({ reduzido, estatico: semFramer }), [reduzido, semFramer]);

  /* ---------- dados globais (API real) ---------- */
  const [catalogo, setCatalogo] = React.useState(null);       // null = carregando
  const [config, setConfig] = React.useState(null);
  const [buscas, setBuscas] = React.useState(null);
  const [pregoes, setPregoes] = React.useState(null);
  const [erros, setErros] = React.useState({});               // {pregoes, buscas, catalogo}
  const [detalhe, setDetalhe] = React.useState(null);         // {id, pregao, itens, habilitacao, erro}
  const [sincronizando, setSincronizando] = React.useState(false);

  const catalogoRef = React.useRef(null);
  React.useEffect(() => { catalogoRef.current = catalogo; }, [catalogo]);
  const promessaCatalogo = React.useRef(null);

  const produtosPorId = React.useMemo(() => {
    const m = {};
    (catalogo || []).forEach((p) => { m[p.id] = p; });
    return m;
  }, [catalogo]);
  const catalogoPorCod = React.useMemo(() => {
    const m = {};
    (catalogo || []).forEach((p) => { m[p.cod] = p; });
    return m;
  }, [catalogo]);

  /* ---------- toast de aviso (erros de mutação etc.) ---------- */
  const [aviso, setAviso] = React.useState(null);
  const avisoTimer = React.useRef(null);
  const avisar = React.useCallback((texto) => {
    setAviso(texto);
    clearTimeout(avisoTimer.current);
    avisoTimer.current = setTimeout(() => setAviso(null), 5500);
  }, []);

  /* ---------- carga inicial (paralela) + "Tentar de novo" ---------- */
  const carregarTudo = React.useCallback(() => {
    setErros({});
    setPregoes(null); setBuscas(null); setCatalogo(null);
    promessaCatalogo.current = api.listarCatalogo()
      .then((cs) => { setCatalogo(cs); return cs; })
      .catch((e) => { setCatalogo([]); setErros((o) => ({ ...o, catalogo: e.message || "erro" })); });
    api.lerConfig().then(setConfig).catch(() => setConfig(CONFIG_PADRAO));
    api.listarBuscas().then(setBuscas)
      .catch((e) => setErros((o) => ({ ...o, buscas: e.message || "erro" })));
    api.listarPregoes().then(setPregoes)
      .catch((e) => setErros((o) => ({ ...o, pregoes: e.message || "erro" })));
  }, []);
  React.useEffect(() => { carregarTudo(); }, [carregarTudo]);

  /* ---------- navegação ---------- */
  const [tela, setTela] = React.useState({ nome: "find" });
  // estado por pregão: { custos:{n:v}, matches:{n:match|null}, habilitacao:{id:status} }
  const [estadoPregoes, setEstadoPregoes] = React.useState({});
  const scrollRef = React.useRef(null);

  const mapaProdutos = () => {
    const m = {};
    (catalogoRef.current || []).forEach((p) => { m[p.id] = p; });
    return m;
  };

  const carregarDetalhe = React.useCallback((id) => {
    setDetalhe({ id, pregao: null, itens: null, habilitacao: null, erro: null });
    const pronto = promessaCatalogo.current || Promise.resolve();
    return pronto.catch(() => {}).then(() => {
      const mapa = mapaProdutos();
      return Promise.allSettled([
        api.pregao(id),
        api.carregarItens(id, mapa),
        api.carregarHabilitacao(id),
      ]).then(([rp, ri, rh]) => {
        const itensOk = ri.status === "fulfilled" ? ri.value : null;
        // pregão sem itens: busca automática na API do PNCP (sincronização
        // leve, sem PDF) — itens vêm da API pública, não de extração
        const precisaItens = rp.status === "fulfilled" && itensOk && itensOk.length === 0;
        setDetalhe((d) => {
          if (!d || d.id !== id) return d; // o usuário trocou de pregão no meio
          return {
            id,
            pregao: rp.status === "fulfilled" ? rp.value : null,
            itens: precisaItens ? null : itensOk,   // null = skeleton enquanto busca
            habilitacao: rh.status === "fulfilled" ? rh.value : null,
            erro:
              rp.status === "rejected" ? (rp.reason && rp.reason.message) || "erro"
              : ri.status === "rejected" ? (ri.reason && ri.reason.message) || "erro"
              : null,
          };
        });
        if (precisaItens) {
          api.sincronizarItens(id)
            .catch(() => {})   // PNCP fora: a recarga abaixo mostra lista vazia
            .then(() => Promise.allSettled([api.pregao(id), api.carregarItens(id, mapa)]))
            .then(([rp2, ri2]) => {
              setDetalhe((d) => {
                if (!d || d.id !== id) return d;
                return {
                  ...d,
                  pregao: rp2.status === "fulfilled" ? rp2.value : d.pregao,
                  itens: ri2.status === "fulfilled" ? ri2.value : [],
                };
              });
              // agregados novos (veredito/cobertura) também na lista
              if (rp2.status === "fulfilled") {
                setPregoes((ps) => (ps || []).map((p) => (p.id === id ? rp2.value : p)));
              }
            });
        }
        // PDF oficial a um clique mesmo sem sincronizar: se o pregão ainda não
        // tem arquivos no banco, busca só os metadados na API do PNCP
        const pregaoOk = rp.status === "fulfilled" ? rp.value : null;
        if (pregaoOk && !(pregaoOk.arquivos || []).length) {
          api.carregarArquivos(id).then((arqs) => {
            if (!arqs.length) return;
            setDetalhe((d) => {
              if (!d || d.id !== id || !d.pregao) return d;
              return { ...d, pregao: { ...d.pregao, arquivos: arqs } };
            });
          }).catch(() => {}); // melhor-esforço; o link "Ver no PNCP" cobre
        }
      });
    });
  }, []);

  const abrirPregao = (id) => {
    setTela({ nome: "analise", pregaoId: id, origem: tela.nome });
    carregarDetalhe(id);
    // marcar como visto (flag "novo" do monitoramento)
    const p = (pregoes || []).find((x) => x.id === id);
    if (p && p.novo) {
      setPregoes((ps) => ps.map((x) => (x.id === id ? { ...x, novo: false } : x)));
      api.atualizarPregao(id, { novo: false }).catch(() => {});
    }
  };

  /* ---------- estado local de edição (recálculo ao vivo) ---------- */
  // valor === undefined remove a chave (volta a valer o dado do backend)
  const mutarEstado = (pregaoId, campo, chave, valor) => {
    setEstadoPregoes((o) => {
      const ep = o[pregaoId] || {};
      const grupo = { ...(ep[campo] || {}) };
      if (valor === undefined) delete grupo[chave];
      else grupo[chave] = valor;
      return { ...o, [pregaoId]: { ...ep, [campo]: grupo } };
    });
  };

  const idAtivo = tela.nome === "analise" ? tela.pregaoId : null;
  const estadoAtivo = (idAtivo != null && estadoPregoes[idAtivo]) || {};

  const setCusto = (n, valor) => { if (idAtivo != null) mutarEstado(idAtivo, "custos", n, valor); };
  const setLance = (n, valor) => { if (idAtivo != null) mutarEstado(idAtivo, "lances", n, valor); };

  /* ---------- mutações (otimista → API → reverte em erro) ---------- */

  // aplica a resposta {item, pregao(agregados)} do match/custo no detalhe
  // (item adaptado + agregados) e na lista de pregões (agregados no cartão)
  const aplicarAgregados = (pregaoId, ag, adaptado) => {
    const fundir = (alvo) => ({
      ...alvo,
      agregados: {
        ...alvo.agregados,
        veredito: ag.veredito,
        lucroPotencial: ag.lucro_potencial,
        margemMedia: ag.margem_media,
        cobertura: ag.cobertura,
        itensTotal: ag.itens_total,
        itensConfirmados: ag.itens_confirmados,
        itensComCusto: ag.itens_com_custo,
      },
    });
    setDetalhe((d) => {
      if (!d || d.id !== pregaoId) return d;
      const itens = adaptado && d.itens
        ? d.itens.map((i) => (i.id === adaptado.id ? adaptado : i)) : d.itens;
      return { ...d, itens, pregao: d.pregao ? fundir(d.pregao) : d.pregao };
    });
    setPregoes((ps) => (ps ? ps.map((p) => (p.id === pregaoId ? fundir(p) : p)) : ps));
  };

  // custo unitário POR ITEM (P3): ao vivo via setCusto; no blur/Enter grava
  // custo_manual (override local do pregão — NÃO toca o catálogo). A resposta
  // traz {item, pregao(agregados)}; valor null limpa e volta ao catálogo.
  const confirmarCustoItem = (item, valor) => {
    const pregaoId = idAtivo;
    if (pregaoId == null) return;
    api.definirCustoItem(item.id, valor)
      .then(({ item: cru, pregao: ag }) => {
        const adaptado = adaptarItem(cru, mapaProdutos());
        aplicarAgregados(pregaoId, ag, adaptado);
        // dado do servidor agora carrega o custo — limpa o override ao vivo
        mutarEstado(pregaoId, "custos", item.n, undefined);
      })
      .catch(() => {
        mutarEstado(pregaoId, "custos", item.n, undefined);
        avisar("Não foi possível salvar o custo — valor revertido.");
      });
  };

  // limpar custo manual (×): volta ao custo do catálogo se houver match
  const limparCustoItem = (item) => confirmarCustoItem(item, null);

  // lance previsto POR ITEM (P4): ao vivo via setLance; no blur/Enter grava
  // lance_previsto (override local do pregão). A resposta traz {item,
  // pregao(agregados)}; valor null limpa e volta ao deságio/teto. Espelho do
  // custo manual.
  const confirmarLanceItem = (item, valor) => {
    const pregaoId = idAtivo;
    if (pregaoId == null) return;
    api.definirLanceItem(item.id, valor)
      .then(({ item: cru, pregao: ag }) => {
        const adaptado = adaptarItem(cru, mapaProdutos());
        aplicarAgregados(pregaoId, ag, adaptado);
        // dado do servidor agora carrega o lance — limpa o override ao vivo
        mutarEstado(pregaoId, "lances", item.n, undefined);
      })
      .catch(() => {
        mutarEstado(pregaoId, "lances", item.n, undefined);
        avisar("Não foi possível salvar o lance — valor revertido.");
      });
  };

  // limpar lance (×): volta ao preço por deságio/teto
  const limparLanceItem = (item) => confirmarLanceItem(item, null);

  // catálogo (tela Meu catálogo): edição inline do custo
  const salvarCustoProduto = (produto, valor) => {
    const anterior = produto.custo;
    setCatalogo((cs) => (cs || []).map((c) => (c.id === produto.id ? { ...c, custo: valor } : c)));
    api.atualizarProduto(produto.id, { custo_unit: valor }).catch(() => {
      setCatalogo((cs) => (cs || []).map((c) => (c.id === produto.id ? { ...c, custo: anterior } : c)));
      avisar("Não foi possível salvar o custo — valor revertido.");
    });
  };

  // matching human-in-the-loop: a resposta da API traz {item, pregao(agregados)}
  const definirMatch = (item, match) => {
    const pregaoId = idAtivo;
    if (pregaoId == null) return;
    const ep = estadoPregoes[pregaoId] || {};
    const anterior = ep.matches && ep.matches[item.n] !== undefined ? ep.matches[item.n] : undefined;
    mutarEstado(pregaoId, "matches", item.n, match);
    const produto = match ? catalogoPorCod[match.cod] : null;
    api.definirMatch(item.id, produto ? produto.id : null, !!(match && match.confirmado))
      .then(({ item: cru, pregao: ag }) => {
        const adaptado = adaptarItem(cru, mapaProdutos());
        aplicarAgregados(pregaoId, ag, adaptado);
        // o item do servidor agora carrega o match — limpa o override local
        mutarEstado(pregaoId, "matches", item.n, undefined);
      })
      .catch(() => {
        mutarEstado(pregaoId, "matches", item.n, anterior);
        avisar("Não foi possível salvar o match — alteração revertida.");
      });
  };

  // checklist de habilitação: Tenho / Pendente / Não tenho
  const setHabil = (h, status) => {
    const pregaoId = idAtivo;
    if (pregaoId == null) return;
    const ep = estadoPregoes[pregaoId] || {};
    const anterior = ep.habilitacao && ep.habilitacao[h.id] !== undefined ? ep.habilitacao[h.id] : h.status;
    mutarEstado(pregaoId, "habilitacao", h.id, status);
    api.definirStatusHabilitacao(h.id, status).catch(() => {
      mutarEstado(pregaoId, "habilitacao", h.id, anterior);
      avisar("Não foi possível salvar o status do requisito — revertido.");
    });
  };

  // margem alvo (P3): guia da simulação dos itens sem custo. Persiste na
  // config e recarrega os itens do pregão ativo (simulação recalculada no
  // backend). Otimista no config; reverte em erro.
  const definirMargemAlvo = (valor) => {
    const anterior = config;
    const v = Math.max(0, Math.min(0.95, valor));
    setConfig((c) => ({ ...(c || CONFIG_PADRAO), margem_alvo: String(v) }));
    api.atualizarConfig({ margem_alvo: String(v) })
      .then((cfg) => {
        setConfig(cfg);
        const id = idAtivo;
        if (id != null) {
          api.carregarItens(id, mapaProdutos())
            .then((itens) => setDetalhe((d) => (d && d.id === id ? { ...d, itens } : d)))
            .catch(() => {});
        }
      })
      .catch(() => {
        setConfig(anterior);
        avisar("Não foi possível salvar a margem alvo — revertido.");
      });
  };

  // deságio esperado (P4): base do preço esperado de TODOS os itens. Persiste
  // na config e o backend re-analisa todos os pregões com itens (agregados de
  // cartões/funil). Por isso, além de recarregar os itens do pregão ativo,
  // refaz o fetch da LISTA de pregões e do DETALHE aberto. Otimista; reverte.
  const definirDesagio = (valor) => {
    const anterior = config;
    const v = Math.max(0, Math.min(0.90, valor));
    setConfig((c) => ({ ...(c || CONFIG_PADRAO), desagio_esperado: String(v) }));
    api.atualizarConfig({ desagio_esperado: String(v) })
      .then((cfg) => {
        setConfig(cfg);
        // agregados de todos mudaram no backend → atualiza a lista inteira
        api.listarPregoes().then(setPregoes).catch(() => {});
        const id = idAtivo;
        if (id != null) {
          // itens (preço esperado por item) + pregão (agregados persistidos)
          Promise.allSettled([
            api.carregarItens(id, mapaProdutos()),
            api.pregao(id),
          ]).then(([ri, rp]) => {
            setDetalhe((d) => {
              if (!d || d.id !== id) return d;
              return {
                ...d,
                itens: ri.status === "fulfilled" ? ri.value : d.itens,
                pregao: rp.status === "fulfilled" ? rp.value : d.pregao,
              };
            });
          });
        }
      })
      .catch(() => {
        setConfig(anterior);
        avisar("Não foi possível salvar o deságio esperado — revertido.");
      });
  };

  // regime tributário (alterna CSOSN↔CST em toda a aba Fiscal)
  const setRegime = (regime) => {
    const anterior = config;
    setConfig((c) => ({ ...(c || CONFIG_PADRAO), regime_tributario: regime }));
    api.atualizarConfig({ regime_tributario: regime })
      .then(setConfig)
      .catch(() => {
        setConfig(anterior);
        avisar("Não foi possível trocar o regime tributário — revertido.");
      });
  };

  // sincronizar pregão (itens + arquivos + habilitação) — pode levar minutos
  const sincronizarPregao = () => {
    const id = idAtivo;
    if (id == null || sincronizando) return;
    setSincronizando(true);
    api.sincronizar(id)
      .then(() => Promise.all([
        carregarDetalhe(id),
        api.listarPregoes().then(setPregoes).catch(() => {}),
      ]))
      .catch((e) => avisar("Sincronização falhou: " + (e.message || "erro inesperado")))
      .finally(() => setSincronizando(false));
  };

  // buscas salvas
  const rodarBusca = (id) =>
    api.rodarBusca(id)
      .then((r) => {
        avisar(r && typeof r.novos === "number"
          ? "Busca concluída — " + r.novos + (r.novos === 1 ? " pregão novo." : " pregões novos.")
          : "Busca concluída.");
        return Promise.all([
          api.listarBuscas().then(setBuscas),
          api.listarPregoes().then(setPregoes),
        ]).catch(() => {});
      })
      .catch((e) => {
        avisar(e.status === 503
          ? "PNCP indisponível no momento (rate limit ou instabilidade) — tente de novo em instantes."
          : "Não foi possível rodar a busca: " + (e.message || "erro"));
      });

  const criarBusca = (corpo) =>
    api.criarBusca(corpo)
      .then(() => api.listarBuscas().then(setBuscas))
      .catch((e) => {
        avisar("Não foi possível criar a busca: " + (e.message || "erro"));
        throw e;
      });

  const alternarBusca = (b) => {
    const alvo = !b.ativo;
    setBuscas((bs) => (bs || []).map((x) => (x.id === b.id ? { ...x, ativo: alvo } : x)));
    api.atualizarBusca(b.id, { ativo: alvo }).catch(() => {
      setBuscas((bs) => (bs || []).map((x) => (x.id === b.id ? { ...x, ativo: b.ativo } : x)));
      avisar("Não foi possível atualizar a busca — revertido.");
    });
  };

  // importar pregão da busca AO VIVO do PNCP para o radar (estado global)
  const importarPregao = (numeroControle, hit) =>
    api.importarPregao(numeroControle, hit)
      .then((pregao) => {
        setPregoes((ps) => {
          const lista = ps || [];
          // idempotente: se já está na lista, não duplica (atualiza no lugar)
          if (lista.some((p) => p.id === pregao.id)) {
            return lista.map((p) => (p.id === pregao.id ? pregao : p));
          }
          return [pregao, ...lista];
        });
        return pregao;
      })
      .catch((e) => {
        avisar(e.status === 503
          ? "PNCP indisponível no momento — tente de novo em instantes."
          : "Não foi possível adicionar ao radar: " + (e.message || "erro"));
        throw e;
      });

  // catálogo
  const criarProduto = (corpo) =>
    api.criarProduto(corpo)
      .then(() => api.listarCatalogo().then(setCatalogo))
      .catch((e) => {
        avisar("Não foi possível adicionar o produto: " + (e.message || "erro"));
        throw e;
      });

  /* ---------- funil de disputa (P2) — otimista → API → reverte ---------- */
  const mudarPipeline = (id, campos) => {
    const anterior = (pregoes || []).find((p) => p.id === id);
    const anteriorDetalhe = detalhe && detalhe.id === id ? detalhe.pregao : null;
    const otimista = (p) => ({
      ...p,
      statusPipeline: campos.status_pipeline !== undefined ? campos.status_pipeline : p.statusPipeline,
      dataDisputa: campos.data_disputa !== undefined ? campos.data_disputa : p.dataDisputa,
      valorFinal: campos.valor_final !== undefined ? campos.valor_final : p.valorFinal,
      salvo: campos.salvo !== undefined ? campos.salvo : p.salvo,
    });
    setPregoes((ps) => (ps || []).map((p) => (p.id === id ? otimista(p) : p)));
    // o detalhe também é otimista — os controles da Análise são controlados
    // por ele e "piscariam" esperando a API (achado do review)
    setDetalhe((d) => (d && d.id === id && d.pregao
      ? { ...d, pregao: otimista(d.pregao) } : d));
    return api.atualizarPregao(id, campos).then((atualizado) => {
      setPregoes((ps) => (ps || []).map((p) => (p.id === id ? atualizado : p)));
      setDetalhe((d) => (d && d.id === id && d.pregao
        ? { ...d, pregao: { ...d.pregao, ...atualizado } } : d));
      return atualizado;
    }).catch((e) => {
      setPregoes((ps) => (ps || []).map((p) => (p.id === id ? anterior : p)));
      setDetalhe((d) => (d && d.id === id && anteriorDetalhe
        ? { ...d, pregao: anteriorDetalhe } : d));
      avisar("Não foi possível atualizar o funil — revertido.");
      throw e;
    });
  };

  const salvarPregao = (id, salvo) => mudarPipeline(id, { salvo });

  /* ---------- pregão ativo (detalhe + lista como fallback do cabeçalho) ---------- */
  const pregaoLista = idAtivo != null && pregoes ? pregoes.find((p) => p.id === idAtivo) : null;
  const detalheDoAtivo = detalhe && detalhe.id === idAtivo ? detalhe : null;
  const pregaoAtivo = idAtivo != null
    ? (detalheDoAtivo && detalheDoAtivo.pregao
        ? { ...detalheDoAtivo.pregao, itens: detalheDoAtivo.itens, habilitacao: detalheDoAtivo.habilitacao }
        : pregaoLista
          ? { ...pregaoLista, itens: detalheDoAtivo ? detalheDoAtivo.itens : null, habilitacao: detalheDoAtivo ? detalheDoAtivo.habilitacao : null }
          : null)
    : null;

  // P5: margem alvo da config (guia o potencial aderente exibido nos cartões;
  // só cenário, nunca promessa). default 0.20 quando inválida/ausente.
  const margemAlvoConfig = (() => {
    const v = parseFloat((config || {}).margem_alvo);
    return Number.isFinite(v) ? v : 0.2;
  })();

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
          : (NAV.find((n) => n.id === tela.nome) || {}).rotulo || tela.nome
      }
      {...transTela}
    >
      {tela.nome === "find" && (
        <FindScreen aoAbrir={abrirPregao} apenasSalvos={false}
          pregoes={pregoes} erro={erros.pregoes} recarregar={carregarTudo}
          aoImportar={importarPregao} margemAlvo={margemAlvoConfig} />
      )}
      {tela.nome === "meus" && (
        <FindScreen aoAbrir={abrirPregao} apenasSalvos={true}
          pregoes={pregoes} erro={erros.pregoes} recarregar={carregarTudo}
          mudarPipeline={mudarPipeline} margemAlvo={margemAlvoConfig} />
      )}
      {tela.nome === "buscas" && (
        <BuscasScreen buscas={buscas} erro={erros.buscas} recarregar={carregarTudo}
          rodar={rodarBusca} criar={criarBusca} alternar={alternarBusca} />
      )}
      {tela.nome === "catalogo" && (
        <CatalogScreen catalogo={catalogo} erro={erros.catalogo} recarregar={carregarTudo}
          salvarCusto={salvarCustoProduto} criar={criarProduto} />
      )}
      {tela.nome === "analise" && pregaoAtivo && (
        <AnalysisScreen
          pregao={pregaoAtivo}
          estado={estadoAtivo}
          setCusto={setCusto}
          confirmarCusto={confirmarCustoItem}
          limparCusto={limparCustoItem}
          definirMargemAlvo={definirMargemAlvo}
          setLance={setLance}
          confirmarLance={confirmarLanceItem}
          limparLance={limparLanceItem}
          definirDesagio={definirDesagio}
          setMatch={definirMatch}
          setHabil={setHabil}
          config={config || CONFIG_PADRAO}
          setRegime={setRegime}
          catalogo={catalogo || []}
          catalogoPorCod={catalogoPorCod}
          sincronizar={sincronizarPregao}
          sincronizando={sincronizando}
          erroDetalhe={detalheDoAtivo ? detalheDoAtivo.erro : null}
          recarregarDetalhe={() => carregarDetalhe(idAtivo)}
          mudarPipeline={mudarPipeline}
          salvarPregao={salvarPregao}
          voltar={() => setTela({ nome: tela.origem && tela.origem !== "analise" ? tela.origem : "find" })}
          scrollRef={scrollRef}
          meterVariant="led"
        />
      )}
      {tela.nome === "analise" && !pregaoAtivo && (
        <div className="screen-inner">
          {detalheDoAtivo && detalheDoAtivo.erro
            ? <EstadoErro mensagem={detalheDoAtivo.erro} recarregar={() => carregarDetalhe(idAtivo)} />
            : <EstadoCarregando />}
        </div>
      )}
    </motion.div>
  );

  return (
    <MotionCtx.Provider value={modo}>
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
            Ferramenta de apoio à decisão. O edital oficial e os valores estão no PNCP.
            Confira antes de dar lance.
          </span>
        </div>

        {aviso && (
          <div className="toast" role="alert">
            <span className="aviso-led" aria-hidden="true"></span>
            <span>{aviso}</span>
          </div>
        )}
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
            aria-current={tela.nome === n.id ? "page" : undefined}
            onClick={() => irPara(n.id)}
          >
            {Ico[n.ico]}
            {n.rotulo}
          </button>
        ))}
      </nav>
      <div className="sidebar-foot">PNCP · dados reais</div>
    </motion.aside>
  );
}
