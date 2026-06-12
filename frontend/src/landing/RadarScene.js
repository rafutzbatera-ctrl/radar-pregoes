import * as THREE from "three";

/* ======================================================================
 * RadarScene — radar fosforescente tipo CRT (Three.js puro, sem React).
 *
 * Contrato fechado (spec 2026-06-12 §5). LandingPage só fala esta API:
 *   constructor(canvas, { reduzido, mobile })
 *   ligar()          boot CRT ~1.6s + rAF (reduzido: UM frame, sem rAF)
 *   setProgresso(p)  0..1 — define ALVOS de feixe/tilt/zoom (lerp no rAF)
 *   setPonteiro(x,y) -1..1 — parallax sutil (no-op no mobile)
 *   pausar() retomar()
 *   dispose()        rAF cancelado, listeners fora, GPU liberada
 *
 * Glow barato: additive blending + falloff exponencial no fragment.
 * Sem postprocessing/bloom. Brilho CONTIDO — o texto --neve continua AA.
 * ==================================================================== */

const COR_FOSFORO = new THREE.Color(0x2bd97f);
const COR_AMBAR = new THREE.Color(0xe0a21b);
const COR_RUBI = new THREE.Color(0xe25a4a);

const TAU = Math.PI * 2;
const GRAU = Math.PI / 180;

// Alvos por progresso (interpolados): p=0 calmo, p=1 acelerado/fechado.
const FEIXE_LENTO = 0.5; // rad/s
const FEIXE_RAPIDO = 1.4; // rad/s
const TILT_ABERTO = 35 * GRAU;
const TILT_FECHADO = 18 * GRAU;
const ZOOM_BASE = 1.0;
const ZOOM_FECHADO = 1.18;

export default class RadarScene {
  constructor(canvas, { reduzido = false, mobile = false } = {}) {
    this.canvas = canvas;
    this.reduzido = reduzido;
    this.mobile = mobile;

    this.raioGrade = 4.2;
    this.qtdPontos = mobile ? 800 : 3000;

    // Estado de animação
    this.rafId = 0;
    this._ultimoTs = 0; // delta manual via performance.now (THREE.Clock está deprecado)
    this.tempo = 0;
    this.anguloFeixe = 0;
    this.bootInicio = 0;
    this.pausado = false;
    this.rodando = false;

    // Alvos (setProgresso) e valores correntes (lerp suave no rAF)
    this.alvoVelFeixe = FEIXE_LENTO;
    this.alvoTilt = TILT_ABERTO;
    this.alvoZoom = ZOOM_BASE;
    this.velFeixe = FEIXE_LENTO;
    this.tilt = TILT_ABERTO;
    this.zoom = ZOOM_BASE;

    // Parallax de ponteiro (no-op mobile)
    this.ponteiroX = 0;
    this.ponteiroY = 0;
    this.ponteiroAlvoX = 0;
    this.ponteiroAlvoY = 0;

    this._construirRenderer();
    this._construirCena();
    this._construirGrade();
    this._construirPontos();
    this._construirFeixe();

    this._aoRedimensionar = this._aoRedimensionar.bind(this);
    this._aoMudarVisibilidade = this._aoMudarVisibilidade.bind(this);
    this._loop = this._loop.bind(this);
    window.addEventListener("resize", this._aoRedimensionar);
    document.addEventListener("visibilitychange", this._aoMudarVisibilidade);

    this._aoRedimensionar();
  }

  /* ---------------- construção ---------------- */

  _construirRenderer() {
    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      antialias: false,
      alpha: true,
      powerPreference: this.mobile ? "low-power" : "high-performance",
    });
    const dprMax = this.mobile ? 1 : 1.5;
    this.dpr = Math.min(window.devicePixelRatio || 1, dprMax);
    this.renderer.setPixelRatio(this.dpr);
    this.renderer.setClearColor(0x000000, 0); // fundo do canvas vem do CSS (--noite)
  }

  _construirCena() {
    this.cena = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    // Pivô que inclina o plano polar (tilt da câmera = inclinação do radar).
    this.pivo = new THREE.Group();
    this.cena.add(this.pivo);
  }

  _construirGrade() {
    const pos = [];
    const aRaio = []; // raio normalizado 0..1 de cada vértice (boot acende de dentro pra fora)
    const aneis = 5;
    const segCirc = 96;

    // Anéis concêntricos
    for (let k = 1; k <= aneis; k++) {
      const r = (k / aneis) * this.raioGrade;
      const rn = k / aneis;
      for (let s = 0; s < segCirc; s++) {
        const a0 = (s / segCirc) * TAU;
        const a1 = ((s + 1) / segCirc) * TAU;
        pos.push(Math.cos(a0) * r, 0, Math.sin(a0) * r);
        pos.push(Math.cos(a1) * r, 0, Math.sin(a1) * r);
        aRaio.push(rn, rn);
      }
    }
    // Radiais
    const radiais = 12;
    for (let i = 0; i < radiais; i++) {
      const a = (i / radiais) * TAU;
      pos.push(0, 0, 0);
      pos.push(Math.cos(a) * this.raioGrade, 0, Math.sin(a) * this.raioGrade);
      aRaio.push(0, 1);
    }

    this.gradeGeo = new THREE.BufferGeometry();
    this.gradeGeo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    this.gradeGeo.setAttribute("aRaio", new THREE.Float32BufferAttribute(aRaio, 1));

    this.gradeMat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uBoot: { value: 0 },
        uCor: { value: COR_FOSFORO.clone() },
        uOpacidade: { value: 0.06 },
      },
      vertexShader: /* glsl */ `
        attribute float aRaio;
        uniform float uBoot;
        varying float vAcende;
        void main() {
          // anel acende quando a frente do boot (uBoot) ultrapassa seu raio.
          float frente = uBoot * 1.15;
          vAcende = smoothstep(frente, frente - 0.28, aRaio);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: /* glsl */ `
        precision mediump float;
        uniform vec3 uCor;
        uniform float uOpacidade;
        varying float vAcende;
        void main() {
          gl_FragColor = vec4(uCor, uOpacidade * vAcende);
        }
      `,
    });

    this.grade = new THREE.LineSegments(this.gradeGeo, this.gradeMat);
    this.pivo.add(this.grade);
  }

  _construirPontos() {
    const n = this.qtdPontos;
    const aAngulo = new Float32Array(n);
    const aRaio = new Float32Array(n);
    const aTipo = new Float32Array(n);
    const aSeed = new Float32Array(n);

    // 6-8 clusters gaussianos (regiões do país, abstrato).
    const nClusters = this.mobile ? 6 : 8;
    const clusters = [];
    for (let c = 0; c < nClusters; c++) {
      clusters.push({
        ang: Math.random() * TAU,
        raio: 0.25 + Math.random() * 0.7, // 0..1 do raio da grade
        espalhaAng: 0.18 + Math.random() * 0.22,
        espalhaRaio: 0.06 + Math.random() * 0.1,
      });
    }

    for (let i = 0; i < n; i++) {
      // 78% dos pontos em clusters; 22% campo difuso (preenche a varredura).
      let ang, rn;
      if (Math.random() < 0.78) {
        const c = clusters[(Math.random() * nClusters) | 0];
        ang = c.ang + gauss() * c.espalhaAng;
        rn = clamp01(c.raio + gauss() * c.espalhaRaio);
      } else {
        ang = Math.random() * TAU;
        rn = Math.sqrt(Math.random()); // densidade uniforme por área
      }
      aAngulo[i] = ang;
      aRaio[i] = 0.06 + rn * 0.94; // evita amontoar no centro
      aSeed[i] = Math.random();

      // ~97% fósforo, ~3% âmbar/rubi (metade cada).
      const r = Math.random();
      aTipo[i] = r < 0.97 ? 0 : r < 0.985 ? 1 : 2;
    }

    this.pontosGeo = new THREE.BufferGeometry();
    // posição base obrigatória (recomputada no shader a partir de ângulo/raio)
    this.pontosGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(n * 3), 3));
    this.pontosGeo.setAttribute("aAngulo", new THREE.BufferAttribute(aAngulo, 1));
    this.pontosGeo.setAttribute("aRaio", new THREE.BufferAttribute(aRaio, 1));
    this.pontosGeo.setAttribute("aTipo", new THREE.BufferAttribute(aTipo, 1));
    this.pontosGeo.setAttribute("aSeed", new THREE.BufferAttribute(aSeed, 1));

    this.pontosMat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      depthTest: false,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uTempo: { value: 0 },
        uFeixe: { value: 0 },
        uBoot: { value: 0 },
        uPixelRatio: { value: this.dpr },
        uRaioGrade: { value: this.raioGrade },
        uTamanho: { value: this.mobile ? 46 : 64 },
        uCorFosforo: { value: COR_FOSFORO.clone() },
        uCorAmbar: { value: COR_AMBAR.clone() },
        uCorRubi: { value: COR_RUBI.clone() },
      },
      vertexShader: /* glsl */ `
        attribute float aAngulo;
        attribute float aRaio;
        attribute float aTipo;
        attribute float aSeed;
        uniform float uTempo;
        uniform float uFeixe;
        uniform float uBoot;
        uniform float uPixelRatio;
        uniform float uRaioGrade;
        uniform float uTamanho;
        varying float vBrilho;
        varying float vTipo;

        const float TAU = 6.2831853;

        void main() {
          float r = aRaio * uRaioGrade;
          // respiração leve para a cena nunca ficar morta
          float resp = 1.0 + 0.012 * sin(uTempo * 0.7 + aSeed * 12.0);
          vec3 p = vec3(cos(aAngulo) * r * resp, 0.0, sin(aAngulo) * r * resp);

          // rastro fosforescente: distância angular ATRÁS do feixe (sentido +).
          float dif = mod(uFeixe - aAngulo, TAU);          // 0 = feixe em cima
          float rastro = exp(-dif * 2.2);                  // decaimento exponencial
          float frenteBoot = smoothstep(uBoot * 1.15, uBoot * 1.15 - 0.3, aRaio);
          float cintila = 0.85 + 0.15 * sin(uTempo * 2.3 + aSeed * 30.0);
          vBrilho = (0.18 + rastro) * frenteBoot * cintila;
          vTipo = aTipo;

          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          gl_Position = projectionMatrix * mv;
          // size attenuation + ponto maior quando aceso pelo feixe
          float tamBase = uTamanho * (1.0 + rastro * 0.9);
          gl_PointSize = tamBase * uPixelRatio / max(-mv.z, 0.001);
        }
      `,
      fragmentShader: /* glsl */ `
        precision mediump float;
        uniform vec3 uCorFosforo;
        uniform vec3 uCorAmbar;
        uniform vec3 uCorRubi;
        varying float vBrilho;
        varying float vTipo;

        void main() {
          // disco suave (sprite radial via smoothstep) — núcleo + halo barato
          vec2 uv = gl_PointCoord - 0.5;
          float d = length(uv);
          float disco = smoothstep(0.5, 0.0, d);
          float nucleo = smoothstep(0.18, 0.0, d);
          float a = disco * 0.55 + nucleo * 0.45;

          vec3 cor = uCorFosforo;
          if (vTipo > 1.5) cor = uCorRubi;
          else if (vTipo > 0.5) cor = uCorAmbar;

          float intens = clamp(vBrilho, 0.0, 1.6);
          // alpha contido: glow vem do additive, não de alpha estourado.
          gl_FragColor = vec4(cor * intens, a * intens);
        }
      `,
    });

    this.pontos = new THREE.Points(this.pontosGeo, this.pontosMat);
    this.pontos.frustumCulled = false;
    this.pivo.add(this.pontos);
  }

  _construirFeixe() {
    // Cunha de ~70° varrendo, com gradiente angular de alpha (forte na borda
    // dianteira, some no rastro). Geometria leve (anel de setor triangulado).
    const segs = 40;
    const meiaAbertura = 35 * GRAU; // cunha de 70°
    const rInt = 0.05;
    const rExt = this.raioGrade;
    const pos = [];
    const aFrac = []; // 0 na borda traseira → 1 na borda dianteira da cunha

    for (let s = 0; s < segs; s++) {
      const f0 = s / segs;
      const f1 = (s + 1) / segs;
      const a0 = -meiaAbertura + f0 * (2 * meiaAbertura);
      const a1 = -meiaAbertura + f1 * (2 * meiaAbertura);
      const x0i = Math.cos(a0) * rInt, z0i = Math.sin(a0) * rInt;
      const x0e = Math.cos(a0) * rExt, z0e = Math.sin(a0) * rExt;
      const x1i = Math.cos(a1) * rInt, z1i = Math.sin(a1) * rInt;
      const x1e = Math.cos(a1) * rExt, z1e = Math.sin(a1) * rExt;
      // dois triângulos por segmento
      pos.push(x0i, 0, z0i, x0e, 0, z0e, x1e, 0, z1e);
      aFrac.push(f0, f0, f1);
      pos.push(x0i, 0, z0i, x1e, 0, z1e, x1i, 0, z1i);
      aFrac.push(f0, f1, f1);
    }

    this.feixeGeo = new THREE.BufferGeometry();
    this.feixeGeo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    this.feixeGeo.setAttribute("aFrac", new THREE.Float32BufferAttribute(aFrac, 1));

    this.feixeMat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      depthTest: false,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
      uniforms: {
        uBoot: { value: 0 },
        uCor: { value: COR_FOSFORO.clone() },
        uForca: { value: 0.16 }, // alpha de pico contido (não estoura o texto)
      },
      vertexShader: /* glsl */ `
        attribute float aFrac;
        varying float vFrac;
        varying float vRaio;
        void main() {
          vFrac = aFrac;
          vRaio = length(position.xz);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: /* glsl */ `
        precision mediump float;
        uniform vec3 uCor;
        uniform float uForca;
        uniform float uBoot;
        varying float vFrac;
        varying float vRaio;
        void main() {
          // gradiente angular: brilho concentrado na borda dianteira (frac=1)
          float ang = pow(clamp(vFrac, 0.0, 1.0), 2.4);
          // some na ponta do raio para não desenhar borda dura
          float rad = smoothstep(4.2, 1.4, vRaio);
          float a = ang * (0.35 + 0.65 * rad) * uForca * uBoot;
          gl_FragColor = vec4(uCor, a);
        }
      `,
    });

    this.feixe = new THREE.Mesh(this.feixeGeo, this.feixeMat);
    this.feixe.frustumCulled = false;
    this.pivo.add(this.feixe);
  }

  /* ---------------- API pública ---------------- */

  ligar() {
    if (this.reduzido) {
      // Um frame bonito: boot completo, feixe parado a ~40°, sem rAF.
      this._aplicarUniformsEstaticos();
      this._posicionarCamera();
      this.renderer.render(this.cena, this.camera);
      return;
    }
    if (this.rodando) return;
    this.rodando = true;
    this.pausado = false;
    this.bootInicio = performance.now();
    this._ultimoTs = performance.now();
    this.rafId = requestAnimationFrame(this._loop);
  }

  setProgresso(p) {
    const t = clamp01(p);
    this.alvoVelFeixe = FEIXE_LENTO + (FEIXE_RAPIDO - FEIXE_LENTO) * t;
    this.alvoTilt = TILT_ABERTO + (TILT_FECHADO - TILT_ABERTO) * t;
    this.alvoZoom = ZOOM_BASE + (ZOOM_FECHADO - ZOOM_BASE) * t;
  }

  setPonteiro(x, y) {
    if (this.mobile || this.reduzido) return; // no-op mobile
    this.ponteiroAlvoX = clamp(x, -1, 1);
    this.ponteiroAlvoY = clamp(y, -1, 1);
  }

  pausar() {
    if (!this.rodando) return;
    this.pausado = true;
    if (this.rafId) {
      cancelAnimationFrame(this.rafId);
      this.rafId = 0;
    }
  }

  retomar() {
    if (!this.rodando || !this.pausado || this.reduzido) return;
    this.pausado = false;
    // evita salto de dt após pausa longa
    this._ultimoTs = performance.now();
    // nunca dois loops concorrentes (toggles rápidos de visibilidade)
    if (this.rafId) cancelAnimationFrame(this.rafId);
    this.rafId = requestAnimationFrame(this._loop);
  }

  dispose() {
    this.rodando = false;
    if (this.rafId) {
      cancelAnimationFrame(this.rafId);
      this.rafId = 0;
    }
    window.removeEventListener("resize", this._aoRedimensionar);
    document.removeEventListener("visibilitychange", this._aoMudarVisibilidade);

    const geos = [this.gradeGeo, this.pontosGeo, this.feixeGeo];
    const mats = [this.gradeMat, this.pontosMat, this.feixeMat];
    geos.forEach((g) => g && g.dispose());
    mats.forEach((m) => m && m.dispose());
    if (this.renderer) {
      this.renderer.dispose();
      // libera o contexto WebGL (evita "too many contexts" ao reabrir a landing)
      const ext = this.renderer.getContext().getExtension("WEBGL_lose_context");
      if (ext) ext.loseContext();
    }
    this.cena = null;
    this.camera = null;
  }

  /* ---------------- internos ---------------- */

  _aoRedimensionar() {
    if (!this.renderer || !this.camera) return;
    const w = window.innerWidth;
    const h = window.innerHeight;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / Math.max(h, 1);
    this.camera.updateProjectionMatrix();
    if (this.reduzido) {
      // re-render do frame estático no resize
      this._posicionarCamera();
      this.renderer.render(this.cena, this.camera);
    }
  }

  _aoMudarVisibilidade() {
    if (this.reduzido) return;
    if (document.hidden) this.pausar();
    else this.retomar();
  }

  _aplicarUniformsEstaticos() {
    this.gradeMat.uniforms.uBoot.value = 1;
    this.pontosMat.uniforms.uBoot.value = 1;
    this.pontosMat.uniforms.uFeixe.value = 40 * GRAU;
    this.pontosMat.uniforms.uTempo.value = 0;
    this.feixeMat.uniforms.uBoot.value = 1;
    this.anguloFeixe = 40 * GRAU;
    this.feixe.rotation.y = -this.anguloFeixe;
    // tilt/zoom no estado aberto
    this.tilt = TILT_ABERTO;
    this.zoom = ZOOM_BASE;
  }

  _posicionarCamera() {
    // Câmera olhando o centro; tilt = inclinação do plano (gira o pivô em X).
    this.pivo.rotation.x = this.tilt;
    // parallax sutil do pivô
    this.pivo.rotation.z = this.ponteiroX * 0.04;
    this.pivo.position.x = this.ponteiroX * 0.12;
    this.pivo.position.y = -this.ponteiroY * 0.08;

    const dist = 9.5 / this.zoom;
    this.camera.position.set(0, dist * 0.62, dist * 0.78);
    this.camera.lookAt(0, 0, 0);
  }

  _loop() {
    if (!this.rodando || this.pausado) return;
    this.rafId = requestAnimationFrame(this._loop);

    const agora = performance.now();
    const dt = Math.min((agora - this._ultimoTs) / 1000, 0.05); // clamp p/ estabilidade
    this._ultimoTs = agora;
    this.tempo += dt;

    // boot 0→1 em 1.6s (easeOut cúbico)
    const tBoot = Math.min((performance.now() - this.bootInicio) / 1600, 1);
    const boot = 1 - Math.pow(1 - tBoot, 3);

    // lerp suave dos alvos (responde ao scroll sem saltos)
    this.velFeixe += (this.alvoVelFeixe - this.velFeixe) * 0.05;
    this.tilt += (this.alvoTilt - this.tilt) * 0.05;
    this.zoom += (this.alvoZoom - this.zoom) * 0.05;
    this.ponteiroX += (this.ponteiroAlvoX - this.ponteiroX) * 0.06;
    this.ponteiroY += (this.ponteiroAlvoY - this.ponteiroY) * 0.06;

    // varredura
    this.anguloFeixe = (this.anguloFeixe + dt * this.velFeixe) % TAU;
    this.feixe.rotation.y = -this.anguloFeixe; // alinha a cunha com o ângulo

    // uniforms
    this.gradeMat.uniforms.uBoot.value = boot;
    this.pontosMat.uniforms.uBoot.value = boot;
    this.pontosMat.uniforms.uTempo.value = this.tempo;
    this.pontosMat.uniforms.uFeixe.value = this.anguloFeixe;
    this.feixeMat.uniforms.uBoot.value = boot;

    this._posicionarCamera();
    this.renderer.render(this.cena, this.camera);
  }
}

/* ---------------- helpers ---------------- */

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}
function clamp01(v) {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}
// Aproximação gaussiana barata (soma de uniformes — Irwin-Hall), média 0.
function gauss() {
  return (Math.random() + Math.random() + Math.random() - 1.5) * 0.9;
}
