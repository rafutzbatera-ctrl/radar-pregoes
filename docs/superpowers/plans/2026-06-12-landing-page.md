# Landing Page Dark Imersiva 3D — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Landing page nível Awwwards como porta de entrada do app (tela `landing` na SPA), com cena Three.js de radar varrendo pregões + coreografia GSAP, mobile-friendly e honesta (dados vivos reais ou nada).

**Architecture:** Tela `landing` lazy (React.lazy) fora do shell `.app`; código isolado em `frontend/src/landing/` (LandingPage.jsx compõe seções + GSAP; RadarScene.js é classe Three.js pura com API fechada; landing.css tema dark escopado). O app existente não muda de comportamento nem de bundle.

**Tech Stack:** React 18 + Vite, GSAP 3 (ScrollTrigger), Three.js (Points + shader custom, sem postprocessing), CSS variables.

**Spec:** `docs/superpowers/specs/2026-06-12-landing-page-design.md` (decisões do dono e conteúdo literal — os textos PT-BR das seções estão no §7 da spec e são OBRIGATÓRIOS).

**Verificação (não há test runner JS no projeto — convenção do projeto):** cada task fecha com `npm run build` verde + checagem no preview (Chrome DevTools: console limpo, screenshot). Backend intocado (pytest 171 verdes no fim).

**Servidores em uso pelo dono: NUNCA matar processos nas portas 8000/5173.**

---

### Task 1: Dependências + tela `landing` integrada (esqueleto)

**Files:**
- Modify: `frontend/package.json` (via npm i)
- Create: `frontend/src/landing/LandingPage.jsx` (esqueleto)
- Create: `frontend/src/landing/landing.css` (tokens mínimos)
- Modify: `frontend/src/App.jsx` (tela inicial, render fora do shell, link sidebar)

- [ ] **Step 1: instalar deps**

```powershell
cd "D:\CLAUDE PROJECTS\Radar_pregao\frontend"; npm i gsap three
```
Expected: `added 2 packages` (ou similar), sem erros.

- [ ] **Step 2: esqueleto da LandingPage**

`frontend/src/landing/LandingPage.jsx`:
```jsx
import React from "react";
import "./landing.css";

/** Porta de entrada do app (spec 2026-06-12). aoEntrar() leva ao app. */
export default function LandingPage({ aoEntrar }) {
  return (
    <div className="landing">
      <section className="ld-hero">
        <p className="ld-eyebrow">RADAR DE PREGÕES · LEI 14.133 · FONTE OFICIAL PNCP</p>
        <h1 className="ld-h1">O PNCP INTEIRO<br />NO SEU RADAR.</h1>
        <button type="button" className="ld-cta" onClick={aoEntrar}>
          Entrar no radar →
        </button>
      </section>
    </div>
  );
}
```

`frontend/src/landing/landing.css` (tokens da spec §4 + base):
```css
.landing {
  --noite: #0A0F0D; --fosforo: #2BD97F; --fosforo-2: rgba(43,217,127,0.14);
  --neve: #E9F2EC; --cinza: #7C8A81; --ambar: #E0A21B; --rubi: #E25A4A;
  position: fixed; inset: 0; overflow-y: auto; background: var(--noite);
  color: var(--neve); font-family: var(--font-body);
}
.ld-eyebrow { font-family: var(--font-mono); font-size: 12px;
  letter-spacing: 0.14em; color: var(--cinza); }
.ld-h1 { font-family: var(--font-display); font-weight: 800;
  font-size: clamp(64px, 12vw, 160px); line-height: 0.92; margin: 0;
  text-transform: uppercase; }
.ld-cta { font-family: var(--font-mono); font-weight: 600; font-size: 14px;
  background: var(--fosforo); color: var(--noite); border: 0;
  padding: 16px 28px; min-height: 44px; cursor: pointer; }
.ld-hero { min-height: 100dvh; display: grid; align-content: center;
  gap: 24px; padding: 24px clamp(20px, 6vw, 96px); }
```

- [ ] **Step 3: integrar no App.jsx**

(a) Import lazy no topo (junto dos outros imports):
```jsx
const LandingPage = React.lazy(() => import("./landing/LandingPage.jsx"));
```
(b) Tela inicial (linha ~76, hoje `useState({ nome: "find" })`):
```jsx
const [tela, setTela] = React.useState(() =>
  localStorage.getItem("radar_visitou") ? { nome: "find" } : { nome: "landing" }
);
```
(c) Render FORA do shell — antes do `return` que monta `.app`, curto-circuito:
```jsx
if (tela.nome === "landing") {
  return (
    <React.Suspense fallback={<div style={{ position: "fixed", inset: 0, background: "#0A0F0D" }} />}>
      <LandingPage aoEntrar={() => {
        localStorage.setItem("radar_visitou", "1");
        setTela({ nome: "find" });
      }} />
    </React.Suspense>
  );
}
```
(d) No rodapé do `<Sidebar>` (componente na linha ~607, junto do bloco final
da nav), link discreto:
```jsx
<button type="button" className="nav-apresentacao"
  onClick={() => irPara("landing")}>Apresentação</button>
```
ATENÇÃO: `irPara` hoje faz `setTela({ nome: id })` — "landing" funciona sem
mudança. Estilizar `.nav-apresentacao` no styles.css do app (mono 10.5px,
cor silk, fundo transparente, hover sublinhado).

- [ ] **Step 4: verificar**

```powershell
npm run build
```
Expected: verde; no output do Vite aparece um chunk novo (LandingPage) separado do index.
Preview (DevTools): `localStorage.removeItem("radar_visitou")` + reload → landing aparece; clicar "Entrar no radar" → app; reload → direto no app; "Apresentação" na sidebar → landing. Console: zero erros.

- [ ] **Step 5: commit**

```powershell
git add frontend; git commit -m "Landing: tela de entrada lazy integrada na SPA (esqueleto)"
```

---

### Task 2: Tema completo + todas as seções (estático, conteúdo literal)

**Files:**
- Modify: `frontend/src/landing/LandingPage.jsx` (todas as seções)
- Modify: `frontend/src/landing/landing.css` (tema completo)

- [ ] **Step 1: seções com o conteúdo LITERAL da spec §7**

Estrutura JSX (textos exatos na spec — hero, como funciona com atos 01/02/03,
manifesto com 3 frases, CTA final, rodapé com os 2 avisos do CLAUDE.md §9):
```jsx
<div className="landing">
  <canvas className="ld-canvas" ref={canvasRef} aria-hidden="true" />
  <section className="ld-hero">…eyebrow, h1, sub, CTAs, stat vivo (Task 5)…</section>
  <section className="ld-como" id="como-funciona">
    <h2 className="ld-h2">COMO FUNCIONA</h2>
    {/* 3 .ld-ato: número mono gigante + título + texto + mini-mockup HTML/CSS */}
  </section>
  <section className="ld-manifesto">{/* 3 .ld-frase: LED + display + corpo */}</section>
  <section className="ld-final">…h2 + CTA…</section>
  <footer className="ld-rodape">…avisos §9 literais…</footer>
</div>
```
Mini-mockups: HTML/CSS estilizado (cards com linhas mono, LEDs, barras de
margem) ecoando a UI real — SEM imagens, SEM iframe.

- [ ] **Step 2: tema completo no landing.css**

Requisitos (spec §4/§9): atmosfera em camadas (radial-gradients fosforosos a
6%, grain sutil), `.ld-h2` clamp(40px, 7vw, 96px), corpo Archivo 16–18px,
labels mono 0.12em, LEDs (`.ld-led` 10px, box-shadow glow), seções com
`padding: clamp(64px, 14vh, 160px) clamp(20px, 6vw, 96px)`, empilhamento
mobile ≤ 720px, alvos ≥ 44px, `:focus-visible` herdado do app.
`.ld-canvas { position: fixed; inset: 0; z-index: 0; pointer-events: none; }`
e todas as seções `position: relative; z-index: 1;`.

- [ ] **Step 3: verificar**

`npm run build` verde. Preview: screenshots desktop (1440) e mobile (380) —
todas as seções presentes, textos batem com a spec §7, nada vazando na
horizontal no mobile. Console zero erros.

- [ ] **Step 4: commit**

```powershell
git add frontend; git commit -m "Landing: tema dark fosforo + secoes completas (estatico)"
```

---

### Task 3: RadarScene.js (Three.js)

**Files:**
- Create: `frontend/src/landing/RadarScene.js`
- Modify: `frontend/src/landing/LandingPage.jsx` (montar a cena no canvas)

- [ ] **Step 1: implementar a classe (API fechada da spec §5)**

```js
import * as THREE from "three";

export default class RadarScene {
  constructor(canvas, { reduzido = false, mobile = false } = {}) { /* … */ }
  ligar() {}            // boot CRT ~1.6s e inicia rAF (reduzido: 1 frame só)
  setProgresso(p) {}    // 0..1 → ALVOS de tilt/zoom/velocidade (lerp no rAF)
  setPonteiro(x, y) {}  // -1..1 parallax; no-op se mobile
  pausar() {} retomar() {}
  dispose() {}          // cancelAnimationFrame, remove resize listener,
                        // geometry/material/renderer.dispose()
}
```
Conteúdo obrigatório (spec §5):
- Renderer: `{ canvas, antialias: false, alpha: true, powerPreference: mobile ? "low-power" : "high-performance" }`; `setPixelRatio(Math.min(devicePixelRatio, mobile ? 1 : 1.5))`; resize por listener de `window.resize`.
- Grade polar: anéis concêntricos + radiais via `LineSegments`, cor `#2BD97F`, opacity ~0.06.
- Pontos: `THREE.Points`, **3000 desktop / 800 mobile**, distribuição radial com 6–8 clusters gaussianos; atributos `aAngulo`, `aRaio`, `aTipo` (0 fósforo 97%, 1 âmbar, 2 rubi); `ShaderMaterial` com uniforms `uTempo`, `uFeixe` (ângulo atual), `uBoot` (0..1), `uPixelRatio`; vertex: posição polar + size attenuation; fragment: disco suave (smoothstep), brilho = base 0.18 + rastro `exp(-difAngular * 2.2)` atrás do feixe, additive blending, `depthWrite: false`.
- Feixe: cunha de geometria leve (Mesh com shader de gradiente angular alpha) girando `uFeixe += dt * velocidade`; velocidade/tilt/zoom interpolam (lerp 0.05) para alvos definidos por `setProgresso` (p=0: feixe 0.5 rad/s, câmera tilt 35°, zoom 1; p=1: feixe 1.4 rad/s, tilt 18°, zoom 1.18).
- Boot em `ligar()`: `uBoot` 0→1 em 1.6s (easeOut) acendendo anéis de dentro pra fora; reduzido=true: renderiza UM frame com `uBoot=1`, feixe a 40°, sem rAF.
- `document.visibilitychange` → pausar/retomar internos.

- [ ] **Step 2: montar no LandingPage**

```jsx
const canvasRef = React.useRef(null);
const cenaRef = React.useRef(null);
React.useEffect(() => {
  const reduzido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const mobile = window.matchMedia("(max-width: 720px)").matches;
  const cena = new RadarScene(canvasRef.current, { reduzido, mobile });
  cenaRef.current = cena;
  cena.ligar();
  const aoMover = (e) => cena.setPonteiro(
    (e.clientX / window.innerWidth) * 2 - 1,
    (e.clientY / window.innerHeight) * 2 - 1,
  );
  if (!mobile && !reduzido) window.addEventListener("pointermove", aoMover);
  return () => { window.removeEventListener("pointermove", aoMover); cena.dispose(); };
}, []);
```

- [ ] **Step 3: verificar**

`npm run build` verde. Preview: cena visível atrás do hero (boot animando),
sem erros WebGL no console; trocar para 380px (preview_resize) → continua
fluida; voltar ao app ("Entrar") e reabrir a landing → sem vazamento
(console sem warning de contexto WebGL duplicado).

- [ ] **Step 4: commit**

```powershell
git add frontend; git commit -m "Landing: cena Three.js do radar (varredura + boot CRT)"
```

---

### Task 4: Coreografia GSAP (load orquestrado + scroll)

**Files:**
- Modify: `frontend/src/landing/LandingPage.jsx`

- [ ] **Step 1: implementar dentro de `gsap.matchMedia()`**

```jsx
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
gsap.registerPlugin(ScrollTrigger);
```
No `useEffect` (depois de montar a cena), com o `.landing` como `scroller`:
- `mm = gsap.matchMedia()`; bloco `(prefers-reduced-motion: no-preference)`:
  1. **Load orquestrado** (UMA timeline): eyebrow → linhas do H1 (y 40,
     clip-path, stagger 0.08) → sub → CTAs → stat (cada um ~0.5s, ease
     "power3.out"); coincide com `cena.ligar()`.
  2. **Scrub global**: `ScrollTrigger.create({ scroller: ".landing", start: 0,
     end: "max", onUpdate: (st) => cena.setProgresso(st.progress) })`.
  3. **Reveals por seção** (`once: true`): atos (y+opacity stagger), frases do
     manifesto (LED acende com `boxShadow` + texto sobe), CTA final.
- Bloco `(prefers-reduced-motion: reduce)`: nada — conteúdo nasce visível
  (CSS não pode esconder por padrão: estados iniciais via `gsap.set` SÓ no
  bloco animado, nunca no CSS).
- Cleanup: `return () => { mm.revert(); }` antes do `cena.dispose()`.

- [ ] **Step 2: verificar**

Preview: reload → reveals escalonados no load; scroll até o fim → feixe
acelera/câmera fecha (setProgresso), seções revelam uma vez; console zero
erros; `ScrollTrigger.getAll().length` > 0 via preview_eval; mobile 380px
→ scroll fluido.

- [ ] **Step 3: commit**

```powershell
git add frontend; git commit -m "Landing: page-load orquestrado + scroll scrub GSAP"
```

---

### Task 5: Stat vivo honesto no hero

**Files:**
- Modify: `frontend/src/landing/LandingPage.jsx`

- [ ] **Step 1: buscar o total real**

```jsx
const [statVivo, setStatVivo] = React.useState(null); // null = não mostra
React.useEffect(() => {
  let vivo = true;
  api.descobrir({ pagina: 1 })
    .then((r) => { if (vivo && r && r.total > 0) setStatVivo(r.total); })
    .catch(() => {});           // falhou → linha NÃO renderiza (nunca inventa)
  return () => { vivo = false; };
}, []);
```
Render (só quando `statVivo`): número mono grande com roll-up GSAP (snap 1)
ao aparecer + carimbo `fonte: PNCP ao vivo`. Formato `pt-BR`
(`toLocaleString("pt-BR")`).

- [ ] **Step 2: verificar**

Preview com backend de pé: número real aparece e rola. `preview_eval` com
backend respondendo é suficiente; o caminho de falha é coberto lendo o código
(catch → estado null → sem render).

- [ ] **Step 3: commit**

```powershell
git add frontend; git commit -m "Landing: stat vivo do PNCP no hero (honesto: some em falha)"
```

---

### Task 6: Verificação final (DevTools) + prova

- [ ] Build: `npm run build` verde; conferir no output que three/gsap NÃO
  estão no chunk principal (index-*.js) e sim no chunk da landing.
- [ ] Backend intocado: `cd backend; .\.venv\Scripts\python -m pytest tests -q`
  → 171 passed.
- [ ] Preview DevTools: console zero erros após load + scroll completo;
  screenshots: hero desktop 1440, hero mobile 380, manifesto, CTA final.
- [ ] Fluxo: localStorage limpo → landing; Entrar → app; reload → app;
  Apresentação → landing.
- [ ] Commit final (se sobrou ajuste) e relatório com screenshots.
