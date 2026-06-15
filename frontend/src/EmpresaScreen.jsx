// RADAR DE PREGÕES — Tela "Minha empresa"
// Cadastro do fornecedor (razão social, CNPJ, endereço, representante legal,
// porte). Esses dados preenchem automaticamente as MINUTAS de declaração de
// habilitação (aba Declarações de cada pregão, RAG Fase 3). Carrega via
// getEmpresa; salva via salvarEmpresa (PUT). Campos podem vir null.
import React from "react";
import { motion } from "framer-motion";
import { api } from "./api.js";
import { MotionCtx, Ico } from "./helpers.jsx";
import { EstadoCarregando, EstadoErro } from "./FindScreen.jsx";

const FORM_VAZIO = {
  razao_social: "",
  cnpj: "",
  endereco: "",
  representante_nome: "",
  representante_cpf: "",
  representante_cargo: "",
  porte: "",
};

// backend → form (null vira string vazia; porte fora do enum vira "")
function deBackend(e) {
  if (!e) return { ...FORM_VAZIO };
  return {
    razao_social: e.razao_social || "",
    cnpj: e.cnpj || "",
    endereco: e.endereco || "",
    representante_nome: e.representante_nome || "",
    representante_cpf: e.representante_cpf || "",
    representante_cargo: e.representante_cargo || "",
    porte: e.porte === "me_epp" || e.porte === "normal" ? e.porte : "",
  };
}

// form → backend (string vazia vira null; porte "" vira null)
function paraBackend(f) {
  const t = (v) => (v && v.trim() ? v.trim() : null);
  return {
    razao_social: t(f.razao_social),
    cnpj: t(f.cnpj),
    endereco: t(f.endereco),
    representante_nome: t(f.representante_nome),
    representante_cpf: t(f.representante_cpf),
    representante_cargo: t(f.representante_cargo),
    porte: f.porte === "me_epp" || f.porte === "normal" ? f.porte : null,
  };
}

export default function EmpresaScreen({ avisar }) {
  const { reduzido, estatico } = React.useContext(MotionCtx);
  const [form, setForm] = React.useState(null);   // null = carregando
  const [erro, setErro] = React.useState(null);
  const [salvando, setSalvando] = React.useState(false);
  const [salvo, setSalvo] = React.useState(false);

  const carregar = React.useCallback(() => {
    setErro(null);
    setForm(null);
    api.getEmpresa()
      .then((e) => setForm(deBackend(e)))
      .catch((e) => setErro(e.message || "erro"));
  }, []);
  React.useEffect(() => { carregar(); }, [carregar]);

  const campo = (k) => (e) => {
    const v = e.target.value;
    setSalvo(false);
    setForm((f) => ({ ...f, [k]: v }));
  };

  const aoSalvar = (e) => {
    e.preventDefault();
    if (salvando || !form) return;
    setSalvando(true);
    api.salvarEmpresa(paraBackend(form))
      .then((res) => {
        if (res) setForm(deBackend(res));
        setSalvo(true);
        if (avisar) avisar("Dados da empresa salvos.", "ok");
      })
      .catch((err) => {
        if (avisar) avisar("Não foi possível salvar: " + (err.message || "erro"), "erro");
      })
      .finally(() => setSalvando(false));
  };

  const carregando = form == null && !erro;

  return (
    <motion.div className="screen-inner"
      initial={estatico ? false : reduzido ? { opacity: 0 } : { opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reduzido ? { duration: 0.15 } : { type: "spring", stiffness: 300, damping: 30 }}>
      <div className="silk">Cadastro do fornecedor</div>
      <h1 className="pg-titulo">Minha empresa</h1>
      <p className="pg-sub">
        Estes dados preenchem automaticamente as minutas de declaração de
        habilitação (aba Declarações de cada pregão). Confira sempre o texto
        gerado antes de assinar — é apoio, não orientação jurídica.
      </p>

      {carregando ? (
        <EstadoCarregando />
      ) : erro ? (
        <EstadoErro mensagem={erro} recarregar={carregar} />
      ) : (
        <div className="mod form-mod" style={{ marginTop: "14px" }}>
          <div className="silk">Dados cadastrais</div>
          <form className="form-linhas" onSubmit={aoSalvar} style={{ flexDirection: "column", alignItems: "stretch" }}>
            <label className="emp-label">
              <span className="silk">Razão social</span>
              <input className="form-input longa" value={form.razao_social}
                onChange={campo("razao_social")} placeholder="Razão social da empresa"
                aria-label="Razão social" />
            </label>

            <div className="emp-linha">
              <label className="emp-label">
                <span className="silk">CNPJ</span>
                <input className="form-input" value={form.cnpj} onChange={campo("cnpj")}
                  placeholder="00.000.000/0000-00" aria-label="CNPJ" />
              </label>
              <label className="emp-label">
                <span className="silk">Porte</span>
                <select className="form-input" value={form.porte} onChange={campo("porte")}
                  aria-label="Porte da empresa">
                  <option value="">— não informado —</option>
                  <option value="me_epp">ME/EPP</option>
                  <option value="normal">Demais (não ME/EPP)</option>
                </select>
              </label>
            </div>

            <label className="emp-label">
              <span className="silk">Endereço</span>
              <input className="form-input longa" value={form.endereco}
                onChange={campo("endereco")} placeholder="Endereço completo"
                aria-label="Endereço" />
            </label>

            <div className="silk" style={{ marginTop: "10px" }}>Representante legal</div>
            <div className="emp-linha">
              <label className="emp-label">
                <span className="silk">Nome</span>
                <input className="form-input" value={form.representante_nome}
                  onChange={campo("representante_nome")} placeholder="Nome do representante"
                  aria-label="Nome do representante" />
              </label>
              <label className="emp-label">
                <span className="silk">CPF</span>
                <input className="form-input" value={form.representante_cpf}
                  onChange={campo("representante_cpf")} placeholder="000.000.000-00"
                  aria-label="CPF do representante" />
              </label>
              <label className="emp-label">
                <span className="silk">Cargo</span>
                <input className="form-input" value={form.representante_cargo}
                  onChange={campo("representante_cargo")} placeholder="Ex.: Sócio-administrador"
                  aria-label="Cargo do representante" />
              </label>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "12px", marginTop: "12px" }}>
              <button type="submit" className="btn-rodar" disabled={salvando}
                style={{ color: "var(--sobre-acento)" }}>
                {salvando
                  ? <React.Fragment><span className="spin" aria-hidden="true"></span> Salvando…</React.Fragment>
                  : <React.Fragment>{Ico.check} Salvar dados</React.Fragment>}
              </button>
              {salvo && !salvando && (
                <span className="silk" style={{ color: "var(--sinal)" }} role="status">Salvo.</span>
              )}
            </div>
          </form>
        </div>
      )}
    </motion.div>
  );
}
