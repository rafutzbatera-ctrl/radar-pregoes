// RADAR DE PREGÕES — helpers: cálculo, formatação, medidor-assinatura, números animados
import React from "react";
import { animate as fmAnimate } from "framer-motion";

/* ---------- contexto de motion ----------
   reduzido: sem springs/parallax (prefers-reduced-motion)
   estatico: render direto no estado final (mesmo caminho do reduzido) */
export const MotionCtx = React.createContext({ reduzido: false, estatico: false });

/* ---------- formatação pt-BR ---------- */
const _brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
export const fmtBRL = (v) => _brl.format(v);
export const fmtPct = (v) =>
  v.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + "%";
export const parseBRL = (str) => {
  const limpo = String(str).replace(/[R$\s.]/g, "").replace(",", ".");
  const v = parseFloat(limpo);
  return isNaN(v) ? null : v;
};

/* ---------- cálculo de viabilidade ---------- */
// status por item: <0 prejuízo (clip) · 0–28% atenção (pico) · ≥28% saudável (sinal)
export function statusItem(margemPct) {
  if (margemPct < 0) return "clip";
  if (margemPct < 28) return "pico";
  return "sinal";
}

export const linkPncp = (p) =>
  "https://pncp.gov.br/app/editais/" + p.cnpj + "/" + p.ano + "/" + p.seq;

// o backend grava "nao_vale"; a UI/CSS usa "nao"
export const normalizarVeredito = (v) => (v === "nao_vale" ? "nao" : v || null);

// veredito (regra do CLAUDE.md §6.2):
// vale: margem ≥20% E cobertura ≥60% E lucro ≥ R$ 1.000
// não vale: margem <8% OU lucro < R$ 300 · senão: talvez
// Só item com match CONFIRMADO entra na conta (human-in-the-loop).
// catalogoPorCod vem da API (App) — o mock morreu.
export function analisar(pregao, estado, catalogoPorCod, previa) {
  const custos = (estado && estado.custos) || {};
  const matches = (estado && estado.matches) || {};
  const cat = catalogoPorCod || {};
  const itens = (pregao.itens || []).map((it) => {
    const m = matches[it.n] !== undefined ? matches[it.n] : it.match;
    if (it.sigiloso) {
      return { ...it, matchAtual: m, produto: m ? cat[m.cod] || null : null, custo: null, coberto: false, margemPct: null, lucro: null, status: "sigiloso" };
    }
    if (!m || !cat[m.cod]) {
      return { ...it, matchAtual: m || null, produto: null, custo: null, coberto: false, margemPct: null, lucro: null, status: "fora" };
    }
    const produto = cat[m.cod];
    const custo = custos[it.n] !== undefined ? custos[it.n] : produto.custo;
    const semValor = it.unit == null || !it.unit;
    const margemPct = semValor ? null : ((it.unit - custo) / it.unit) * 100;
    const lucro = semValor ? null : (it.unit - custo) * it.qtd;
    const confirmado = m.confirmado || !!previa;
    if (!confirmado) {
      return { ...it, matchAtual: m, produto, custo, coberto: false, margemPct, lucro, status: "sugerido" };
    }
    if (semValor) {
      // confirmado mas sem valor oficial — fora da conta, visível
      return { ...it, matchAtual: m, produto, custo, coberto: false, margemPct: null, lucro: null, status: "fora" };
    }
    return { ...it, matchAtual: m, produto, custo, coberto: true, margemPct, lucro, status: statusItem(margemPct) };
  });
  const cobertos = itens.filter((i) => i.coberto);
  const sugeridos = itens.filter((i) => i.status === "sugerido").length;
  const lucroTotal = cobertos.reduce((s, i) => s + i.lucro, 0);
  const receitaCoberta = cobertos.reduce((s, i) => s + i.unit * i.qtd, 0);
  const margemAgregada = receitaCoberta > 0 ? (lucroTotal / receitaCoberta) * 100 : 0;
  const cobertura = itens.length > 0 ? cobertos.length / itens.length : 0;
  let veredito;
  // sem item confirmado não há análise — veredito nulo, como no backend
  // ("não vale" para pregão não analisado seria chute, e chute é proibido)
  if (cobertos.length === 0) veredito = null;
  else if (margemAgregada >= 20 && cobertura >= 0.6 && lucroTotal >= 1000) veredito = "vale";
  else if (margemAgregada < 8 || lucroTotal < 300) veredito = "nao";
  else veredito = "talvez";
  return {
    itens, lucroTotal, receitaCoberta, margemAgregada, sugeridos,
    cobertos: cobertos.length, total: itens.length, cobertura, veredito,
  };
}

/* ---------- fiscal / prontidão NF-e (CLAUDE.md §6.4 — sempre sugestão) ---------- */
export function fiscalDoItem(item, pregao, config) {
  const produto = item.produto;
  const ncm = item.ncmPncp || (produto && produto.ncm) || null;
  const ncmFonte = item.ncmPncp ? "PNCP" : produto && produto.ncm ? "catálogo" : null;
  const cfop = pregao.uf === config.uf_origem ? "5102" : "6102";
  const cstCsosn = produto ? (config.regime_tributario === "simples" ? produto.csosn : produto.cst) : null;
  const cstRotulo = config.regime_tributario === "simples" ? "CSOSN" : "CST";
  const pronto = !!(ncm && item.unidade && cstCsosn);
  return { ncm, ncmFonte, cfop, cstCsosn, cstRotulo, pronto };
}

export const CATEGORIA_TXT = {
  juridica: "Jurídica",
  fiscal: "Fiscal",
  tecnica: "Técnica",
  economico_financeira: "Econômico-financeira",
  proposta: "Proposta",
  outros: "Outros",
};

export const VEREDITO_TXT = { vale: "Vale", talvez: "Talvez", nao: "Não vale" };

/* ---------- número com tween suave ---------- */
export function useTweenNumber(value, dur = 0.65) {
  const { reduzido } = React.useContext(MotionCtx);
  const [mostrado, setMostrado] = React.useState(value);
  const atual = React.useRef(value);
  React.useEffect(() => {
    if (reduzido) {
      atual.current = value;
      setMostrado(value);
      return;
    }
    const ctrl = fmAnimate(atual.current, value, {
      duration: dur,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (v) => {
        atual.current = v;
        setMostrado(v);
      },
    });
    return () => ctrl.stop();
  }, [value, reduzido]);
  return mostrado;
}

export function NumBRL({ value, className }) {
  const v = useTweenNumber(value);
  return <span className={className}>{fmtBRL(v)}</span>;
}
export function NumPct({ value, className }) {
  const v = useTweenNumber(value);
  return <span className={className}>{fmtPct(v)}</span>;
}

/* ---------- MEDIDOR DE VIABILIDADE (elemento-assinatura) ----------
   Escada de LEDs estilo VU master, escala em % de margem:
   −10 ─ 8 (clip / não vale) ─ 20 (pico / talvez) ─ 40 (sinal / vale) */
const MED_MIN = -10, MED_MAX = 40, MED_N = 32;
const ZONAS = [
  { ate: 8, cor: "var(--clip)", corLed: "#E5604F" },
  { ate: 20, cor: "var(--pico)", corLed: "#EFB02A" },
  { ate: Infinity, cor: "var(--sinal)", corLed: "#35C580" },
];
const corDaPos = (pos) => ZONAS.find((z) => pos < z.ate).corLed;

export function Medidor({ valor, variante = "led", delay = 0 }) {
  const { reduzido } = React.useContext(MotionCtx);
  const alvo = Math.max(MED_MIN, Math.min(MED_MAX, valor));
  const [mostrado, setMostrado] = React.useState(reduzido ? alvo : MED_MIN);
  const atual = React.useRef(reduzido ? alvo : MED_MIN);
  React.useEffect(() => {
    if (reduzido) {
      atual.current = alvo;
      setMostrado(alvo);
      return;
    }
    // spring de VU: sobe com overshoot contido e assenta
    const ctrl = fmAnimate(atual.current, alvo, {
      type: "spring",
      stiffness: 64,
      damping: 12.5,
      mass: 1.1,
      delay,
      restDelta: 0.01,
      onUpdate: (v) => {
        atual.current = v;
        setMostrado(v);
      },
    });
    return () => ctrl.stop();
  }, [alvo, reduzido]);

  const frac = Math.max(0, Math.min(1, (mostrado - MED_MIN) / (MED_MAX - MED_MIN)));
  const ticks = [-10, 0, 8, 20, 40];
  const pos = (v) => ((v - MED_MIN) / (MED_MAX - MED_MIN)) * 100;

  let leds = null;
  if (variante === "led") {
    const acesos = frac * MED_N;
    leds = (
      <div className="medidor-leds" aria-hidden="true">
        {Array.from({ length: MED_N }, (_, i) => {
          const centro = MED_MIN + ((i + 0.5) / MED_N) * (MED_MAX - MED_MIN);
          const cor = corDaPos(centro);
          const aceso = i + 0.4 < acesos;
          const ultimo = aceso && i + 1.4 >= acesos;
          return (
            <div
              key={i}
              className="medidor-seg"
              style={
                aceso
                  ? { background: cor, boxShadow: ultimo ? `0 0 9px 1px ${cor}` : `0 0 3px ${cor}55` }
                  : undefined
              }
            ></div>
          );
        })}
      </div>
    );
  } else {
    const cor = corDaPos(mostrado);
    leds = (
      <div className="medidor-track" aria-hidden="true">
        <div
          className="medidor-fill"
          style={{ transform: `scaleX(${frac})`, background: cor, boxShadow: `0 0 12px ${cor}66` }}
        ></div>
      </div>
    );
  }

  return (
    <div
      className="medidor"
      role="meter"
      aria-label="Medidor de viabilidade — margem média"
      aria-valuemin={MED_MIN}
      aria-valuemax={MED_MAX}
      aria-valuenow={Math.round(valor * 10) / 10}
      aria-valuetext={fmtPct(valor) + " de margem média"}
    >
      {leds}
      <div className="medidor-escala" aria-hidden="true">
        {ticks.map((t) => (
          <span key={t} className="medidor-tick" style={{ left: pos(t) + "%" }}>
            {t}
          </span>
        ))}
        <span className="medidor-zona z-nao" style={{ left: pos(-1) + "%" }}>Não vale</span>
        <span className="medidor-zona z-talvez" style={{ left: pos(14) + "%" }}>Talvez</span>
        <span className="medidor-zona z-vale" style={{ left: pos(30) + "%" }}>Vale</span>
      </div>
    </div>
  );
}

/* ---------- etiqueta de veredito ---------- */
export function Etiqueta({ veredito }) {
  return (
    <span className={"etiqueta " + veredito}>
      <span className="led" aria-hidden="true"></span>
      {VEREDITO_TXT[veredito]}
    </span>
  );
}

/* ---------- cartão de resumo (faixa-resumo da análise e do funil) ---------- */
export function Resumo({ k, v, sub, pequeno }) {
  return (
    <div className="mod resumo-mod">
      <div className="silk">{k}</div>
      <div className="v" style={pequeno ? { fontSize: "12px", fontWeight: 500 } : undefined}>
        {v}
        {sub && <small><br />{sub}</small>}
      </div>
    </div>
  );
}

/* ---------- célula de custo editável (tabela de itens + catálogo) ----------
   aoEditar(v): chamado a cada digitação válida (recálculo ao vivo)
   aoConfirmar(v): chamado no blur/Enter (persistência via API) */
export function CostInput({ valor, aoEditar, aoConfirmar, rotulo }) {
  const [editando, setEditando] = React.useState(false);
  const [rascunho, setRascunho] = React.useState("");
  const fmt = (v) => v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const exibido = editando ? rascunho : fmt(valor);
  const confirmar = () => {
    if (!editando) return;
    const v = parseBRL(rascunho);
    if (v != null && v >= 0) {
      const arred = Math.round(v * 100) / 100;
      if (aoEditar) aoEditar(arred);
      if (aoConfirmar) aoConfirmar(arred);
    }
    setEditando(false);
  };
  return (
    <input
      className="custo-input" type="text" inputMode="decimal" value={exibido}
      aria-label={rotulo}
      onFocus={(e) => { setRascunho(fmt(valor)); setEditando(true); requestAnimationFrame(() => e.target.select()); }}
      onChange={(e) => { setRascunho(e.target.value); const v = parseBRL(e.target.value); if (v != null && v >= 0 && aoEditar) aoEditar(Math.round(v * 100) / 100); }}
      onBlur={confirmar}
      onKeyDown={(e) => { if (e.key === "Enter") e.target.blur(); if (e.key === "Escape") { setEditando(false); e.target.blur(); } e.stopPropagation(); }}
      onClick={(e) => e.stopPropagation()}
    />
  );
}

/* ---------- ícones (traço simples, serigrafia) ---------- */
export const Ico = {
  busca: (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="7" cy="7" r="4.6"></circle>
      <path d="M10.5 10.5 14 14"></path>
    </svg>
  ),
  radar: (
    <svg className="nav-ico" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="9" cy="9" r="7"></circle>
      <circle cx="9" cy="9" r="3.5"></circle>
      <path d="M9 9 13.5 4.5"></path>
    </svg>
  ),
  pasta: (
    <svg className="nav-ico" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M2 5.5c0-.8.7-1.5 1.5-1.5h3l1.5 2h6.5c.8 0 1.5.7 1.5 1.5v6c0 .8-.7 1.5-1.5 1.5h-11C2.7 15 2 14.3 2 13.5v-8Z"></path>
    </svg>
  ),
  fader: (
    <svg className="nav-ico" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M4 3v12M9 3v12M14 3v12"></path>
      <rect x="2.2" y="6.5" width="3.6" height="3" rx="1" fill="currentColor" stroke="none"></rect>
      <rect x="7.2" y="10" width="3.6" height="3" rx="1" fill="currentColor" stroke="none"></rect>
      <rect x="12.2" y="4.5" width="3.6" height="3" rx="1" fill="currentColor" stroke="none"></rect>
    </svg>
  ),
  raio: (
    <svg className="nav-ico" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M10 2 4 10.5h4L8 16l6-8.5h-4L10 2Z"></path>
    </svg>
  ),
  fechar: (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M2 2 12 12M12 2 2 12"></path>
    </svg>
  ),
  seta: (
    <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M9 2 4 7l5 5"></path>
    </svg>
  ),
  externo: (
    <svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M5 2H2.5v9.5h9.5V9M8 2h4v4M12 2 6.5 7.5"></path>
    </svg>
  ),
  link: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M6.5 9.5 9.5 6.5M7 4.5 8 3.5a2.5 2.5 0 0 1 3.5 3.5l-1 1M9 11.5 8 12.5A2.5 2.5 0 0 1 4.5 9l1-1"></path>
    </svg>
  ),
  check: (
    <svg width="13" height="13" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M2.5 7.5 6 11l5.5-7.5"></path>
    </svg>
  ),
  doc: (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4">
      <path d="M4 1.5h5L12.5 5v9.5h-8.5z"></path>
      <path d="M9 1.5V5h3.5M5.5 8h5M5.5 10.5h5"></path>
    </svg>
  ),
  escudo: (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M8 1.5 13 3v4.5c0 3.2-2.2 5.5-5 7-2.8-1.5-5-3.8-5-7V3z"></path>
      <path d="M5.8 8 7.3 9.5 10.4 6"></path>
    </svg>
  ),
  alerta: (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ verticalAlign: "-2px", marginRight: "4px" }}>
      <path d="M8 2 1.5 13.5h13z"></path>
      <path d="M8 6.5v3.5M8 12h.01"></path>
    </svg>
  ),
};
