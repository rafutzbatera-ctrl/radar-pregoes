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

# matching (CLAUDE.md §3)
MATCH_MODELO = "intfloat/multilingual-e5-small"
MATCH_THRESHOLD = 0.83

# regras do veredito (CLAUDE.md §6.2) — sobreponíveis via tabela config
VEREDITO_PADRAO = {
    "vale_margem_min": 0.20,
    "vale_cobertura_min": 0.60,
    "vale_lucro_min": 1000.0,
    "nao_vale_margem_max": 0.08,
    "nao_vale_lucro_max": 300.0,
}
