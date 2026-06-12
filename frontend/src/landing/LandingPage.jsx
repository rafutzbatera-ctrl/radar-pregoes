import React from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import "./landing.css";
import RadarScene from "./RadarScene.js";
import { api } from "../api.js";

gsap.registerPlugin(ScrollTrigger);

/** Porta de entrada do app (spec 2026-06-12). aoEntrar() leva ao app.
 *  Cena Three.js (Task 3) + coreografia GSAP (Task 4) + stat vivo do PNCP
 *  (Task 5). O conteúdo nasce VISÍVEL: nenhum estado inicial de animação no
 *  CSS — só via gsap.set DENTRO do bloco animado. */
export default function LandingPage({ aoEntrar }) {
  const raizRef = React.useRef(null);     // .landing — scroller dos ScrollTriggers
  const canvasRef = React.useRef(null);
  const cenaRef = React.useRef(null);
  const statNumRef = React.useRef(null);  // alvo do roll-up GSAP do stat vivo

  // stat vivo do hero (Task 5): total real do PNCP via api.descobrir. null = a
  // linha NÃO renderiza — nunca um número inventado (princípio 1 do CLAUDE.md).
  const [statVivo, setStatVivo] = React.useState(null);

  // Cena Three.js do radar (classe pura). Boot CRT + varredura; em
  // reduced-motion renderiza UM frame estático. Cleanup faz dispose completo.
  React.useEffect(() => {
    const reduzido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const mobile = window.matchMedia("(max-width: 720px)").matches;
    let cena = null;
    try {
      cena = new RadarScene(canvasRef.current, { reduzido, mobile });
      cenaRef.current = cena;
      cena.ligar();
    } catch {
      cenaRef.current = null; // sem WebGL: a landing segue inteira, só sem 3D
    }
    const aoMover = (e) =>
      cena.setPonteiro(
        (e.clientX / window.innerWidth) * 2 - 1,
        (e.clientY / window.innerHeight) * 2 - 1,
      );
    if (cena && !mobile && !reduzido) window.addEventListener("pointermove", aoMover);
    return () => {
      window.removeEventListener("pointermove", aoMover);
      if (cena) cena.dispose();
      cenaRef.current = null;
    };
  }, []);

  // ---------- Task 4: coreografia GSAP (load orquestrado + scroll scrub) ----------
  // TUDO dentro de gsap.matchMedia(): motion completo só em no-preference; no
  // modo reduzido nenhum trigger é criado (a cena já é no-op) e o conteúdo nasce
  // visível — estados iniciais vêm de gsap.set DENTRO do bloco, nunca do CSS.
  // Este effect é registrado DEPOIS do da cena → seu cleanup (mm.revert) roda
  // ANTES do dispose da cena (React limpa effects em ordem reversa).
  React.useEffect(() => {
    const raiz = raizRef.current;
    if (!raiz) return undefined;
    const mm = gsap.matchMedia();

    mm.add("(prefers-reduced-motion: no-preference)", () => {
      const q = gsap.utils.selector(raiz);

      // (a) Page-load orquestrado — UMA timeline, ease power3.out. Coincide com
      // o boot da cena (já disparado no mount). Estados iniciais via gsap.set.
      // O .ld-stat NÃO entra: ele só existe depois da resposta do PNCP (async)
      // e nasce visível com roll-up próprio — mirá-lo aqui só gera o warning
      // GSAP target not found.
      gsap.set(q(".ld-eyebrow, .ld-sub, .ld-ctas > *"), { autoAlpha: 0, y: 24 });
      gsap.set(q(".ld-hero .ld-h1-inner"), {
        yPercent: 110,
        clipPath: "inset(0 0 100% 0)",
      });

      const tlLoad = gsap.timeline({ defaults: { ease: "power3.out" } });
      tlLoad
        .to(q(".ld-eyebrow"), { autoAlpha: 1, y: 0, duration: 0.5 })
        .to(
          q(".ld-hero .ld-h1-inner"),
          { yPercent: 0, clipPath: "inset(0 0 0% 0)", duration: 0.8, stagger: 0.08 },
          "-=0.2",
        )
        .to(q(".ld-sub"), { autoAlpha: 1, y: 0, duration: 0.5 }, "-=0.4")
        .to(q(".ld-ctas > *"), { autoAlpha: 1, y: 0, duration: 0.5, stagger: 0.08 }, "-=0.3");

      // (b) Scrub global: o scroll é do contêiner .landing (fixed/overflow-y).
      // Passamos o ELEMENTO como scroller (não a string) p/ evitar ambiguidade.
      // setProgresso só ajusta alvos (lerp interno) → sem throttle no onUpdate.
      const scrub = ScrollTrigger.create({
        scroller: raiz,
        trigger: raiz,
        start: 0,
        end: "max",
        onUpdate: (st) => cenaRef.current?.setProgresso(st.progress),
      });

      // (c) Reveals por seção (once: true) — disparam uma única vez ao entrar.
      const atos = q(".ld-ato");
      gsap.set(atos, { autoAlpha: 0, y: 40 });
      atos.forEach((ato) => {
        gsap.to(ato, {
          autoAlpha: 1,
          y: 0,
          duration: 0.7,
          ease: "power3.out",
          scrollTrigger: { scroller: raiz, trigger: ato, start: "top 82%", once: true },
        });
      });

      // manifesto: o LED acende (cor + glow) e o texto da frase sobe.
      const frases = q(".ld-frase");
      gsap.set(frases, { autoAlpha: 0, y: 36 });
      gsap.set(q(".ld-frase .ld-led"), {
        backgroundColor: "rgba(124,138,129,0.35)",
        boxShadow: "0 0 0 0 rgba(43,217,127,0)",
      });
      frases.forEach((frase) => {
        const led = frase.querySelector(".ld-led");
        gsap
          .timeline({
            defaults: { ease: "power3.out" },
            scrollTrigger: { scroller: raiz, trigger: frase, start: "top 80%", once: true },
          })
          .to(led, {
            backgroundColor: "#2BD97F",
            boxShadow: "0 0 14px 2px rgba(43,217,127,0.75)",
            duration: 0.45,
          })
          .to(frase, { autoAlpha: 1, y: 0, duration: 0.7 }, "-=0.25");
      });

      // CTA final: o bloco inteiro entra junto.
      const final = q(".ld-final");
      if (final.length) {
        gsap.set(final, { autoAlpha: 0, y: 40 });
        gsap.to(final, {
          autoAlpha: 1,
          y: 0,
          duration: 0.8,
          ease: "power3.out",
          scrollTrigger: { scroller: raiz, trigger: final, start: "top 85%", once: true },
        });
      }

      return () => {
        tlLoad.kill();
        scrub.kill();
      };
    });

    // Bloco reduzido: NADA (sem triggers, sem sets) — conteúdo já visível.

    return () => mm.revert();
  }, []);

  // ---------- Task 5: stat vivo honesto (total real do PNCP) ----------
  // Sucesso com total > 0 → renderiza a linha + roll-up. Falha/timeout → catch
  // silencioso, statVivo segue null → a linha NÃO renderiza (nunca inventa).
  React.useEffect(() => {
    let vivo = true;
    api
      .descobrir({ pagina: 1 })
      .then((r) => {
        if (vivo && r && r.total > 0) setStatVivo(r.total);
      })
      .catch(() => {});
    return () => {
      vivo = false;
    };
  }, []);

  // Roll-up do número ao aparecer (snap 1, formato pt-BR). Respeita reduced-
  // motion: sob "reduce" escreve o total final direto, sem animar.
  React.useEffect(() => {
    if (statVivo == null) return undefined;
    const alvo = statNumRef.current;
    if (!alvo) return undefined;
    const reduzido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const escrever = (n) => {
      alvo.textContent = Math.round(n).toLocaleString("pt-BR");
    };
    if (reduzido) {
      escrever(statVivo);
      return undefined;
    }
    const contador = { v: 0 };
    const tween = gsap.to(contador, {
      v: statVivo,
      duration: 1.1,
      ease: "power2.out",
      snap: { v: 1 },
      onUpdate: () => escrever(contador.v),
    });
    return () => tween.kill();
  }, [statVivo]);

  return (
    <div className="landing" ref={raizRef}>
      <canvas className="ld-canvas" ref={canvasRef} aria-hidden="true" />

      {/* ---------- HERO ---------- */}
      {/* Desktop (≥1024px): o hero vira grid de 2 linhas — topo (identidade +
          sub/CTAs) e o stat como faixa horizontal de rodapé na largura cheia.
          Mobile/base: empilha como antes (os wrappers são transparentes). */}
      <section className="ld-hero">
        <div className="ld-hero-topo">
          <div className="ld-hero-id">
            <p className="ld-eyebrow">RADAR DE PREGÕES · LEI 14.133 · FONTE OFICIAL PNCP</p>
            <h1 className="ld-h1">
              <span className="ld-h1-linha"><span className="ld-h1-inner">O PNCP INTEIRO</span></span>
              <span className="ld-h1-linha"><span className="ld-h1-inner">NO SEU RADAR.</span></span>
            </h1>
          </div>
          <div className="ld-hero-acao">
            <p className="ld-sub">
              Busca ao vivo nos ~37 mil editais nacionais, margem e veredito
              calculados no preço esperado de disputa — sempre com a fonte oficial
              à vista.
            </p>
            <div className="ld-ctas">
              <button type="button" className="ld-cta" onClick={aoEntrar}>
                Entrar no radar →
              </button>
              <a className="ld-cta-2" href="#como-funciona">Ver como funciona ↓</a>
            </div>
          </div>
        </div>
        {statVivo != null && (
          <p className="ld-stat">
            {/* o número é escrito pelo roll-up GSAP (ref); valor inicial já
                formatado p/ reduced-motion e p/ caso o tween não rode. */}
            <span className="ld-stat-num" ref={statNumRef}>
              {statVivo.toLocaleString("pt-BR")}
            </span>
            <span className="ld-stat-txt"> oportunidades recebendo propostas agora</span>
            <span className="ld-stat-fonte">fonte: PNCP ao vivo</span>
          </p>
        )}
      </section>

      {/* ---------- MARQUEE (faixa de recursos) ---------- */}
      {/* Faixa fina full-bleed entre hero e "como funciona". CSS puro (sem GSAP):
          o track duplicado 2× rola translateX 0→-50% em loop contínuo. Conteúdo
          decorativo/redundante → role="presentation"; cópia duplicada aria-hidden.
          reduced-motion: animação parada (linha estática cortada pelo overflow). */}
      <div className="ld-marquee" role="presentation">
        <div className="ld-marquee-track">
          <MarqueeItens />
          <MarqueeItens dup />
        </div>
      </div>

      {/* ---------- COMO FUNCIONA ---------- */}
      {/* Inner (.ld-wrap) centraliza o conteúdo num max-width largo no desktop,
          mantendo o padding clamp da seção nas bordas. Em ≥1024px os 3 atos
          ficam lado a lado num grid de 3 colunas iguais (.ld-atos-grid); abaixo
          disso empilham em coluna única como sempre. */}
      <section className="ld-como" id="como-funciona">
        <div className="ld-wrap">
          <h2 className="ld-h2">COMO FUNCIONA</h2>

          <div className="ld-atos-grid">
            <div className="ld-ato">
              <div className="ld-ato-corpo">
                <span className="ld-ato-num">01</span>
                <h3 className="ld-ato-titulo">DESCOBRIR</h3>
                <p className="ld-ato-texto">
                  Varra o Brasil por palavra-chave ou navegue tudo aberto. Filtro de
                  compra de verdade: sem credenciamento, sem leilão, sem ruído.
                </p>
              </div>
              <div className="ld-ato-mock"><MockDescobrir /></div>
            </div>

            <div className="ld-ato">
              <div className="ld-ato-corpo">
                <span className="ld-ato-num">02</span>
                <h3 className="ld-ato-titulo">ANALISAR</h3>
                <p className="ld-ato-texto">
                  Itens cruzados com o seu catálogo, margem no preço esperado de
                  disputa (não no teto) e veredito honesto: Vale, Talvez ou Não vale
                  — com a conta sempre à mostra.
                </p>
              </div>
              <div className="ld-ato-mock"><MockAnalisar /></div>
            </div>

            <div className="ld-ato">
              <div className="ld-ato-corpo">
                <span className="ld-ato-num">03</span>
                <h3 className="ld-ato-titulo">DISPUTAR</h3>
                <p className="ld-ato-texto">
                  Checklist de habilitação extraído do edital com citação verificada
                  página por página, e o funil da disputa até o resultado.
                </p>
              </div>
              <div className="ld-ato-mock"><MockDisputar /></div>
            </div>
          </div>

          <div className="ld-como-cta">
            <button type="button" className="ld-cta" onClick={aoEntrar}>
              Entrar no radar →
            </button>
          </div>
        </div>
      </section>

      {/* ---------- MANIFESTO ---------- */}
      {/* Cada .ld-frase vira grid de 2 colunas em ≥1024px: frase display gigante
          à esquerda, corpo (~32rem) à direita alinhado pela baseline. */}
      <section className="ld-manifesto">
        <div className="ld-wrap">
          <div className="ld-frase">
            <span className="ld-led" aria-hidden="true" />
            <h2 className="ld-frase-titulo">NUNCA INVENTA.</h2>
            <p className="ld-frase-corpo">
              Toda exigência sai com o trecho literal do edital, página e
              verificação. O que não foi achado fica marcado: não encontrado.
            </p>
          </div>
          <div className="ld-frase">
            <span className="ld-led" aria-hidden="true" />
            <h2 className="ld-frase-titulo">FONTE OFICIAL SEMPRE À VISTA.</h2>
            <p className="ld-frase-corpo">
              Valores e prazos vêm do PNCP. O link do edital oficial nunca sai da
              tela.
            </p>
          </div>
          <div className="ld-frase">
            <span className="ld-led" aria-hidden="true" />
            <h2 className="ld-frase-titulo">A CONTA É SUA.</h2>
            <p className="ld-frase-corpo">
              Custo é dado seu; simulação vem rotulada de simulação. O veredito
              nunca esconde os números.
            </p>
          </div>
        </div>
      </section>

      {/* ---------- CTA FINAL ---------- */}
      {/* Em ≥1024px o CTA centraliza em largura cheia e o rodapé vira 2 colunas
          (um aviso em cada). */}
      <section className="ld-final">
        <div className="ld-wrap">
          <div className="ld-final-bloco">
            <h2 className="ld-h2 ld-final-h2">
              <span className="ld-h1-linha">PRONTO PARA O</span>
              <span className="ld-h1-linha">PRÓXIMO PREGÃO?</span>
            </h2>
            <button type="button" className="ld-cta" onClick={aoEntrar}>
              Entrar no radar →
            </button>
          </div>

          <footer className="ld-rodape">
            <p className="ld-aviso">
              Ferramenta de apoio à decisão. O edital oficial e os valores estão
              no PNCP. Confira antes de dar lance.
            </p>
            <p className="ld-aviso">
              Sugestões fiscais (NCM, CFOP, CST/CSOSN) são apoio, não orientação
              contábil. Confirme com seu contador antes de emitir a nota.
            </p>
          </footer>
        </div>
      </section>
    </div>
  );
}

/* ====================================================================== */
/* Marquee: itens de recurso em mono caixa-alta, separados por LED-dot.    */
/* Renderizado 2× dentro do track (a 2ª cópia aria-hidden) para o loop     */
/* translateX 0→-50% emendar sem salto.                                    */
/* ====================================================================== */
const MARQUEE_ITENS = [
  "FONTE OFICIAL PNCP",
  "BUSCA AO VIVO",
  "BRASIL INTEIRO",
  "MARGEM NO PREÇO ESPERADO",
  "CITAÇÃO VERIFICADA",
  "VEREDITO HONESTO",
  "SÓ COMPRA DE BENS",
  "FUNIL DE DISPUTA",
  "PRONTIDÃO NF-E",
  "CUSTO É SEU DADO",
];

function MarqueeItens({ dup = false }) {
  return (
    <ul className="ld-marquee-grupo" aria-hidden={dup ? "true" : undefined}>
      {MARQUEE_ITENS.map((t) => (
        <li className="ld-marquee-item" key={t}>
          <span className="ld-marquee-dot" />
          <span className="ld-marquee-txt">{t}</span>
        </li>
      ))}
    </ul>
  );
}

/* ====================================================================== */
/* Mini-mockups: HTML/CSS estilizado ecoando a UI real do app.            */
/* SEM imagens, SEM iframe — o "produto dentro da página".                */
/* ====================================================================== */

function MockDescobrir() {
  return (
    <div className="ld-mock" aria-hidden="true">
      <div className="ld-mock-top">
        <span className="ld-mock-tag">q: áudio · microfone</span>
        <span className="ld-mock-tag ld-mock-tag-ok">SP</span>
      </div>
      <div className="ld-mock-row">
        <span className="ld-led ld-led-fos" />
        <span className="ld-mock-linha">PREGÃO ELETRÔNICO 90/2026</span>
        <span className="ld-mock-val">R$ 142 mil</span>
      </div>
      <div className="ld-mock-row">
        <span className="ld-led ld-led-fos" />
        <span className="ld-mock-linha">SISTEMA DE SONORIZAÇÃO — CÂMARA</span>
        <span className="ld-mock-val">R$ 88 mil</span>
      </div>
      <div className="ld-mock-row ld-mock-row-mute">
        <span className="ld-led ld-led-mute" />
        <span className="ld-mock-linha">CREDENCIAMENTO (FILTRADO)</span>
        <span className="ld-mock-val">—</span>
      </div>
    </div>
  );
}

function MockAnalisar() {
  return (
    <div className="ld-mock" aria-hidden="true">
      <div className="ld-mock-top">
        <span className="ld-mock-tag">VEREDITO</span>
        <span className="ld-veredito ld-veredito-vale">VALE</span>
      </div>
      <div className="ld-mock-item">
        <span className="ld-mock-linha">MICROFONE SEM FIO UHF</span>
        <div className="ld-barra"><span className="ld-barra-fill" style={{ width: "72%" }} /></div>
        <span className="ld-mock-pct">+72%</span>
      </div>
      <div className="ld-mock-item">
        <span className="ld-mock-linha">CAIXA ACÚSTICA ATIVA 15"</span>
        <div className="ld-barra"><span className="ld-barra-fill ld-barra-amb" style={{ width: "31%" }} /></div>
        <span className="ld-mock-pct ld-pct-amb">+31%</span>
      </div>
      <div className="ld-mock-item">
        <span className="ld-mock-linha">PROJETOR (SEM CUSTO)</span>
        <div className="ld-barra"><span className="ld-barra-fill ld-barra-mute" style={{ width: "8%" }} /></div>
        <span className="ld-mock-pct ld-pct-mute">—</span>
      </div>
      <div className="ld-mock-foot">
        <span>lucro potencial</span><span className="ld-mock-val">R$ 18.400</span>
      </div>
    </div>
  );
}

function MockDisputar() {
  return (
    <div className="ld-mock" aria-hidden="true">
      <div className="ld-mock-top">
        <span className="ld-mock-tag">HABILITAÇÃO · pág. citada</span>
      </div>
      <div className="ld-mock-check">
        <span className="ld-check ld-check-ok">✓</span>
        <span className="ld-mock-linha">CND FEDERAL <em>pág. 14</em></span>
      </div>
      <div className="ld-mock-check">
        <span className="ld-check ld-check-ok">✓</span>
        <span className="ld-mock-linha">ATESTADO TÉCNICO <em>pág. 22</em></span>
      </div>
      <div className="ld-mock-check">
        <span className="ld-check ld-check-pend">•</span>
        <span className="ld-mock-linha">BALANÇO PATRIMONIAL <em>pendente</em></span>
      </div>
      <div className="ld-mock-funil">
        <span className="ld-funil-etapa ld-funil-on">SALVO</span>
        <span className="ld-funil-etapa ld-funil-on">DISPUTA</span>
        <span className="ld-funil-etapa">RESULTADO</span>
      </div>
    </div>
  );
}
