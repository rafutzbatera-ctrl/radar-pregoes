"""Cliente da API pública do PNCP (CLAUDE.md §4).

Gentileza com API pública (princípio 6, atualizado 12/06/2026): a fila tem
DUAS PISTAS independentes (lock + último_ts próprios), para que a paginação do
usuário não fique presa atrás de lotes de avaliação:

- pista "interativa" (intervalo 0,3s): 1 chamada por ação do usuário —
  `buscar`, `consulta_propostas`, `detalhe_compra`, `arquivos` (metadados).
- pista "pesada" (intervalo 1,0s, como sempre): loops de avaliação/sincronização
  — `itens` e `baixar_arquivo`.

Pico teórico somando as duas pistas ~4,3 req/s (3,3 interativa + 1,0 pesada) —
ainda gentil com a API pública (decisão do dono: paginação não espera atrás de
lotes). Backoff exponencial em erro, cache local de respostas JSON, User-Agent
identificável seguem intactos.
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
BASE_CONSULTA = "https://pncp.gov.br/api/consulta/v1"

# intervalos por pista (segundos entre requisições da MESMA pista)
_INTERVALO_PESADA = 1.0       # itens/downloads (loops) — como sempre
_INTERVALO_INTERATIVA = 0.3   # buscar/consulta/detalhe/arquivos (ação avulsa)
_MIN_INTERVALO = _INTERVALO_PESADA  # compat: pista pesada é o default
# a busca do PNCP costuma derrubar as primeiras conexões (WAF); o backoff resolve
_TENTATIVAS = 5
_CACHE_TTL = 6 * 3600  # 6 h


def _validar_identidade(cnpj, ano, seq) -> tuple[str, int, int]:
    """Sanitiza a identidade do pregão antes de virar URL ou caminho de arquivo.

    cnpj/ano/seq vêm de hits do PNCP (e, no /descobrir/importar, do corpo do
    usuário). Sem validação, um cnpj com `../`, `/` ou `@host` desvia o request
    (SSRF) ou escapa de ARQUIVOS_DIR (path traversal). Regra mínima:
    - cnpj: SÓ dígitos (qualquer não-dígito → rejeita; bloqueia traversal/host);
    - ano/seq: inteiros (int() conversível).
    Inválido → ValueError (não monta URL nem path). NÃO força 14 dígitos aqui
    para preservar os cnpj curtos dos testes do cliente; a forma canônica
    (^\\d{14}$) é exigida no ponto de ENTRADA (persistir_hit)."""
    s = "" if cnpj is None else str(cnpj)
    if not s.isdigit():
        raise ValueError(f"cnpj inválido (só dígitos): {cnpj!r}")
    try:
        ano_i = int(ano)
        seq_i = int(seq)
    except (TypeError, ValueError):
        raise ValueError(f"ano/seq inválidos: {ano!r}/{seq!r}")
    return s, ano_i, seq_i


def link_pncp(cnpj: str, ano: int, seq: int) -> str:
    cnpj, ano, seq = _validar_identidade(cnpj, ano, seq)
    return f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}"


class ClientePNCP:
    def __init__(self, cache_dir: Path | None = None, cache_ttl: int = _CACHE_TTL):
        self.cache_dir = Path(cache_dir) if cache_dir else settings.CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_ttl = cache_ttl
        # duas pistas independentes: cada uma tem o próprio lock + último_ts, de
        # modo que a pista interativa nunca espera atrás de um lote da pesada.
        self._pistas = {
            "pesada": {"lock": threading.Lock(), "ultima": 0.0,
                       "intervalo": _INTERVALO_PESADA},
            "interativa": {"lock": threading.Lock(), "ultima": 0.0,
                           "intervalo": _INTERVALO_INTERATIVA},
        }
        self._http = httpx.Client(
            headers={"User-Agent": settings.USER_AGENT},
            timeout=60,
            follow_redirects=True,
        )

    # ---------- infra ----------

    def _esperar_vez(self, pista: str = "pesada") -> None:
        """Respeita o intervalo da PISTA indicada, mesmo com chamadas concorrentes.

        Cada pista tem lock + último_ts próprios → a pista interativa (0,3s) não
        espera atrás de um lote da pesada (1,0s) e vice-versa.
        """
        p = self._pistas[pista]
        with p["lock"]:
            agora = time.monotonic()
            falta = p["intervalo"] - (agora - p["ultima"])
            if falta > 0:
                time.sleep(falta)
            p["ultima"] = time.monotonic()

    def _chave_cache(self, url: str, params: dict) -> Path:
        bruto = url + "?" + json.dumps(params, sort_keys=True, ensure_ascii=False)
        return self.cache_dir / (hashlib.sha256(bruto.encode()).hexdigest() + ".json")

    def _get_json(self, url: str, params: dict, usar_cache: bool = True,
                  pista: str = "pesada"):
        arq = self._chave_cache(url, params)
        if usar_cache and arq.exists() and time.time() - arq.stat().st_mtime < self.cache_ttl:
            return json.loads(arq.read_text(encoding="utf-8"))

        ultima_exc: Exception | None = None
        for tentativa in range(_TENTATIVAS):
            self._esperar_vez(pista)
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
        # Resiliência (12/06/2026): o PNCP cai/intermite com alguma frequência
        # ("Erro na comunicação com o banco de dados"). Cache VENCIDO ainda é o
        # dado oficial — só mais velho; servir é melhor que tela vazia. Só após
        # esgotar TODAS as tentativas, e nunca quando usar_cache=False.
        if usar_cache and arq.exists():
            log.warning("PNCP %s segue fora; servindo cache vencido", url)
            return json.loads(arq.read_text(encoding="utf-8"))
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
        # pista interativa: 1 chamada por ação do usuário (paginação/digitação)
        return self._get_json(BASE_SEARCH, params, usar_cache, pista="interativa")

    def consulta_propostas(self, data_final: str, modalidade: str = "",
                           uf: str = "", pagina: int = 1, tamanho: int = 50,
                           usar_cache: bool = True) -> dict:
        """4.4 — API de Consulta (bulk): contratações com proposta em aberto.

        `GET /consulta/v1/contratacoes/proposta?dataFinal=AAAAMMDD&pagina&tamanhoPagina`.
        TODO registro traz `valorTotalEstimado` preenchido (≠ da busca textual,
        onde valor_global vem null) — é a fonte EM MASSA dos valores oficiais.

        Params verificados (12/06/2026): `codigoModalidadeContratacao` (id único
        1-13, CLAUDE.md §4.1) e `uf` (sigla única). Só entram quando truthy;
        `dataFinal` é sempre obrigatório. Resposta:
        `{"data": [...], "totalRegistros": N, "totalPaginas": N, ...}`.
        """
        params = {
            "dataFinal": data_final,
            "pagina": pagina,
            "tamanhoPagina": tamanho,
        }
        if modalidade:
            params["codigoModalidadeContratacao"] = modalidade
        if uf:
            params["uf"] = uf
        # pista interativa: paginação em massa também é ação do usuário
        return self._get_json(
            f"{BASE_CONSULTA}/contratacoes/proposta", params, usar_cache,
            pista="interativa",
        )

    def detalhe_compra(self, cnpj: str, ano: int, seq: int,
                       usar_cache: bool = True) -> dict:
        """4.4 — detalhe de uma compra pela API de Consulta.

        `GET /consulta/v1/orgaos/{cnpj}/compras/{ano}/{seq}` responde
        publicamente com `valorTotalEstimado`/`valorTotalHomologado` (o caminho
        antigo `api/pncp/v1/...` dá 301). Disponível e testado; ainda não usado
        pela UI (o bulk já embute o valor em cada registro).
        """
        cnpj, ano, seq = _validar_identidade(cnpj, ano, seq)
        url = f"{BASE_CONSULTA}/orgaos/{cnpj}/compras/{ano}/{seq}"
        # pista interativa: detalhe avulso (1 compra por ação)
        return self._get_json(url, {}, usar_cache, pista="interativa")

    def itens(self, cnpj: str, ano: int, seq: int, usar_cache: bool = True) -> list:
        """4.2 — itens do pregão (pagina até esgotar).

        Pista PESADA (1,0s): roda em loops de avaliação/sincronização — fica na
        fila lenta para não atrapalhar a paginação interativa do usuário.
        """
        cnpj, ano, seq = _validar_identidade(cnpj, ano, seq)
        todos: list = []
        pagina = 1
        while True:
            url = f"{BASE_API}/orgaos/{cnpj}/compras/{ano}/{seq}/itens"
            lote = self._get_json(
                url, {"pagina": pagina, "tamanhoPagina": 100}, usar_cache,
                pista="pesada",
            )
            if not lote:
                break
            todos.extend(lote)
            if len(lote) < 100:
                break
            pagina += 1
        return todos

    def arquivos(self, cnpj: str, ano: int, seq: int, usar_cache: bool = True) -> list:
        """4.3 — arquivos do pregão (edital, TR, anexos).

        Pista INTERATIVA (0,3s): só metadados (lista de URLs), 1 chamada por
        ação — o download do binário é que vai na pista pesada.
        """
        cnpj, ano, seq = _validar_identidade(cnpj, ano, seq)
        url = f"{BASE_API}/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos"
        return self._get_json(
            url, {"pagina": 1, "tamanhoPagina": 20}, usar_cache, pista="interativa"
        ) or []

    def historico(self, cnpj: str, ano: int, seq: int,
                  usar_cache: bool = True) -> list:
        """Histórico de manutenção do pregão (eventos do PNCP).

        `GET /pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/historico` → lista crua de
        eventos (`logManutencaoDataInclusao, tipoLogManutencaoNome,
        categoriaLogManutencaoNome, usuarioNome, justificativa, documentoTitulo`).

        Pista INTERATIVA (0,3s): 1 chamada por ação do usuário (abrir a aba).
        O FILTRO de ruído de sincronização NÃO mora aqui (cliente devolve cru) —
        é feito num helper testável (services/historico.py). Retorna a lista crua.
        """
        cnpj, ano, seq = _validar_identidade(cnpj, ano, seq)
        url = f"{BASE_API}/orgaos/{cnpj}/compras/{ano}/{seq}/historico"
        return self._get_json(
            url, {"pagina": 1, "tamanhoPagina": 500}, usar_cache, pista="interativa"
        ) or []

    def baixar_arquivo(self, url: str, destino_dir: Path) -> Path:
        """Baixa o binário de um arquivo, respeitando o nome do content-disposition.

        Pista PESADA (1,0s): o binário pode ter MBs e roda em lote junto da
        sincronização — fica na fila lenta.
        """
        destino_dir.mkdir(parents=True, exist_ok=True)
        ultima_exc: Exception | None = None
        for tentativa in range(_TENTATIVAS):
            self._esperar_vez("pesada")
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
