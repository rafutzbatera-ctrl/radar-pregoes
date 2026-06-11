"""M2 — matching: threshold 0.83, sugestão nunca vira confirmação,
decisão do usuário nunca é sobrescrita. Embedder determinístico injetado
(a matemática é a mesma do e5 real: cosseno sobre vetores normalizados)."""
import math

from app.services import matching

# vetores 2D normalizados por texto (prefixos e5 incluídos)
_VETORES = {
    "query: Microfone de mesa USB omnidirecional": (1.0, 0.0),
    "query: Canaleta PVC com tampa para piso": (0.6, 0.8),
    "passage: Microfone de mesa USB": (1.0, 0.0),                  # cos=1.0 c/ item 1
    "passage: Caixa de som ativa 200W": (0.0, 1.0),                # cos=0.8 c/ item 2
}


def _embed(textos):
    return [_VETORES[t] for t in textos]


def _montar(con):
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,1,'NC-1')")
    pregao_id = con.execute("SELECT id FROM pregoes").fetchone()["id"]
    con.execute("INSERT INTO catalogo_produtos (id, nome, custo_unit) "
                "VALUES (1, 'Microfone de mesa USB', 800)")
    con.execute("INSERT INTO catalogo_produtos (id, nome, custo_unit) "
                "VALUES (2, 'Caixa de som ativa 200W', 900)")
    con.execute("""INSERT INTO itens_pregao (pregao_id, numero, descricao)
                   VALUES (?,1,'Microfone de mesa USB omnidirecional')""", (pregao_id,))
    con.execute("""INSERT INTO itens_pregao (pregao_id, numero, descricao)
                   VALUES (?,2,'Canaleta PVC com tampa para piso')""", (pregao_id,))
    con.commit()
    return pregao_id


def test_sugere_acima_do_threshold_e_nada_abaixo(con):
    pregao_id = _montar(con)
    n = matching.sugerir_matches(con, pregao_id, embed=_embed)
    assert n == 1

    item1 = con.execute("SELECT * FROM itens_pregao WHERE numero=1").fetchone()
    assert item1["produto_id"] == 1
    assert math.isclose(item1["match_score"], 1.0, abs_tol=1e-4)
    assert item1["match_confirmado"] == 0  # sugestão NUNCA entra confirmada

    item2 = con.execute("SELECT * FROM itens_pregao WHERE numero=2").fetchone()
    assert item2["produto_id"] is None     # melhor score 0.8 < 0.83


def test_nao_sobrescreve_decisao_do_usuario(con):
    pregao_id = _montar(con)
    # usuário casou manualmente o item 1 com o produto 2 e confirmou
    con.execute("UPDATE itens_pregao SET produto_id=2, match_confirmado=1 WHERE numero=1")
    con.commit()
    matching.sugerir_matches(con, pregao_id, embed=_embed)
    item1 = con.execute("SELECT * FROM itens_pregao WHERE numero=1").fetchone()
    assert item1["produto_id"] == 2
    assert item1["match_confirmado"] == 1


def test_catalogo_vazio_nao_quebra(con):
    pregao_id = _montar(con)
    con.execute("DELETE FROM catalogo_produtos")
    con.commit()
    assert matching.sugerir_matches(con, pregao_id, embed=_embed) == 0
