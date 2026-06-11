# Pipeline de Disputa + Resumo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Funil de disputa (6 status fixos) sobre os pregões salvos, com data da disputa, valor final e faixa-resumo de resultados em "Meus pregões".

**Architecture:** Colunas novas na tabela `pregoes` (migração v2); `PATCH /pregoes/{id}` estendido com gatilho salvar→cotacao; novo `GET /pipeline/resumo`; UI evolui "Meus pregões" com faixa-resumo + alternância Lista/Quadro (select de status no cartão, sem drag & drop).

**Tech Stack:** FastAPI + SQLite (backend/.venv), React/Vite/Framer Motion (frontend), pytest.

Spec: `docs/superpowers/specs/2026-06-11-pipeline-disputa-design.md`. Suíte hoje: **84 verdes** (`cd backend; .\.venv\Scripts\python.exe -m pytest tests -q`).

---

### Task 1: Migração v2 (colunas do pipeline)

**Files:**
- Modify: `backend/app/db.py` (lista `MIGRACOES`)
- Test: `backend/tests/test_pipeline.py` (criar)

- [ ] **Step 1: Teste que falha**

```python
"""P2 — pipeline de disputa: migração, PATCH, resumo."""
import sqlite3

from app import db


def test_migracao_v2_preserva_dados_v1(tmp_path):
    caminho = tmp_path / "radar.db"
    con = sqlite3.connect(caminho)
    con.executescript(db.MIGRACOES[0])          # banco v1 com dados
    con.execute("PRAGMA user_version = 1")
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,1,'NC-1')")
    con.commit(); con.close()

    c2 = db.abrir(caminho)                      # migra para v2
    cols = {r[1] for r in c2.execute("PRAGMA table_info(pregoes)")}
    assert {"status_pipeline", "data_disputa", "valor_final"} <= cols
    assert c2.execute("SELECT COUNT(*) c FROM pregoes").fetchone()["c"] == 1
    assert c2.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRACOES)
    c2.close()
```

- [ ] **Step 2: Rodar e ver falhar** — `.\.venv\Scripts\python.exe -m pytest tests/test_pipeline.py -v` → FAIL (colunas ausentes).

- [ ] **Step 3: Implementação mínima** — em `db.py`, append na lista `MIGRACOES` (depois do script v1):

```python
    # v2 — pipeline de disputa (P2): status do funil, data da disputa e
    # valor final proposto/arrematado. NULL em status_pipeline = fora do funil.
    """
    ALTER TABLE pregoes ADD COLUMN status_pipeline TEXT;
    ALTER TABLE pregoes ADD COLUMN data_disputa TEXT;
    ALTER TABLE pregoes ADD COLUMN valor_final REAL;
    """,
```

- [ ] **Step 4: Rodar e ver passar** + suíte completa (`pytest tests -q`, 84+1).
- [ ] **Step 5: Commit** — `git add backend; git commit -m "P2: migracao v2 com colunas do pipeline"`

---

### Task 2: PATCH /pregoes/{id} com campos do pipeline + gatilho salvar→cotacao

**Files:**
- Modify: `backend/app/routers/pregoes.py` (classe `PregaoPatch` e função `atualizar`)
- Test: `backend/tests/test_pipeline.py` (append)

- [ ] **Step 1: Testes que falham** (append em test_pipeline.py; fixtures `client`/`con` do conftest):

```python
def _novo_pregao(con, nc="NC-1"):
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,1,?)", (nc,))
    con.commit()
    return con.execute("SELECT id FROM pregoes WHERE numero_controle=?",
                       (nc,)).fetchone()["id"]


def test_patch_campos_pipeline(client, con):
    pid = _novo_pregao(con)
    r = client.patch(f"/pregoes/{pid}", json={
        "status_pipeline": "disputando",
        "data_disputa": "2026-06-20 09:00",
        "valor_final": 12500.5,
    })
    assert r.status_code == 200
    assert r.json()["status_pipeline"] == "disputando"
    assert r.json()["data_disputa"] == "2026-06-20 09:00"
    assert r.json()["valor_final"] == 12500.5


def test_patch_status_invalido_422(client, con):
    pid = _novo_pregao(con)
    assert client.patch(f"/pregoes/{pid}",
                        json={"status_pipeline": "ganhei"}).status_code == 422


def test_salvar_seta_cotacao_e_preserva_status_existente(client, con):
    pid = _novo_pregao(con)
    r = client.patch(f"/pregoes/{pid}", json={"salvo": True})
    assert r.json()["status_pipeline"] == "cotacao"   # gatilho de entrada

    client.patch(f"/pregoes/{pid}", json={"status_pipeline": "ganho"})
    client.patch(f"/pregoes/{pid}", json={"salvo": False})   # dessalvar preserva
    r = client.patch(f"/pregoes/{pid}", json={"salvo": True})  # re-salvar idem
    assert r.json()["status_pipeline"] == "ganho"
```

- [ ] **Step 2: Rodar e ver falhar** (campos desconhecidos são ignorados pelo Pydantic → status_pipeline não persiste).

- [ ] **Step 3: Implementação** — em `routers/pregoes.py` substituir `PregaoPatch` e `atualizar`:

```python
class PregaoPatch(BaseModel):
    salvo: bool | None = None
    novo: bool | None = None
    # pipeline de disputa (P2); null em status_pipeline = sai do funil
    status_pipeline: Literal["cotacao", "habilitacao", "disputando",
                             "ganho", "perdido", "suspenso"] | None = None
    data_disputa: str | None = None
    valor_final: float | None = None
```

(adicionar `from typing import Literal` aos imports)

```python
@router.patch("/{pregao_id}")
def atualizar(pregao_id: int, corpo: PregaoPatch,
              con: sqlite3.Connection = Depends(get_db)):
    # exclude_unset: distingue "não enviado" de "enviado como null" —
    # null limpa o campo (ex.: tirar do funil), ausente não toca
    campos = corpo.model_dump(exclude_unset=True)
    if not campos:
        raise HTTPException(400, "Nada para atualizar")
    sets = ", ".join(f"{c}=?" for c in campos)
    valores = [int(v) if isinstance(v, bool) else v for v in campos.values()]
    cur = con.execute(
        f"UPDATE pregoes SET {sets} WHERE id=?", (*valores, pregao_id)
    )
    if not cur.rowcount:
        raise HTTPException(404, "Pregão não encontrado")
    # entrada no funil: salvar pregão ainda sem status → cotacao
    if campos.get("salvo") is True:
        con.execute(
            "UPDATE pregoes SET status_pipeline='cotacao' "
            "WHERE id=? AND status_pipeline IS NULL", (pregao_id,)
        )
    con.commit()
    return detalhe(pregao_id, con)
```

- [ ] **Step 4: Rodar testes novos + suíte completa** (os testes antigos de PATCH salvo/novo continuam passando com exclude_unset).
- [ ] **Step 5: Commit** — `git commit -m "P2: PATCH pipeline + gatilho salvar->cotacao"`

---

### Task 3: GET /pipeline/resumo

**Files:**
- Create: `backend/app/routers/pipeline.py`
- Modify: `backend/app/main.py` (registrar router)
- Test: `backend/tests/test_pipeline.py` (append)

- [ ] **Step 1: Testes que falham**:

```python
def test_resumo_vazio(client):
    r = client.get("/pipeline/resumo")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["total_funil"] == 0
    assert corpo["taxa_ganho"] is None
    assert corpo["valor_ganho"] is None


def test_resumo_com_funil(client, con):
    dados = [  # (nc, status, valor_final)
        ("NC-1", "cotacao", None), ("NC-2", "disputando", None),
        ("NC-3", "ganho", 10000.0), ("NC-4", "ganho", None),
        ("NC-5", "perdido", None),
    ]
    for i, (nc, st, vf) in enumerate(dados, 1):
        con.execute(
            "INSERT INTO pregoes (cnpj, ano, seq, numero_controle, salvo, "
            "status_pipeline, valor_final) VALUES ('1',2026,?,?,1,?,?)",
            (i, nc, st, vf))
    # salvo=0 fica FORA do funil mesmo com status
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, salvo, "
                "status_pipeline) VALUES ('1',2026,99,'NC-99',0,'ganho')")
    con.commit()

    corpo = client.get("/pipeline/resumo").json()
    assert corpo["total_funil"] == 5
    assert corpo["por_status"]["ganho"] == 2
    assert corpo["ganhos"] == 2 and corpo["perdidos"] == 1
    assert corpo["taxa_ganho"] == 2 / 3
    assert corpo["valor_ganho"] == 10000.0   # só valores PREENCHIDOS
    assert corpo["ganhos_sem_valor"] == 1    # honestidade: 1 ganho sem valor
```

- [ ] **Step 2: Rodar e ver falhar** (404).

- [ ] **Step 3: Implementação** — criar `backend/app/routers/pipeline.py`:

```python
import sqlite3

from fastapi import APIRouter, Depends

from ..deps import get_db

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

STATUS_FUNIL = ("cotacao", "habilitacao", "disputando",
                "ganho", "perdido", "suspenso")


@router.get("/resumo")
def resumo(con: sqlite3.Connection = Depends(get_db)):
    """Resultados do funil (pregões salvos). Princípio 1: valor_ganho só soma
    valor_final PREENCHIDO de pregões ganhos — sem dado, é null, nunca chute."""
    linhas = con.execute(
        "SELECT status_pipeline s, valor_final v FROM pregoes WHERE salvo=1"
    ).fetchall()
    por_status = {s: 0 for s in STATUS_FUNIL}
    valor_ganho = 0.0
    tem_valor = False
    ganhos_sem_valor = 0
    for ln in linhas:
        if ln["s"] in por_status:
            por_status[ln["s"]] += 1
            if ln["s"] == "ganho":
                if ln["v"] is not None:
                    valor_ganho += ln["v"]
                    tem_valor = True
                else:
                    ganhos_sem_valor += 1
    ganhos, perdidos = por_status["ganho"], por_status["perdido"]
    encerrados = ganhos + perdidos
    return {
        "por_status": por_status,
        "total_funil": sum(por_status.values()),
        "ganhos": ganhos,
        "perdidos": perdidos,
        "taxa_ganho": (ganhos / encerrados) if encerrados else None,
        "valor_ganho": valor_ganho if tem_valor else None,
        "ganhos_sem_valor": ganhos_sem_valor,
    }
```

Em `main.py`: importar `pipeline` no `from .routers import ...` e `app.include_router(pipeline.router)`.

- [ ] **Step 4: Rodar testes + suíte completa.**
- [ ] **Step 5: Commit** — `git commit -m "P2: GET /pipeline/resumo"`

---

### Task 4: Frontend — api + faixa-resumo + Lista/Quadro + módulo Disputa

**Files:**
- Modify: `frontend/src/api.js` (adaptarPregao + 2 chamadas)
- Create: `frontend/src/Kanban.jsx`
- Modify: `frontend/src/FindScreen.jsx` (tela Meus pregões: resumo + alternância)
- Modify: `frontend/src/AnalysisScreen.jsx` (módulo Disputa + Salvar no funil)
- Modify: `frontend/src/App.jsx` (handlers `mudarPipeline`, `salvarPregao`)
- Modify: `frontend/src/styles.css` (fim, seção port real)

(Frontend sem runner de testes — verificação por `npm run build` + smoke no preview.)

- [ ] **Step 1: api.js** — em `adaptarPregao`, acrescentar ao objeto retornado:

```js
    statusPipeline: p.status_pipeline || null,
    dataDisputa: p.data_disputa || null,
    valorFinal: p.valor_final,
```

E em `api`:

```js
  pipelineResumo: () => req("/pipeline/resumo"),
  // PATCH genérico já existe: atualizarPregao(id, {status_pipeline, data_disputa, valor_final, salvo})
```

- [ ] **Step 2: Kanban.jsx** (novo) — quadro com 6 colunas fixas, select de status, inputs de data/valor:

```jsx
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
```

- [ ] **Step 3: FindScreen.jsx (Meus pregões)** — quando `apenasSalvos`: carregar `api.pipelineResumo()` (estado local, recarregar após cada `mudarPipeline`); renderizar faixa-resumo acima da lista (classe `.resumo` existente):

```jsx
{resumo && (
  <div className="resumo pipeline-resumo">
    {STATUS_PIPELINE.map((s) => (
      <Resumo key={s.id} k={s.rotulo} v={String(resumo.por_status[s.id] || 0)} />
    ))}
    <Resumo k="Taxa de ganho"
            v={resumo.taxa_ganho != null ? Math.round(resumo.taxa_ganho * 100) + "%" : "—"}
            sub={resumo.ganhos + " ganhos · " + resumo.perdidos + " perdidos"} />
    <Resumo k="Valor ganho"
            v={resumo.valor_ganho != null ? fmtBRL(resumo.valor_ganho) : "—"}
            sub={resumo.ganhos_sem_valor > 0 ? resumo.ganhos_sem_valor + " ganho(s) sem valor informado" : undefined} />
  </div>
)}
```

(`Resumo` hoje vive em AnalysisScreen — mover para `helpers.jsx` e exportar, ajustando os imports.)
Segmentado Lista | Quadro (mesmo padrão visual do seletor do PNCP ao vivo); no modo Quadro renderizar `<Kanban pregoes={pregoesSalvos} aoAbrir={aoAbrir} mudarPipeline={mudarPipeline} />`.

- [ ] **Step 4: App.jsx** — handlers (padrão otimista existente):

```jsx
const mudarPipeline = (id, campos) => {
  const anterior = (pregoes || []).find((p) => p.id === id);
  setPregoes((ps) => (ps || []).map((p) => (p.id === id ? {
    ...p,
    statusPipeline: campos.status_pipeline !== undefined ? campos.status_pipeline : p.statusPipeline,
    dataDisputa: campos.data_disputa !== undefined ? campos.data_disputa : p.dataDisputa,
    valorFinal: campos.valor_final !== undefined ? campos.valor_final : p.valorFinal,
  } : p)));
  api.atualizarPregao(id, campos).then((atualizado) => {
    setPregoes((ps) => (ps || []).map((p) => (p.id === id ? atualizado : p)));
  }).catch(() => {
    setPregoes((ps) => (ps || []).map((p) => (p.id === id ? anterior : p)));
    avisar("Não foi possível atualizar o funil — revertido.");
  });
};

const salvarPregao = (id, salvo) => mudarPipeline(id, { salvo });
```

Passar `mudarPipeline` ao FindScreen (Meus pregões) e `salvarPregao` ao AnalysisScreen.

- [ ] **Step 5: AnalysisScreen.jsx** — módulo "Disputa" após a faixa `.resumo` (mesmos inputs do CartaoFunil: select status + datetime + valor final; usar `pregao.salvo ? ... : botão "Salvar no funil"` que chama `salvarPregao(pregao.id, true)`).

- [ ] **Step 6: styles.css** — append na seção port real:

```css
/* ==== P2: funil de disputa ==== */
.kanban { display: grid; grid-template-columns: repeat(6, minmax(180px, 1fr)); gap: 10px; align-items: start; overflow-x: auto; }
.kanban-col { background: var(--aluminio); border: 1px solid var(--linha); border-radius: 10px; padding: 8px; min-height: 120px; }
.kanban-cab { display: flex; justify-content: space-between; margin: 2px 4px 8px; }
.kanban-n { color: var(--tinta-2); }
.kanban-cards { display: flex; flex-direction: column; gap: 8px; }
.kanban-card { background: var(--painel); border: 1px solid var(--linha); border-radius: 8px; padding: 10px; display: flex; flex-direction: column; gap: 6px; }
.kanban-titulo { font-family: var(--font-display); font-weight: 700; text-transform: uppercase; letter-spacing: 0.02em; font-size: 14px; text-align: left; background: none; border: 0; cursor: pointer; padding: 0; }
.kanban-titulo:hover { text-decoration: underline; }
.kanban-orgao { font-size: 12px; color: var(--tinta-2); }
.kanban-meta { display: flex; gap: 8px; align-items: center; font-size: 12px; }
.kanban-campo { display: flex; flex-direction: column; gap: 3px; }
.kanban-vazio { text-align: center; padding: 10px 0; }
.pipeline-resumo { margin-bottom: 14px; }
@media (max-width: 1100px) { .kanban { grid-template-columns: repeat(3, minmax(180px, 1fr)); } }
```

- [ ] **Step 7: Build** — `cd frontend; npm run build` → verde.
- [ ] **Step 8: Commit** — `git commit -m "P2: funil em Meus pregoes (resumo + quadro) e modulo Disputa na analise"`

---

### Task 5: Validação final
- [ ] Suíte backend completa verde (89+).
- [ ] `npm run build` verde.
- [ ] Smoke no preview: salvar pregão → aparece em cotação; mover para ganho com valor → resumo reflete taxa e valor; recarregar página → persistiu.
