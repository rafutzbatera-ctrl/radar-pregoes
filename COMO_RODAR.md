# Como rodar o Radar de Pregões

Sistema real: backend FastAPI + SQLite, frontend React/Vite, dados do PNCP.

## 1. Pré-requisitos
- Python 3.11+ e Node 18+
- Uma chave da Anthropic API (para o extrator de habilitação — M3)

## 2. Configuração (uma vez)
```powershell
# na raiz do projeto
Copy-Item .env.example .env
# edite .env e cole sua ANTHROPIC_API_KEY (sem ela tudo funciona,
# exceto a extração do checklist de habilitação dos editais)

# backend
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

# frontend
cd ..\frontend
npm install

# (opcional) catálogo inicial com os 14 produtos AV do handoff
# REVISE OS CUSTOS — margem é calculada a partir deles
cd ..
backend\.venv\Scripts\python scripts\seed_catalogo.py
```

## 3. Rodar
Dois terminais:

```powershell
# terminal 1 — API (porta 8000) + monitoramento 2x/dia (06:00/18:00)
cd backend
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000

# terminal 2 — UI (porta 5173, proxy /api -> 8000)
cd frontend
npm run dev
```

Abra http://localhost:5173.

## 4. Fluxo de uso
1. **Buscas salvas** → criar busca (ex.: termos `áudio, microfone, caixa de som`, UF `SP`) → "Rodar agora" (ou aguardar o agendador 2×/dia).
2. **Encontrar pregões** → abrir um pregão → sincronizar (baixa itens, edital
   em PDF e extrai habilitação — pode levar minutos em editais grandes).
3. **Itens & margem** → confirmar/recusar/trocar os matches sugeridos pelo
   matching e5 (só item confirmado entra na conta) → veredito aparece.
4. **Habilitação** → checklist com citação do edital (selo "verificada"
   = o trecho existe literalmente no PDF) → marcar tenho/pendente/não tenho.
5. **Fiscal · NF-e** → NCM/CFOP/CST-CSOSN como sugestão — confirme com contador.

## 5. Testes
```powershell
cd backend
.\.venv\Scripts\python -m pytest tests -q   # 45 testes
```

## Notas
- Primeiro matching baixa o modelo `intfloat/multilingual-e5-small` (~450 MB).
- A API de busca do PNCP derruba as primeiras conexões às vezes; o cliente
  tem retry com backoff (até 5 tentativas) — re-rode a busca se falhar.
- Banco: `data/radar.db` · PDFs: `data/arquivos/` · cache HTTP: `data/cache/`.
