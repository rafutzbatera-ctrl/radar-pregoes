"""Configuração por variáveis de ambiente (.env na raiz do projeto)."""
import os
from pathlib import Path

from dotenv import load_dotenv

# raiz do repositório (…/Radar_pregao)
RAIZ = Path(__file__).resolve().parents[2]
load_dotenv(RAIZ / ".env")

DB_PATH = RAIZ / os.getenv("RADAR_DB", "data/radar.db")
CACHE_DIR = RAIZ / "data" / "cache"
ARQUIVOS_DIR = RAIZ / "data" / "arquivos"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.getenv("RADAR_LLM_MODEL", "claude-sonnet-4-6")
SCHEDULER_ATIVO = os.getenv("RADAR_SCHEDULER", "1") == "1"

# extrator de habilitação (CLAUDE.md §6.3) — plugável.
# "heuristico" (padrão, sem IA, 100% local), "api" (Anthropic), "claude_cli".
EXTRATOR_HABILITACAO = os.getenv("RADAR_EXTRATOR", "heuristico")
CLAUDE_CLI_BIN = os.getenv("RADAR_CLAUDE_CLI", "claude")
CLAUDE_CLI_TIMEOUT = int(os.getenv("RADAR_CLAUDE_CLI_TIMEOUT", "600"))

USER_AGENT = "RadarPregoes/0.1 (uso pessoal)"

# matching (CLAUDE.md §3 — atualizado P3: conservador, 0.90)
MATCH_MODELO = "intfloat/multilingual-e5-small"
MATCH_THRESHOLD = 0.90

# RAG leve extrativo (Fase 1) — Q&A sobre os documentos de UM edital por vez.
# Reusa o mesmo e5 do matching (MATCH_MODELO); threshold SEPARADO do 0.90 do
# matching: aqui 0.80 (decisão do dono). Abaixo do threshold a resposta é
# "não encontrado" — nunca inventa (princípio 1). Chunking em chars sobre o
# texto cru da página (verbatim), com fronteiras de parágrafo/cláusula.
RAG_THRESHOLD = float(os.getenv("RADAR_RAG_THRESHOLD", "0.80"))
RAG_TOP_K = int(os.getenv("RADAR_RAG_TOP_K", "5"))
RAG_CHUNK_MAX = int(os.getenv("RADAR_RAG_CHUNK_MAX", "900"))      # teto de chars/chunk
RAG_CHUNK_MIN = int(os.getenv("RADAR_RAG_CHUNK_MIN", "200"))      # alvo mínimo antes de fechar
RAG_CHUNK_OVERLAP = int(os.getenv("RADAR_RAG_CHUNK_OVERLAP", "120"))  # sobreposição entre chunks

# regras do veredito (CLAUDE.md §6.2) — sobreponíveis via tabela config
VEREDITO_PADRAO = {
    "vale_margem_min": 0.20,
    "vale_cobertura_min": 0.60,
    "vale_lucro_min": 1000.0,
    "nao_vale_margem_max": 0.08,
    "nao_vale_lucro_max": 300.0,
}
