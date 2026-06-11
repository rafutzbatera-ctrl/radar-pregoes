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

    r = sincronizacao.sincronizar(con, pregao_id, cliente_fake, com_llm=False, embed=_embed_fake)

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
    sincronizacao.sincronizar(con, pregao_id, cliente_fake, com_llm=False, embed=_embed_fake)
    # usuário confirmou um match entre as sincronizações
    con.execute("INSERT INTO catalogo_produtos (id, nome, custo_unit) VALUES (1,'P',10)")
    con.execute("UPDATE itens_pregao SET produto_id=1, match_confirmado=1 WHERE numero=1")
    con.commit()

    sincronizacao.sincronizar(con, pregao_id, cliente_fake, com_llm=False, embed=_embed_fake)

    itens = con.execute("SELECT * FROM itens_pregao ORDER BY numero").fetchall()
    assert len(itens) == 4  # upsert, não duplica
    assert itens[0]["match_confirmado"] == 1  # decisão do usuário preservada
    # segunda rodada não baixa o arquivo de novo (já existe em disco)
    assert cliente_fake.chamadas["baixar"] == 1
