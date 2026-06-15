"""Sincronizar = itens + arquivos + matching + análise (LLM desligado no teste;
o extrator é coberto em test_m3_habilitacao)."""
from app import settings
from app.services import sincronizacao


def _embed_fake(textos):
    # determinístico, sem modelo real (o e5 é coberto via injeção em test_m2_matching)
    return [(1.0, 0.0) for _ in textos]


def _criar_pregao(con):
    con.execute(
        "INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
        "VALUES ('01613770000172',2026,67,'01613770000172-1-000067/2026')"
    )
    con.commit()
    return con.execute("SELECT id FROM pregoes").fetchone()["id"]


def test_sincronizar_persiste_itens_e_arquivos(con, cliente_fake, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ARQUIVOS_DIR", tmp_path / "arquivos")
    pregao_id = _criar_pregao(con)

    r = sincronizacao.sincronizar(con, pregao_id, cliente_fake, com_habilitacao=False, embed=_embed_fake)

    assert r["itens"] == 4   # fixture real: 4 itens (palanques de Imbaú/PR)
    assert r["arquivos"] == 1
    assert r["erros"] == []

    itens = con.execute("SELECT * FROM itens_pregao ORDER BY numero").fetchall()
    assert len(itens) == 4
    assert itens[0]["valor_unit_estimado"] == 46.59  # valor oficial, nunca "corrigido"
    assert itens[0]["beneficio"] == "Participação exclusiva para ME/EPP"
    assert itens[0]["ncm_pncp"] is None  # órgão não preencheu — fica nulo mesmo

    arq = con.execute("SELECT * FROM arquivos").fetchone()
    assert arq["tipo"] == "Edital"
    assert arq["caminho_local"].endswith(".pdf")

    p = con.execute("SELECT sincronizado_em FROM pregoes").fetchone()
    assert p["sincronizado_em"] is not None


def test_sincronizar_duas_vezes_nao_duplica_itens(con, cliente_fake, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ARQUIVOS_DIR", tmp_path / "arquivos")
    pregao_id = _criar_pregao(con)
    sincronizacao.sincronizar(con, pregao_id, cliente_fake, com_habilitacao=False, embed=_embed_fake)
    # usuário confirmou um match entre as sincronizações
    con.execute("INSERT INTO catalogo_produtos (id, nome, custo_unit) VALUES (1,'P',10)")
    con.execute("UPDATE itens_pregao SET produto_id=1, match_confirmado=1 WHERE numero=1")
    con.commit()

    sincronizacao.sincronizar(con, pregao_id, cliente_fake, com_habilitacao=False, embed=_embed_fake)

    itens = con.execute("SELECT * FROM itens_pregao ORDER BY numero").fetchall()
    assert len(itens) == 4  # upsert, não duplica
    assert itens[0]["match_confirmado"] == 1  # decisão do usuário preservada
    # segunda rodada não baixa o arquivo de novo (já existe em disco)
    assert cliente_fake.chamadas["baixar"] == 1


def test_sincronizar_itens_leve_sem_arquivos(con, cliente_fake):
    """Sincronização leve (abre pregão → itens automáticos): persiste itens e
    calcula análise SEM baixar nenhum arquivo/PDF."""
    pregao_id = _criar_pregao(con)
    r = sincronizacao.sincronizar_itens(con, pregao_id, cliente_fake,
                                        embed=_embed_fake)
    assert r["itens"] == 4
    assert r["erros"] == []
    assert cliente_fake.chamadas["arquivos"] == 0
    assert cliente_fake.chamadas["baixar"] == 0   # leve = zero download
    total = con.execute("SELECT COUNT(*) c FROM itens_pregao").fetchone()["c"]
    assert total == 4
    # valor derivado disponível para a UI (Σ valor_total oficial dos itens)
    soma = con.execute(
        "SELECT SUM(valor_total) s FROM itens_pregao WHERE pregao_id=?",
        (pregao_id,)).fetchone()["s"]
    assert soma == 4659.0 + 43840.0 + 18504.0 + 76180.0  # fixture real Imbaú


def test_persistir_itens_pula_item_sem_numero(con):
    """Item sem numeroItem (órgão omitiu) não pode derrubar a persistência do
    LOTE inteiro: é pulado com log; os demais entram normalmente. (numero é
    INTEGER NOT NULL + parte do UNIQUE → None levantaria IntegrityError e
    abortaria todos os itens do pregão.)"""
    pregao_id = _criar_pregao(con)
    lote = [
        {"numeroItem": 1, "descricao": "Microfone", "quantidade": 2,
         "valorUnitarioEstimado": 100.0, "valorTotal": 200.0},
        {"numeroItem": None, "descricao": "Sem número", "quantidade": 1,
         "valorUnitarioEstimado": 50.0, "valorTotal": 50.0},
        {"numeroItem": 3, "descricao": "Caixa de som", "quantidade": 4,
         "valorUnitarioEstimado": 80.0, "valorTotal": 320.0},
    ]
    persistidos = sincronizacao._persistir_itens(con, pregao_id, lote)
    assert persistidos == 2  # o item sem número foi pulado, não abortou o lote
    numeros = [r["numero"] for r in con.execute(
        "SELECT numero FROM itens_pregao WHERE pregao_id=? ORDER BY numero",
        (pregao_id,))]
    assert numeros == [1, 3]


def test_sincronizar_com_habilitacao_heuristico_nao_explode(
    con, cliente_fake, tmp_path, monkeypatch
):
    """Com habilitação ligada + modo heurístico: PDF fake de 24 bytes extrai texto
    vazio/sem padrões → 0 requisitos, sem erro fatal (princípio: nunca inventa)."""
    monkeypatch.setattr(settings, "ARQUIVOS_DIR", tmp_path / "arquivos")
    monkeypatch.setattr(settings, "EXTRATOR_HABILITACAO", "heuristico")
    # extracao do PDF fake (24 bytes) não tem texto real → simula página vazia
    from app.services import extracao
    monkeypatch.setattr(extracao, "extrair_paginas", lambda _pdf: [""])
    pregao_id = _criar_pregao(con)

    r = sincronizacao.sincronizar(
        con, pregao_id, cliente_fake, com_habilitacao=True, embed=_embed_fake
    )

    assert r["erros"] == []
    assert r["habilitacao"] == 0
    assert con.execute("SELECT COUNT(*) c FROM habilitacao").fetchone()["c"] == 0
