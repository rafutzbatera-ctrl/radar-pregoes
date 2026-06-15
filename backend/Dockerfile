# Backend — FastAPI + e5 local + SQLite. Imagem de PREPARO (preview/portfólio),
# não é um deploy publicado. A imagem fica grande (~2-3 GB) por causa do
# torch/sentence-transformers; é o esperado para o matching/RAG local.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # cache do modelo e5 num dir próprio (volume nomeado evita re-download)
    HF_HOME=/app/hf-cache

WORKDIR /app

# libgomp1: runtime do OpenMP exigido pelo torch (CPU).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# Dirs persistidos por volume nomeado. Criados e chowned ANTES de trocar de
# usuário: como são volumes NOMEADOS e vazios no 1º up, o Docker herda esta
# dona (radar) — escrita não-root funciona sem gambiarra de entrypoint.
RUN mkdir -p /app/data /app/hf-cache \
    && useradd --create-home radar \
    && chown -R radar:radar /app
USER radar

EXPOSE 8000

# /health já existe no app (router de saúde). start-period generoso: o 1º
# request baixa o modelo e5 (~470 MB) e demora.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
