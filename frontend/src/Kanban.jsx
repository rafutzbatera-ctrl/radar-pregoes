// RADAR DE PREGÕES — quadro do funil de disputa (P2). Sem drag & drop:
// mudança de status por select (acessível); data/valor editáveis no cartão.
import React from "react";
import { fmtBRL, Etiqueta, normalizarVeredito } from "./helpers.jsx";

export const STATUS_PIPELINE = [
  { id: "cotacao", rotulo: "Cotação" },
  { id: "habilitacao", rotulo: "Habilitação" },
  { id: "disputando", rotulo: "Disputando" },
  { id: "ganho", rotulo: "Ganho" },
  { id: "perdido", rotulo: "Perdido" },
  { id: "suspenso", rotulo: "Suspenso" },
];

function ordenarPorDisputa(a, b) {
  if (!a.dataDisputa && !b.dataDisputa) return 0;
  if (!a.dataDisputa) return 1;   // sem data vai para o fim
  if (!b.dataDisputa) return -1;
  return a.dataDisputa < b.dataDisputa ? -1 : 1;
}

export function Kanban({ pregoes, aoAbrir, mudarPipeline }) {
  return (
    <div className="kanban" role="list" aria-label="Funil de disputa">
      {STATUS_PIPELINE.map((col) => {
        const cards = (pregoes || [])
          .filter((p) => (p.statusPipeline || "cotacao") === col.id)
          .sort(ordenarPorDisputa);
        return (
          <section key={col.id} className="kanban-col" role="listitem">
            <h3 className="kanban-cab silk">
              {col.rotulo} <span className="kanban-n">{cards.length}</span>
            </h3>
            <div className="kanban-cards">
              {cards.map((p) => (
                <CartaoFunil key={p.id} pregao={p} aoAbrir={aoAbrir}
                             mudarPipeline={mudarPipeline} />
              ))}
              {!cards.length && <div className="kanban-vazio silk">—</div>}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function CartaoFunil({ pregao, aoAbrir, mudarPipeline }) {
  const veredito = normalizarVeredito(pregao.agregados?.veredito);
  return (
    <article className="kanban-card mod">
      <button type="button" className="kanban-titulo" onClick={() => aoAbrir(pregao.id)}>
        {pregao.titulo}
      </button>
      <div className="kanban-orgao">{pregao.orgao || "—"}</div>
      <div className="kanban-meta mono">
        {pregao.valorTotal != null ? fmtBRL(pregao.valorTotal) : "valor —"}
        {veredito && <Etiqueta veredito={veredito} />}
      </div>
      <label className="silk kanban-campo">
        status
        <select className="filtro-sel" value={pregao.statusPipeline || "cotacao"}
                onChange={(e) => mudarPipeline(pregao.id, { status_pipeline: e.target.value })}>
          {STATUS_PIPELINE.map((s) => (
            <option key={s.id} value={s.id}>{s.rotulo}</option>
          ))}
        </select>
      </label>
      <label className="silk kanban-campo">
        disputa
        <input type="datetime-local" className="form-input mono"
               value={paraInputDt(pregao.dataDisputa)}
               onChange={(e) => mudarPipeline(pregao.id, { data_disputa: deInputDt(e.target.value) })} />
      </label>
      {(pregao.statusPipeline === "ganho" || pregao.valorFinal != null) && (
        <label className="silk kanban-campo">
          valor final (R$)
          <input type="number" step="0.01" min="0" className="form-input mono"
                 defaultValue={pregao.valorFinal ?? ""}
                 onBlur={(e) => mudarPipeline(pregao.id, {
                   valor_final: e.target.value === "" ? null : Number(e.target.value),
                 })} />
        </label>
      )}
    </article>
  );
}

// "2026-06-20 09:00" ⇄ "2026-06-20T09:00" (datetime-local)
const paraInputDt = (v) => (v ? v.replace(" ", "T").slice(0, 16) : "");
const deInputDt = (v) => (v ? v.replace("T", " ") : null);
