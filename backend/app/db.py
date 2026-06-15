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
    # v3 — custo manual por item, margem alvo e matching conservador (P3).
    # custo_manual: override local do pregão (NULL = sem custo digitado, usa
    # o catálogo se houver match confirmado). produtos_recusados: JSON [ids]
    # de produtos que o usuário recusou para o item — não voltam como sugestão.
    # margem_alvo: usada só na SIMULAÇÃO de itens sem custo (nunca no veredito).
    """
    ALTER TABLE itens_pregao ADD COLUMN custo_manual REAL;
    ALTER TABLE itens_pregao ADD COLUMN produtos_recusados TEXT;
    INSERT OR IGNORE INTO config(chave, valor) VALUES ('margem_alvo', '0.20');
    """,
    # v4 — preço esperado de disputa (P4). O valor do edital é TETO (leilão
    # reverso, menor preço vence); a conta no teto superestima lucro/veredito.
    # lance_previsto: preço esperado digitado por item (NULL = sem lance).
    # desagio_esperado: % global abaixo do teto. Default 0.20 (decisão do dono,
    # 11/06/2026): pregão é leilão reverso, então o sistema já abre num cenário
    # realista de -20% — o cenário fica sempre declarado no hero e é editável.
    # Preço esperado = lance_previsto ▸ teto×(1−deságio) ▸ teto.
    """
    ALTER TABLE itens_pregao ADD COLUMN lance_previsto REAL;
    INSERT OR IGNORE INTO config(chave, valor) VALUES ('desagio_esperado', '0.20');
    """,
    # v5 — potencial aderente (P5). Item aderente = item com produto_id (sugerido
    # ou confirmado) E preço esperado não nulo. receita_aderente = Σ preço×qtd
    # desses itens; itens_aderentes = quantos são. Persistir a RECEITA (não o
    # potencial) evita reprocessar quando a margem alvo muda — só o deságio (P4)
    # dispara re-análise. Ambas preenchidas por analise.analisar_pregao.
    """
    ALTER TABLE pregoes ADD COLUMN receita_aderente REAL;
    ALTER TABLE pregoes ADD COLUMN itens_aderentes INTEGER;
    """,
    # v6 — CAPAG (Capacidade de Pagamento do comprador, fonte Tesouro/SICONFI).
    # Dados oficiais POPULADOS por scripts/seed_capag.py (manual/mensal), nunca
    # no request — o serviço só LÊ. capag_entes casa cnpj→cod_ibge (download do
    # /entes do SICONFI); capag_notas guarda a nota+indicadores do XLSX anual
    # (municípios E estados; estado usa cod_ibge de 2 díg + esfera 'E').
    # Federais NÃO aparecem em nenhuma das duas (não têm CAPAG — princípio 1:
    # sem dado, sem nota inventada).
    """
    CREATE TABLE capag_entes(
        cnpj TEXT PRIMARY KEY,
        cod_ibge TEXT,
        ente TEXT,
        uf TEXT,
        esfera TEXT          -- M (município) | E (estado)
    );
    CREATE TABLE capag_notas(
        cod_ibge TEXT PRIMARY KEY,
        municipio TEXT,
        uf TEXT,
        nota TEXT,           -- nota final CAPAG: A | B | C | D
        ind1 REAL, nota1 TEXT,   -- Indicador 1 (Endividamento) + sua nota
        ind2 REAL, nota2 TEXT,   -- Indicador 2 (Poupança Corrente) + sua nota
        ind3 REAL, nota3 TEXT,   -- Indicador 3 (Liquidez Relativa) + sua nota
        icf TEXT,            -- ranking ICF (ex. "Bicf")
        origem TEXT,         -- "Origem da Nota Final" (ex. "CAPAG Ano Base 2024")
        esfera TEXT          -- M | E
    );
    """,
    # v7 — esfera do órgão comprador no pregão (CAPAG esfera-aware). A API de
    # Consulta (§4.4) traz orgaoEntidade.esferaId ("F" Federal | "E" Estadual |
    # "M" Municipal | "D" Distrital); a busca textual (§4.1) NÃO traz esfera
    # (fica NULL nesse caminho). A esfera, não a localização, decide a CAPAG:
    # federal paga pela União (risco baixo) e NUNCA herda a nota do município
    # onde está sediado (bug do Zionn). NULL = esfera desconhecida → CAPAG não
    # faz fallback por município (evita misatribuir). Pregões pré-v7 ficam NULL.
    """
    ALTER TABLE pregoes ADD COLUMN esfera TEXT;
    """,
    # v8 — material/serviço do item (§4.2 materialOuServicoNome: "Material" |
    # "Serviço"). A sync descartava esse campo, então a coluna do export saía
    # sempre vazia. Agora é persistido na inclusão do item. Itens pré-v8 ficam
    # NULL (honesto, sem backfill — princípio 1: sem dado, sem chute).
    """
    ALTER TABLE itens_pregao ADD COLUMN material_ou_servico TEXT;
    """,
    # v9 — RAG leve, extrativo e citation-grounded (Fase 1). Q&A sobre os
    # documentos de UM edital por vez, isolado por pregao_id (rag_chunks só é
    # consultado dentro do escopo de um pregão — single-user, um edital em foco).
    # Cada chunk guarda offsets de caractere na página original + o texto VERBATIM
    # (pagina[offset_inicio:offset_fim]) para que toda resposta seja extrativa e
    # rastreável ao trecho real (princípios 1 e 2: nunca inventa, citação real).
    # `vetor` = embedding e5 (float32) gravado como BLOB via np.tobytes(); a
    # recuperação reconstrói a matriz com np.frombuffer e faz cosseno (produto
    # interno, vetores já normalizados) em numpy. rag_status = controle de
    # ingestão por pregão (quando, quantos chunks/páginas, qual modelo).
    """
    CREATE TABLE rag_chunks(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pregao_id INTEGER NOT NULL REFERENCES pregoes(id),
        arquivo_id INTEGER REFERENCES arquivos(id),
        pagina INTEGER,
        ordem INTEGER,
        offset_inicio INTEGER,
        offset_fim INTEGER,
        texto TEXT,
        vetor BLOB,
        criado_em TEXT DEFAULT (datetime('now')),
        UNIQUE(pregao_id, arquivo_id, pagina, ordem)
    );
    CREATE INDEX idx_rag_chunks_pregao ON rag_chunks(pregao_id);
    CREATE TABLE rag_status(
        pregao_id INTEGER PRIMARY KEY REFERENCES pregoes(id),
        ingerido_em TEXT,
        n_chunks INTEGER,
        n_paginas INTEGER,
        modelo TEXT
    );
    """,
    # v10 — índices em colunas de FK/filtro quentes (queries reais confirmadas
    # por grep). Todos com IF NOT EXISTS (idempotente; o índice do RAG já foi
    # criado nominalmente na v9). Por que cada um:
    #   itens_pregao(pregao_id): "WHERE pregao_id=?" no resumo do pregão
    #     (routers/pregoes.py), fiscal (services/fiscal.py), matching.
    #   habilitacao(pregao_id): "WHERE pregao_id=?" no resumo, no detalhe da
    #     habilitação (routers/pregoes.py, routers/habilitacao via service) e no
    #     DELETE de re-extração (services/habilitacao.py).
    #   pregoes(salvo): "WHERE salvo=?" na listagem (routers/pregoes.py) e
    #     "WHERE salvo=1" no funil de pipeline (routers/pipeline.py).
    #   pregoes(status_pipeline): lido no funil e no gatilho de entrada
    #     "WHERE id=? AND status_pipeline IS NULL" (routers/pregoes.py).
    #   pregoes(busca_id): "WHERE busca_id=?" na contagem de novos por busca
    #     (routers/buscas.py) e na descoberta (services/descoberta.py).
    # arquivos(pregao_id) NÃO entra: já coberto pelo índice do UNIQUE(pregao_id,
    # url), cuja coluna líder é pregao_id (índice extra seria redundante).
    """
    CREATE INDEX IF NOT EXISTS idx_itens_pregao_pregao ON itens_pregao(pregao_id);
    CREATE INDEX IF NOT EXISTS idx_habilitacao_pregao ON habilitacao(pregao_id);
    CREATE INDEX IF NOT EXISTS idx_pregoes_salvo ON pregoes(salvo);
    CREATE INDEX IF NOT EXISTS idx_pregoes_status_pipeline ON pregoes(status_pipeline);
    CREATE INDEX IF NOT EXISTS idx_pregoes_busca_id ON pregoes(busca_id);
    """,
    # v11 — busca híbrida do RAG (léxica BM25 + semântica e5). Esta migração é
    # só um MARCADOR de versão: NÃO cria a tabela FTS5 aqui. Motivo: a tabela
    # virtual FTS5 é opcional (degradação graciosa) e `executescript` não captura
    # erro por statement — se o build do SQLite não tivesse FTS5, criar a virtual
    # table aqui quebraria `db.abrir()` inteiro. Em vez disso, o índice FTS é
    # criado SOB DEMANDA, de forma tolerante, em rag.indexar_chunks
    # (services/rag.py → _garantir_fts, com try/except). Sem FTS5, o RAG degrada
    # para só-vetor e o resto do schema segue intacto. Schema da tabela (criada
    # lá): rag_fts USING fts5(texto, chunk_id UNINDEXED, pregao_id UNINDEXED,
    #   tokenize='unicode61 remove_diacritics 2')  -- remove acento (prazo/prázo).
    """
    INSERT OR IGNORE INTO config(chave, valor) VALUES ('rag_busca', 'hibrida');
    """,
    # v12 — "Minhas certidões": o fornecedor guarda suas certidões/documentos de
    # habilitação (CND federal, FGTS, trabalhista etc.) com data de validade, e o
    # sistema AVISA quando estão vencidas/perto de vencer — para não perder pregão
    # por documento expirado (reuso entre licitações; complementa o checklist de
    # habilitação extraído do edital). validade = data ISO 'YYYY-MM-DD' ou NULL
    # (sem validade / indeterminada — princípio 1: NULL é honesto, nunca chute).
    # O status (vencida / vence_em_breve / ok / sem_validade) é CALCULADO a partir
    # de hoje (services/certidoes.py), nunca persistido — assim nunca "envelhece"
    # errado no banco.
    """
    CREATE TABLE certidoes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        orgao_emissor TEXT,
        validade TEXT,                   -- ISO 'YYYY-MM-DD' ou NULL = sem validade
        observacao TEXT,
        criado_em TEXT DEFAULT (datetime('now')),
        atualizado_em TEXT
    );
    """,
    # v13 — Cadastro da EMPRESA do licitante (RAG Fase 3, geração de minutas de
    # declarações de habilitação). Tabela de LINHA ÚNICA (id=1): os dados do
    # próprio fornecedor (razão social, CNPJ, endereço, representante, porte)
    # usados para PREENCHER os templates de declaração — NÃO é extração de
    # edital, é texto-padrão do licitante (o gate de citação não se aplica).
    # Por que NÃO usar a tabela `config`: config é allowlist rígida de
    # parâmetros do sistema (routers/config.py CHAVES_VALIDAS), não dado de
    # negócio. Tudo TEXT nullable: cadastro incremental — o usuário preenche aos
    # poucos e cada campo vazio vira lacuna VISÍVEL na minuta (princípio 1:
    # nunca chutar; lacuna explícita "[CAMPO — preencher]"). porte ∈
    # {'me_epp','normal'} ou NULL (não declarado). A linha 1 é criada no PUT
    # (upsert), não aqui — GET sem linha devolve objeto com campos null.
    """
    CREATE TABLE empresa(
        id INTEGER PRIMARY KEY CHECK (id = 1),
        razao_social TEXT,
        cnpj TEXT,
        endereco TEXT,
        representante_nome TEXT,
        representante_cpf TEXT,
        representante_cargo TEXT,
        porte TEXT,                      -- 'me_epp' | 'normal' | NULL
        atualizado_em TEXT
    );
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
    # WAL + synchronous NORMAL: combinação padrão segura que melhora a
    # concorrência leitura×escrita (o app tem scheduler 2×/dia somado a
    # requests). Só vale para db de ARQUIVO; em :memory: o WAL é ignorado
    # em silêncio pelo SQLite, então não há regressão para esse caso.
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
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
