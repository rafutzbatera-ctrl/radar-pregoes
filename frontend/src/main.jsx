// RADAR DE PREGÕES — entry do app real (Vite). Sem boot/watchdog de rAF:
// aquilo era contorno para iframes ocultos do protótipo. O modo reduzido
// vem de useReducedMotion (framer-motion) dentro do App.
import React from "react";
import ReactDOM from "react-dom/client";
import "./styles.css";
import App from "./App.jsx";

// Tema: restaura a escolha ANTES do render (sem flash). Escuro "noite fósforo"
// é o padrão; só o claro grava no localStorage. A landing fica sempre dark.
if (localStorage.getItem("radar_tema") === "claro") {
  document.documentElement.dataset.tema = "claro";
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
