"""SQLite + migrações simples (PRAGMA user_version)."""
import sqlite3
from pathlib import Path

from . import settings

MIGRACOES = [
    # v1 — esquema inicial (CLAUDE.md §5)
    """
    CREATE TABLE buscas_salvas(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        termos TEXT NOT NULL,            -- separados por vírgula
        ufs TEXT DEFAULT '',             -- "SP,RJ" ou vazio = todas
        status TEXT DEFAULT 'recebendo_proposta',
        ativo INTEGER DEFAULT 1,
        ultima_exec TEXT,
        criado_em TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE pregoes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cnpj TEXT NOT NULL,
        ano INTEGER NOT NULL,
        seq INTEGER NOT NULL,
        numero_controle TEXT UNIQUE NOT NULL,
        titulo TEXT,
        descricao TEXT,
        orgao TEXT,
        unidade TEXT,
        municipio TEXT,
        uf TEXT,
        modalidade TEXT,
        situacao TEXT,
        data_inicio_vigencia TEXT,
        data_fim_vigencia TEXT,
        valor_global REAL,
        json_busca TEXT,                 -- hit cru da API de busca (fonte oficial)
        link_pncp TEXT,
        busca_id INTEGER REFERENCES buscas_salvas(id),
        descoberto_em TEXT DEFAULT (datetime('now')),
        novo INTEGER DEFAULT 1,
        salvo INTEGER DEFAULT 0,
        sincronizado_em TEXT,
        -- calculados (sempre acompanhados dos números crus nos endpoints)
        veredito TEXT,
        lucro_potencial REAL,
        margem_media REAL
    );
    CREATE TABLE itens_pregao(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pregao_id INTEGER NOT NULL REFERENCES pregoes(id),
        numero INTEGER NOT NULL,
        descricao TEXT,
        qtd REAL,
        unidade TEXT,
        valor_unit_estimado REAL,
        valor_total REAL,
        beneficio TEXT,
        criterio TEXT,
        ncm_pncp TEXT,
        info_complementar TEXT,
        sigiloso INTEGER DEFAULT 0,
        produto_id INTEGER REFERENCES catalogo_produtos(id),
        match_score REAL,
        match_confirmado INTEGER DEFAULT 0,
        UNIQUE(pregao_id, numero)
    );
    CREATE TABLE catalogo_produtos(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT,
        nome TEXT NOT NULL,
        categoria TEXT,
        custo_unit REAL NOT NULL,
        ncm TEXT,
        unidade TEXT DEFAULT 'UN',
        origem TEXT,
        csosn TEXT,                      -- usado no Simples
        cst TEXT,                        -- usado no Presumido
        aliq_icms REAL,
        aliq_ipi REAL,
        ativo INTEGER DEFAULT 1
    );
    CREATE TABLE arquivos(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pregao_id INTEGER NOT NULL REFERENCES pregoes(id),
        titulo TEXT,
        tipo TEXT,
        url TEXT,
        caminho_local TEXT,
        baixado_em TEXT,
        UNIQUE(pregao_id, url)
    );
    CREATE TABLE habilitacao(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pregao_id INTEGER NOT NULL REFERENCES pregoes(id),
        requisito TEXT NOT NULL,
        categoria TEXT NOT NULL,
        obrigatorio INTEGER DEFAULT 1,
        pagina INTEGER,
        excerto TEXT,
        verificada INTEGER DEFAULT 0,
        status_usuario TEXT DEFAULT 'pendente'   -- ok|pendente|nao_tenho
    );
    CREATE TABLE config(
        chave TEXT PRIMARY KEY,
        valor TEXT
    );
    INSERT INTO config(chave, valor) VALUES
        ('regime_tributario', 'simples'),
        ('uf_origem', 'SP');
    """,
    # v2 — pipeline de disputa (P2): status do funil, data da disputa e
    # valor final proposto/arrematado. NULL em status_pipeline = fora do funil.
    # Backfill: pregões já salvos antes da v2 entram como 'cotacao', mantendo
    # a invariante "todo salvo está no funil" (mesma regra do gatilho do PATCH).
    """
    ALTER TABLE pregoes ADD COLUMN status_pipeline TEXT;
    ALTER TABLE pregoes ADD COLUMN data_disputa TEXT;
    ALTER TABLE pregoes ADD COLUMN valor_final REAL;
    UPDATE pregoes SET status_pipeline='cotacao'
     WHERE salvo=1 AND status_pipeline IS NULL;
    """,
]


def conectar(db_path: Path | str | None = None) -> sqlite3.Connection:
    caminho = Path(db_path) if db_path else settings.DB_PATH
    caminho.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: FastAPI roda endpoints sync em threadpool;
    # cada request usa a própria conexão (deps.get_db), então é seguro.
    con = sqlite3.connect(caminho, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def migrar(con: sqlite3.Connection) -> None:
    versao = con.execute("PRAGMA user_version").fetchone()[0]
    for i, script in enumerate(MIGRACOES[versao:], start=versao + 1):
        con.executescript(script)
        con.execute(f"PRAGMA user_version = {i}")
        con.commit()


def abrir(db_path: Path | str | None = None) -> sqlite3.Connection:
    con = conectar(db_path)
    migrar(con)
    return con
