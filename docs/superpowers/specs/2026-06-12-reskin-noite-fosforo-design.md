# Re-skin do app — "noite fósforo" (spec aprovada)

Data: 2026-06-12 · Status: aprovada pelo dono ("Bora executa tudo, n esqueça o cookbook")
Escopo: levar a linguagem visual da landing (dark verde-noite + fósforo) para o
app inteiro, **sem mudar layout, espaçamento, markup ou comportamento** —
CSS-only (exceto 4 cores inline no JSX do app). A landing NÃO muda.

## 1. Princípios (cookbook `prompting_for_frontend_aesthetics.ipynb`)

- Cor dominante (verde-noite) com acentos nítidos (fósforo) — nunca paleta
  tímida distribuída. Inspiração: temas de IDE (o app é uma mesa de operação
  noturna, não uma landing — atmosfera mais contida que a LP).
- Coesão 100% via CSS variables.
- Anti "AI slop": nada de roxo, nada de glow em tudo — fósforo só onde há
  VIDA (LEDs, foco, estado ativo, veredito).
- Tipografia intocada (Big Shoulders/Archivo/Plex Mono já são a marca).
- Sem motion novo (Framer existente fica como está).

## 2. Tokens — mesmos NOMES, novos VALORES (zero risco de referência quebrada)

```css
--aluminio: #0A0F0D;   /* era #E4E7E1 — chassi vira noite */
--painel:   #101713;   /* era #FAFBF8 — faces de painel noturno */
--tinta:    #E9F2EC;   /* era #171C1A — TEXTO principal vira neve */
--tinta-2:  #B9C6BE;   /* era #3C443F — texto secundário claro */
--silk:     #7C8A81;   /* era #69716C — labels mono (mesma família) */
--linha:    #1F2A24;   /* era #CDD2CA — hairlines escuras */
--sinal:    #2BD97F;   /* era #149357 — fósforo */
--pico:     #E0A21B;   /* era #C98A04 */
--clip:     #E25A4A;   /* era #CC4537 */
--led-off:  rgba(43, 217, 127, 0.10);
/* novos auxiliares permitidos: */
--fundo-2:  #0D1411;   /* superfícies intermediárias (linhas zebradas, wells) */
--halo:     rgba(43, 217, 127, 0.14);  /* bordas/glows de estado vivo */
```
Comentário do bloco atualizado com nota datada (nomes são históricos da
"mesa de operação"; valores agora são o turno da noite).

## 3. REGRA DE OURO do sweep (não é swap cego)

`--tinta` hoje é usada com DOIS sentidos: superfície escura (ex.: sidebar
`background: var(--tinta)`) e cor de texto. Com o novo valor (neve), todo uso
como SUPERFÍCIE precisa ser re-mapeado à mão:
- **Sidebar**: fundo `#050807` (mais profunda que o chassi), texto `#E9F2EC`,
  labels --silk, item ativo com LED/borda fósforo (hoje deve usar inversão
  clara — re-ler cada regra).
- Botões "primários" escuros (fundo --tinta, texto claro) viram **fósforo
  sobre noite** (`background: var(--sinal); color: #0A0F0D`) — mesmo padrão
  do .ld-cta da landing.
- Qualquer `color: #fff`/claro sobre o que ERA escuro: re-avaliar par a par.
Os ~127 hex + ~72 rgba() hardcoded do styles.css passam TODOS por revisão
semântica: sombras claras → sombras pretas (`rgba(0,0,0,0.5)` típicas) +
hairline --linha; brancos de texto → --tinta (neve) ou #0A0F0D quando sobre
fósforo; verdes/âmbares/vermelhos antigos → --sinal/--pico/--clip.

## 4. Regras por componente

- **Superfícies**: chassi --aluminio; cards/painéis --painel com borda
  `1px solid var(--linha)`; hover eleva com borda `rgba(124,138,129,0.35)`
  (nunca sombra clara). Zebra/wells: --fundo-2.
- **Inputs/selects/textareas**: fundo `#0A0F0D`, borda --linha, texto neve,
  placeholder --silk; foco `outline: 2px solid var(--sinal)` (o :focus-visible
  global muda de --tinta para --sinal).
- **LEDs e vereditos**: semântica intocada — Vale/ok = --sinal, Talvez/atenção
  = --pico, Não vale/erro = --clip. Glow fósforo APENAS nesses estados.
- **Tabelas** (itens da análise): linhas com hairline --linha, hover
  --fundo-2, números mono neve; chips de simulação mantêm rótulo e ganham
  contraste AA.
- **Kanban/funil**: colunas --fundo-2, cartões --painel, faixa-resumo com
  números fósforo.
- **Skeletons**: base `#101713`, brilho `rgba(124,138,129,0.12)`.
- **Toasts/erros**: fundo --painel, borda na cor semântica.
- **Atmosfera**: o body do app pode ganhar os radial-gradients fosforosos da
  landing a ~4% de opacidade (mais discretos — é ferramenta de trabalho).
- **JSX inline** (4 pontos: helpers.jsx ×3, App.jsx ×1): mapear às variáveis.
- **Contraste AA**: texto secundário ≥ 4.5:1 sobre --painel; conferir --silk
  (#7C8A81 sobre #101713 ≈ 4.9:1, ok) e --tinta-2.

## 5. Fora de escopo

Layout/espaçamento/markup; motion novo; landing (pronta); backend; modo claro
(o tema claro antigo morre — sem toggle).

## 6. Aceite

1. `npm run build` verde; 172 pytest intactos (backend não é tocado).
2. Preview (Chrome DevTools): console zero erros; screenshots de TODAS as
   telas — Encontrar (radar + ao vivo), Análise de um pregão, Meus pregões
   (lista + quadro), Buscas salvas, Meu catálogo.
3. Grep final: nenhum hex claro órfão (#E4E7E1, #FAFBF8, #CDD2CA, #fff sobre
   fundo claro) remanescente no styles.css.
4. Revisão crítica (opus-reviewer) antes do aceite.
