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
