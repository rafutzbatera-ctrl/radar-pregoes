"""Cliente da API pública do PNCP (CLAUDE.md §4).

Gentileza com API pública (princípio 6): máx. 1 req/s, backoff exponencial
em erro, cache local de respostas JSON, User-Agent identificável.
"""
import hashlib
import json
import logging
import re
import threading
import time
from pathlib import Path

import httpx

from . import settings

log = logging.getLogger("radar.pncp")

BASE_SEARCH = "https://pncp.gov.br/api/search/"
BASE_API = "https://pncp.gov.br/api/pncp/v1"

_MIN_INTERVALO = 1.0  # segundos entre requisições
# a busca do PNCP costuma derrubar as primeiras conexões (WAF); o backoff resolve
_TENTATIVAS = 5
_CACHE_TTL = 6 * 3600  # 6 h


def link_pncp(cnpj: str, ano: int, seq: int) -> str:
    return f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}"


class ClientePNCP:
    def __init__(self, cache_dir: Path | None = None, cache_ttl: int = _CACHE_TTL):
        self.cache_dir = Path(cache_dir) if cache_dir else settings.CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = cache_ttl
        self._lock = threading.Lock()
        self._ultima_req = 0.0
        self._http = httpx.Client(
            headers={"User-Agent": settings.USER_AGENT},
            timeout=60,
            follow_redirects=True,
        )

    # ---------- infra ----------

    def _esperar_vez(self) -> None:
        """Garante no máximo 1 req/s, mesmo com chamadas concorrentes."""
        with self._lock:
            agora = time.monotonic()
            falta = _MIN_INTERVALO - (agora - self._ultima_req)
            if falta > 0:
                time.sleep(falta)
            self._ultima_req = time.monotonic()

    def _chave_cache(self, url: str, params: dict) -> Path:
        bruto = url + "?" + json.dumps(params, sort_keys=True, ensure_ascii=False)
        return self.cache_dir / (hashlib.sha256(bruto.encode()).hexdigest() + ".json")

    def _get_json(self, url: str, params: dict, usar_cache: bool = True):
        arq = self._chave_cache(url, params)
        if usar_cache and arq.exists() and time.time() - arq.stat().st_mtime < self.cache_ttl:
            return json.loads(arq.read_text(encoding="utf-8"))

        ultima_exc: Exception | None = None
        for tentativa in range(_TENTATIVAS):
            self._esperar_vez()
            try:
                resp = self._http.get(url, params=params)
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError(
                        f"HTTP {resp.status_code}", request=resp.request, response=resp
                    )
                if resp.status_code == 204:  # sem conteúdo (lista vazia)
                    dados = []
                else:
                    resp.raise_for_status()
                    dados = resp.json()
                arq.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
                return dados
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                ultima_exc = exc
                espera = 2**tentativa  # 1, 2, 4, 8 s
                log.warning("PNCP %s falhou (%s); retry em %ss", url, exc, espera)
                time.sleep(espera)
        raise RuntimeError(f"PNCP indisponível após {_TENTATIVAS} tentativas: {ultima_exc}")

    # ---------- endpoints (CLAUDE.md §4) ----------

    def buscar(self, q: str = "", ufs: str = "", status: str = "recebendo_proposta",
               pagina: int = 1, tamanho: int = 50, usar_cache: bool = True,
               tipos_documento: str = "edital", ordenacao: str = "-data",
               modalidades: str = "", esferas: str = "") -> dict:
        """4.1 — busca textual de editais. Retorna {"items": [...], "total": N}.

        `q` é opcional: a API do PNCP aceita busca sem termo (é assim que se vê o
        total nacional de ~37k). Quando vazio, o param `q` NÃO é enviado.

        Params adicionais verificados empiricamente (CLAUDE.md §4.1):
        - `tipos_documento`: edital | ata | contrato.
        - `ordenacao`: -data (recentes) | data (antigos) | relevancia.
        - `modalidades`: csv de ids 1-13 (6 Pregão-Eletrônico, 8 Dispensa, …).
        - `esferas`: csv de letras (F Federal, E Estadual, M Municipal, D Distrital).
        Só entram nos params quando truthy.

        ATENÇÃO `status`: na busca do PNCP, OMITIR o param dá HTTP 400. Por isso,
        quando o chamador passar vazio/None, enviamos `status=todos` (que a API
        trata como "sem filtro de situação"). Só `recebendo_proposta` e
        `encerradas` filtram de fato.
        """
        params = {
            "tipos_documento": tipos_documento or "edital",
            "ordenacao": ordenacao or "-data",
            "pagina": pagina,
            "tamanhoPagina": tamanho,
            # nunca omitir status (omitir → 400); vazio/None vira "todos"
            "status": status or "todos",
        }
        if q:
            params["q"] = q
        if ufs:
            params["ufs"] = ufs
        if modalidades:
            params["modalidades"] = modalidades
        if esferas:
            params["esferas"] = esferas
        return self._get_json(BASE_SEARCH, params, usar_cache)

    def itens(self, cnpj: str, ano: int, seq: int, usar_cache: bool = True) -> list:
        """4.2 — itens do pregão (pagina até esgotar)."""
        todos: list = []
        pagina = 1
        while True:
            url = f"{BASE_API}/orgaos/{cnpj}/compras/{ano}/{seq}/itens"
            lote = self._get_json(
                url, {"pagina": pagina, "tamanhoPagina": 100}, usar_cache
            )
            if not lote:
                break
            todos.extend(lote)
            if len(lote) < 100:
                break
            pagina += 1
        return todos

    def arquivos(self, cnpj: str, ano: int, seq: int, usar_cache: bool = True) -> list:
        """4.3 — arquivos do pregão (edital, TR, anexos)."""
        url = f"{BASE_API}/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos"
        return self._get_json(url, {"pagina": 1, "tamanhoPagina": 20}, usar_cache) or []

    def baixar_arquivo(self, url: str, destino_dir: Path) -> Path:
        """Baixa o binário de um arquivo, respeitando o nome do content-disposition."""
        destino_dir.mkdir(parents=True, exist_ok=True)
        ultima_exc: Exception | None = None
        for tentativa in range(_TENTATIVAS):
            self._esperar_vez()
            try:
                resp = self._http.get(url)
                resp.raise_for_status()
                nome = _nome_do_content_disposition(
                    resp.headers.get("content-disposition", "")
                ) or "arquivo.pdf"
                destino = destino_dir / nome
                destino.write_bytes(resp.content)
                return destino
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                ultima_exc = exc
                time.sleep(2**tentativa)
        raise RuntimeError(f"Falha ao baixar {url}: {ultima_exc}")

    def fechar(self) -> None:
        self._http.close()


def _nome_do_content_disposition(header: str) -> str | None:
    """Extrai filename de um header content-disposition (com ou sem aspas)."""
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", header)
    if not m:
        return None
    nome = m.group(1).strip()
    # remove separadores de caminho por segurança
    return re.sub(r"[\\/:*?\"<>|]", "_", nome) or None


# instância compartilhada do app (testes criam as suas com cache_dir próprio)
_cliente: ClientePNCP | None = None


def cliente() -> ClientePNCP:
    global _cliente
    if _cliente is None:
        _cliente = ClientePNCP()
    return _cliente
