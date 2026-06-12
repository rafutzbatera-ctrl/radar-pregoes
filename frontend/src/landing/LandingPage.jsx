import React from "react";
import "./landing.css";

/** Porta de entrada do app (spec 2026-06-12). aoEntrar() leva ao app.
 *  Estático nesta task — a cena Three.js (Task 3), a coreografia GSAP
 *  (Task 4) e o stat vivo do PNCP (Task 5) entram nas tasks seguintes.
 *  O conteúdo nasce VISÍVEL: nenhum estado inicial de animação no CSS. */
export default function LandingPage({ aoEntrar }) {
  const canvasRef = React.useRef(null);

  // stat vivo do hero (Task 5 liga via api.descobrir). null = a linha NÃO
  // renderiza — nunca um número inventado (princípio 1 do CLAUDE.md).
  const [statVivo] = React.useState(null);

  return (
    <div className="landing">
      <canvas className="ld-canvas" ref={canvasRef} aria-hidden="true" />

      {/* ---------- HERO ---------- */}
      <section className="ld-hero">
        <p className="ld-eyebrow">RADAR DE PREGÕES · LEI 14.133 · FONTE OFICIAL PNCP</p>
        <h1 className="ld-h1">
          <span className="ld-h1-linha">O PNCP INTEIRO</span>
          <span className="ld-h1-linha">NO SEU RADAR.</span>
        </h1>
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
        {statVivo != null && (
          <p className="ld-stat">
            <span className="ld-stat-num">{statVivo.toLocaleString("pt-BR")}</span>
            <span className="ld-stat-txt"> oportunidades recebendo propostas agora</span>
            <span className="ld-stat-fonte">fonte: PNCP ao vivo</span>
          </p>
        )}
      </section>

      {/* ---------- COMO FUNCIONA ---------- */}
      <section className="ld-como" id="como-funciona">
        <h2 className="ld-h2">COMO FUNCIONA</h2>

        <div className="ld-ato">
          <span className="ld-ato-num">01</span>
          <div className="ld-ato-corpo">
            <h3 className="ld-ato-titulo">DESCOBRIR</h3>
            <p className="ld-ato-texto">
              Varra o Brasil por palavra-chave ou navegue tudo aberto. Filtro de
              compra de verdade: sem credenciamento, sem leilão, sem ruído.
            </p>
          </div>
          <MockDescobrir />
        </div>

        <div className="ld-ato">
          <span className="ld-ato-num">02</span>
          <div className="ld-ato-corpo">
            <h3 className="ld-ato-titulo">ANALISAR</h3>
            <p className="ld-ato-texto">
              Itens cruzados com o seu catálogo, margem no preço esperado de
              disputa (não no teto) e veredito honesto: Vale, Talvez ou Não vale
              — com a conta sempre à mostra.
            </p>
          </div>
          <MockAnalisar />
        </div>

        <div className="ld-ato">
          <span className="ld-ato-num">03</span>
          <div className="ld-ato-corpo">
            <h3 className="ld-ato-titulo">DISPUTAR</h3>
            <p className="ld-ato-texto">
              Checklist de habilitação extraído do edital com citação verificada
              página por página, e o funil da disputa até o resultado.
            </p>
          </div>
          <MockDisputar />
        </div>
      </section>

      {/* ---------- MANIFESTO ---------- */}
      <section className="ld-manifesto">
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
      </section>

      {/* ---------- CTA FINAL ---------- */}
      <section className="ld-final">
        <h2 className="ld-h2 ld-final-h2">
          <span className="ld-h1-linha">PRONTO PARA O</span>
          <span className="ld-h1-linha">PRÓXIMO PREGÃO?</span>
        </h2>
        <button type="button" className="ld-cta" onClick={aoEntrar}>
          Entrar no radar →
        </button>

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
      </section>
    </div>
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
