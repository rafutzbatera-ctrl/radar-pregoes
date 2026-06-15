// RADAR DE PREGÕES — Tela "Minhas certidões"
// O fornecedor guarda suas certidões/documentos de habilitação (CND federal,
// FGTS, trabalhista etc.) com data de validade; o sistema avisa quando estão
// vencidas ou perto de vencer — para não perder pregão por documento expirado.
// Dados reais via API (status/dias_restantes calculados no backend a partir de
// hoje). Mutações otimistas → API → reverte + toast como o resto do app.
import React from "react";
import { motion } from "framer-motion";
import { api } from "./api.js";
import { MotionCtx, Ico } from "./helpers.jsx";
import { EstadoCarregando, EstadoErro } from "./FindScreen.jsx";

const FORM_VAZIO = { nome: "", orgao_emissor: "", validade: "", observacao: "" };

// rótulo + cor (CSS var) por status calculado pelo backend
const STATUS_META = {
  vencida: { rotulo: "Vencida", cor: "var(--clip)" },
  vence_em_breve: { rotulo: "Vence em breve", cor: "var(--pico)" },
  ok: { rotulo: "Em dia", cor: "var(--sinal)" },
  sem_validade: { rotulo: "Sem validade", cor: "var(--silk)" },
};

// validade ISO 'YYYY-MM-DD' → dd/mm/aaaa (sem fuso: trata como data pura)
function dataBrPura(iso) {
  if (!iso) return null;
  const m = String(iso).slice(0, 10).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : iso;
}

// texto de dias restantes (honesto: nunca inventa quando não há validade)
function textoDias(c) {
  if (c.status === "sem_validade" || c.dias_restantes == null) return "—";
  const d = c.dias_restantes;
  if (d < 0) return `vencida há ${Math.abs(d)} ${Math.abs(d) === 1 ? "dia" : "dias"}`;
  if (d === 0) return "vence hoje";
  return `${d} ${d === 1 ? "dia" : "dias"} restantes`;
}

function Badge({ status }) {
  const meta = STATUS_META[status] || STATUS_META.sem_validade;
  return (
    <span className="cert-badge" style={{ "--cor-badge": meta.cor }}>
      <span className="cert-badge-led" aria-hidden="true"></span>
      {meta.rotulo}
    </span>
  );
}

export default function CertidoesScreen({ certidoes, erro, recarregar, criar,
                                          atualizar, remover }) {
  const { reduzido, estatico } = React.useContext(MotionCtx);
  const [form, setForm] = React.useState(FORM_VAZIO);
  const [salvando, setSalvando] = React.useState(false);
  const [editId, setEditId] = React.useState(null);
  const [editForm, setEditForm] = React.useState(FORM_VAZIO);

  const carregando = certidoes == null && !erro;
  const itens = certidoes || [];
  const campo = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const campoEdit = (k) => (e) => setEditForm((f) => ({ ...f, [k]: e.target.value }));

  const aoCriar = (e) => {
    e.preventDefault();
    if (!form.nome.trim() || salvando) return;
    setSalvando(true);
    criar({
      nome: form.nome.trim(),
      orgao_emissor: form.orgao_emissor.trim() || null,
      validade: form.validade || null,
      observacao: form.observacao.trim() || null,
    })
      .then(() => setForm(FORM_VAZIO))
      .catch(() => {})
      .finally(() => setSalvando(false));
  };

  const iniciarEdicao = (c) => {
    setEditId(c.id);
    setEditForm({
      nome: c.nome || "",
      orgao_emissor: c.orgao_emissor || "",
      validade: c.validade ? String(c.validade).slice(0, 10) : "",
      observacao: c.observacao || "",
    });
  };

  const salvarEdicao = (e) => {
    e.preventDefault();
    if (!editForm.nome.trim()) return;
    atualizar(editId, {
      nome: editForm.nome.trim(),
      orgao_emissor: editForm.orgao_emissor.trim() || null,
      validade: editForm.validade || "",
      observacao: editForm.observacao.trim() || null,
    })
      .then(() => setEditId(null))
      .catch(() => {});
  };

  const confirmarRemover = (c) => {
    if (window.confirm(`Remover a certidão "${c.nome}"?`)) remover(c);
  };

  const vencidas = itens.filter((c) => c.status === "vencida").length;
  const breve = itens.filter((c) => c.status === "vence_em_breve").length;

  return (
    <motion.div className="screen-inner"
      initial={estatico ? false : reduzido ? { opacity: 0 } : { opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reduzido ? { duration: 0.15 } : { type: "spring", stiffness: 300, damping: 30 }}>
      <div className="silk">Documentos de habilitação</div>
      <h1 className="pg-titulo">Minhas certidões</h1>
      <p className="pg-sub">
        Guarde suas certidões e documentos (CND federal, FGTS, trabalhista…) com a
        data de validade. O sistema avisa quando estão vencidas ou perto de vencer
        — para você não perder pregão por documento expirado. As datas e o status
        são apenas controle interno; confira sempre o documento oficial.
      </p>

      {carregando ? (
        <EstadoCarregando />
      ) : erro ? (
        <EstadoErro mensagem={erro} recarregar={recarregar} />
      ) : (
        <React.Fragment>
          {(vencidas > 0 || breve > 0) && (
            <div className="cert-aviso" role="status">
              {Ico.alerta}
              {vencidas > 0 && (
                <strong style={{ color: "var(--clip)" }}>
                  {vencidas} {vencidas === 1 ? "vencida" : "vencidas"}
                </strong>
              )}
              {vencidas > 0 && breve > 0 && <span> · </span>}
              {breve > 0 && (
                <strong style={{ color: "var(--pico)" }}>
                  {breve} {breve === 1 ? "vencendo" : "vencendo"}
                </strong>
              )}
              <span> — renove antes de disputar.</span>
            </div>
          )}

          <div className="mod tbl" style={{ overflow: "hidden" }}>
            <div className="cert-head">
              <div className="silk">Documento</div>
              <div className="silk">Órgão emissor</div>
              <div className="silk">Validade</div>
              <div className="silk">Situação</div>
              <div className="silk" style={{ textAlign: "right" }}>Ações</div>
            </div>

            {itens.map((c) => (
              editId === c.id ? (
                <form className="cert-edit" key={c.id} onSubmit={salvarEdicao}>
                  <input className="form-input" value={editForm.nome} required
                    onChange={campoEdit("nome")} aria-label="Nome do documento"
                    placeholder="Nome do documento" />
                  <input className="form-input" value={editForm.orgao_emissor}
                    onChange={campoEdit("orgao_emissor")} aria-label="Órgão emissor"
                    placeholder="Órgão emissor" />
                  <input className="form-input" type="date" value={editForm.validade}
                    onChange={campoEdit("validade")} aria-label="Validade" />
                  <input className="form-input" value={editForm.observacao}
                    onChange={campoEdit("observacao")} aria-label="Observação"
                    placeholder="Observação" />
                  <div className="cert-acoes">
                    <button type="submit" className="cert-btn cert-btn-ok">{Ico.check} Salvar</button>
                    <button type="button" className="cert-btn" onClick={() => setEditId(null)}>Cancelar</button>
                  </div>
                </form>
              ) : (
                <div className="cert-row" key={c.id}>
                  <div className="cert-nome">
                    {c.nome}
                    {c.observacao && <em className="cert-obs"> · {c.observacao}</em>}
                  </div>
                  <div className="cert-orgao">{c.orgao_emissor || <span className="silk">—</span>}</div>
                  <div className="mono cert-validade">
                    {c.validade
                      ? <React.Fragment>{dataBrPura(c.validade)}<br /><small className="silk">{textoDias(c)}</small></React.Fragment>
                      : <span className="silk">sem validade</span>}
                  </div>
                  <div><Badge status={c.status} /></div>
                  <div className="cert-acoes">
                    <button type="button" className="cert-btn" onClick={() => iniciarEdicao(c)}>Editar</button>
                    <button type="button" className="cert-btn cert-btn-rm" onClick={() => confirmarRemover(c)}>Remover</button>
                  </div>
                </div>
              )
            ))}

            {itens.length === 0 && (
              <div className="cert-row cert-vazia">
                <div className="silk" style={{ gridColumn: "1 / -1" }}>
                  Nenhuma certidão cadastrada — adicione a primeira abaixo.
                </div>
              </div>
            )}
          </div>

          <div className="mod form-mod" style={{ marginTop: "14px" }}>
            <div className="silk">Adicionar certidão</div>
            <form className="form-linhas" onSubmit={aoCriar}>
              <input className="form-input longa" value={form.nome} required onChange={campo("nome")}
                placeholder="Documento — ex.: Certidão Negativa de Débitos Federais" aria-label="Nome do documento" />
              <input className="form-input" value={form.orgao_emissor} onChange={campo("orgao_emissor")}
                placeholder="Órgão emissor — ex.: Receita Federal" aria-label="Órgão emissor" />
              <input className="form-input curta" type="date" value={form.validade} onChange={campo("validade")}
                aria-label="Validade" title="Validade (deixe em branco se não tiver)" />
              <input className="form-input" value={form.observacao} onChange={campo("observacao")}
                placeholder="Observação (opcional)" aria-label="Observação" />
              <button type="submit" className="btn-rodar" disabled={salvando}>
                {salvando
                  ? <React.Fragment><span className="spin" aria-hidden="true"></span> Salvando…</React.Fragment>
                  : <React.Fragment>{Ico.check} Adicionar</React.Fragment>}
              </button>
            </form>
          </div>
        </React.Fragment>
      )}
    </motion.div>
  );
}
