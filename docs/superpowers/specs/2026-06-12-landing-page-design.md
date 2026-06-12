# Landing page — porta de entrada dark imersiva 3D (spec aprovada)

Data: 2026-06-12 · Status: aprovada pelo dono ("sim segue")
Decisões do dono: **porta de entrada do app** (mesma SPA) + **dark imersivo 3D**
(abordagem A: cena Three.js dedicada + GSAP ScrollTrigger).

## 1. Objetivo

Uma landing page nível Awwwards que apresenta o Radar de Pregões e leva ao app.
A cena 3D É o produto: um radar varrendo os pregões do Brasil — não partícula
genérica flutuando. Mobile-friendly, acessível (reduced-motion), dados vivos
reais (nunca inventa — princípio 1 do CLAUDE.md).

Guia estético (cookbook `prompting_for_frontend_aesthetics.ipynb`):
- Anti "AI slop": nada de gradiente roxo/fundo branco, nada de Inter/Space
  Grotesk, nada de layout previsível de template SaaS.
- Pesos tipográficos extremos e saltos de escala 3x+ (aqui: >6x).
- Cor dominante com acentos nítidos, tudo em CSS variables.
- UM page-load orquestrado com reveals escalonados > micro-interações espalhadas.

## 2. Integração na SPA (App.jsx)

- Nova tela `landing`, renderizada **fora** do shell `.app` (sem sidebar,
  viewport inteiro, scroll próprio).
- `const LandingPage = React.lazy(() => import("./landing/LandingPage.jsx"))`
  — three/gsap ficam num chunk separado; o app atual não paga 1 byte.
  `<React.Suspense fallback={<div class fundo #0A0F0D />}>`.
- Tela inicial: `localStorage.radar_visitou` ausente → `{nome:"landing"}`;
  presente → `{nome:"find"}` (uso diário não revê a landing).
- CTA "Entrar no radar": grava `radar_visitou=1` e `setTela({nome:"find"})`.
- Link discreto "Apresentação" no rodapé da sidebar → `setTela({nome:"landing"})`.

## 3. Arquivos (isolamento)

```
frontend/src/landing/
  LandingPage.jsx    # composição das seções + coreografia GSAP + dados vivos
  RadarScene.js      # classe Three.js PURA (sem React) — testável isolada
  landing.css        # tema dark escopado em .landing (CSS variables próprias)
```
Dependências novas: `npm i gsap three` (gsap ~70KB gz, three ~160KB gz, ambos
só no chunk lazy da landing).

## 4. Identidade visual (escopo `.landing`)

```css
--noite:   #0A0F0D;   /* fundo — verde-noite profundo, não preto chapado */
--fosforo: #2BD97F;   /* acento dominante — verde fósforo de radar CRT */
--fosforo-2: rgba(43,217,127,0.14);  /* halos/linhas */
--neve:    #E9F2EC;   /* texto principal */
--cinza:   #7C8A81;   /* texto secundário (mono) */
--ambar:   #E0A21B;   /* dado de atenção (pontual) */
--rubi:    #E25A4A;   /* dado negativo (pontual) */
```
- Display: **Big Shoulders Display 800** (já carregada), `clamp(64px, 12vw, 160px)`,
  tracking apertado, caixa alta, quebras de linha intencionais.
- Dados/labels: **IBM Plex Mono 400/600** 12–14px, letter-spacing 0.12em
  (mesma linguagem `.silk` do app). Corpo: Archivo 400 16–18px.
- Salto de escala display/corpo > 6x (cookbook: 3x+).
- Textura: grain sutil via CSS (radial-gradients), linhas de grade fosforosas
  a 6% — atmosfera, nunca cor sólida chapada.

## 5. Cena 3D — RadarScene.js (Three.js, classe pura)

API (contrato fechado — LandingPage só fala isso):
```js
class RadarScene {
  constructor(canvas, { reduzido = false, mobile = false } = {})
  ligar()              // boot CRT (~1.6s) e inicia o loop rAF
  setProgresso(p)      // 0..1 — scroll global (scrub GSAP): tilt/zoom/feixe
  setPonteiro(x, y)    // -1..1 parallax de mouse (no-op quando mobile)
  pausar(); retomar()  // document.hidden / fim da página
  dispose()            // listeners fora, geometrias/materiais/renderer liberados
}
```
Visual:
- Plano polar inclinado (~35°) com anéis e radiais de grade (LineSegments,
  opacidade ~6%).
- **~3000 pontos** (Points + shader; **800 no mobile**) em distribuição radial
  com clusters (regiões do país, abstrato). ~97% fósforo, ~3% âmbar/rubi.
- **Feixe de varredura**: uniform de ângulo; brilho do ponto =
  f(distância angular ao feixe) com decaimento lento (rastro fosforescente).
  Glow barato: sprite radial + additive blending. **Sem postprocessing/bloom.**
- Boot (em `ligar()`): flash CRT, anéis acendem de dentro pra fora, feixe parte.
- `setProgresso`: interpola (lerp no rAF, nunca direto) velocidade do feixe,
  tilt da câmera e zoom — a cena "responde" à leitura da página.
Performance:
- DPR ≤ 1.5; `powerPreference: "low-power"` mobile; pausa em `document.hidden`
  e quando a última seção sai (IntersectionObserver + fallback de scroll, mesmo
  padrão do FindScreen).
- `reduzido=true` (prefers-reduced-motion): renderiza UM frame bonito
  (feixe parado a ~40°, pontos acesos) e não anima nada.

## 6. Coreografia GSAP (LandingPage.jsx)

- `gsap.registerPlugin(ScrollTrigger)`; tudo dentro de `gsap.matchMedia()`:
  motion completo só em `(prefers-reduced-motion: no-preference)`; no modo
  reduzido o conteúdo nasce visível, sem trigger algum.
- **Page-load orquestrado** (timeline única, reveals escalonados):
  eyebrow → linhas do H1 (clip-path/y, stagger 0.08s) → sub → CTAs → stat vivo;
  `radar.ligar()` dispara junto. Nada de animar depois disso no hero.
- **Scrub global**: um ScrollTrigger (start topo, end fundo) com
  `onUpdate: (st) => radar.setProgresso(st.progress)`.
- **Por seção** (`once: true`, y+opacity, stagger): atos do "como funciona",
  frases do manifesto (LEDs acendem em sequência — caixinhas `--fosforo`),
  CTA final. Contador do stat: roll-up numérico (gsap to com snap) ao entrar.
- Cleanup React: `useEffect` retorna `mm.revert()` + `radar.dispose()`.

## 7. Conteúdo (PT-BR, literal)

**HERO**
- eyebrow (mono): `RADAR DE PREGÕES · LEI 14.133 · FONTE OFICIAL PNCP`
- H1: `O PNCP INTEIRO` / `NO SEU RADAR.`
- sub: `Busca ao vivo nos ~37 mil editais nacionais, margem e veredito
  calculados no preço esperado de disputa — sempre com a fonte oficial à vista.`
- CTAs: `Entrar no radar →` (primário) · `Ver como funciona ↓` (âncora)
- stat vivo: `{N} oportunidades recebendo propostas agora` + carimbo
  `fonte: PNCP ao vivo` (ver §8; se a API falhar, a linha INTEIRA some).

**COMO FUNCIONA** (3 atos, numeração mono `01·02·03`)
1. `DESCOBRIR` — `Varra o Brasil por palavra-chave ou navegue tudo aberto.
   Filtro de compra de verdade: sem credenciamento, sem leilão, sem ruído.`
2. `ANALISAR` — `Itens cruzados com o seu catálogo, margem no preço esperado
   de disputa (não no teto) e veredito honesto: Vale, Talvez ou Não vale —
   com a conta sempre à mostra.`
3. `DISPUTAR` — `Checklist de habilitação extraído do edital com citação
   verificada página por página, e o funil da disputa até o resultado.`
Cada ato: número gigante + mini-mockup estilizado da UI real (HTML/CSS, não
imagem), animando no scroll.

**MANIFESTO** (frases display gigantes, LED acende antes de cada uma)
- `NUNCA INVENTA.` — `Toda exigência sai com o trecho literal do edital,
  página e verificação. O que não foi achado fica marcado: não encontrado.`
- `FONTE OFICIAL SEMPRE À VISTA.` — `Valores e prazos vêm do PNCP. O link do
  edital oficial nunca sai da tela.`
- `A CONTA É SUA.` — `Custo é dado seu; simulação vem rotulada de simulação.
  O veredito nunca esconde os números.`

**CTA FINAL**
- H2: `PRONTO PARA O` / `PRÓXIMO PREGÃO?`
- botão `Entrar no radar →`
- rodapé (mono, pequeno) com os DOIS avisos fixos do §9 do CLAUDE.md, literais.

## 8. Dados vivos (honestidade)

- Ao montar: `api.descobrir({ pagina: 1 })` (fonte em massa; cache 6h no
  backend). Usa `total` no stat do hero.
- Falhou/timeout → a linha do stat NÃO renderiza (sem número fake, sem "—").
- Nenhum outro número inventado na página: os atos descrevem funções, não métricas.

## 9. Mobile & acessibilidade

- Tipografia 100% `clamp()`; seções empilham; alvos de toque ≥ 44px.
- Cena: 800 pontos, sem parallax de ponteiro, DPR 1, `low-power`.
- `prefers-reduced-motion: reduce` → cena estática 1 frame + conteúdo visível
  sem triggers (paridade com o `semFramer` do app).
- Teclado: CTAs são `<button>/<a>` reais com `:focus-visible` (padrão do app).
- Contraste AA: `--neve` sobre `--noite` ≈ 15:1; `--cinza` ≥ 4.6:1.

## 10. Verificação (aceite)

1. `npm run build` verde; chunk principal do app SEM three/gsap (conferir
   tamanhos no output do Vite).
2. Chrome DevTools via preview: console **zero erros** no load e após scroll
   até o fim; screenshots desktop (1440) e mobile (380) do hero e de mais
   duas seções como prova.
3. Primeira visita → landing; "Entrar no radar" → app; reload → direto no app;
   "Apresentação" na sidebar → landing de novo.
4. Backend intocado; 171 testes pytest seguem verdes.

## 11. Fora de escopo (YAGNI)

- Redesign das telas internas do app (fica para depois, com a linguagem da
  landing como referência).
- SEO/meta tags/OG image, multi-idioma, analytics, vídeo.
- Postprocessing/bloom no Three.js; horizontal scroll sections.
