"""Otimizações PURAS de performance — provas de EQUIVALÊNCIA.

Cada teste fixa a saída ANTES da otimização (cálculo per-item/loop ingênuo) e
exige que a saída DEPOIS seja idêntica campo a campo. As otimizações não podem
mudar nenhum número/shape consumido pelo frontend, export ou PDF.

1. GET /pregoes (listar): N+1 → contagens pré-agregadas com GROUP BY.
2. fiscal.fiscal_do_pregao: N+1 (1 SELECT/produto) → LEFT JOIN único.
3. matching.sugerir_matches / avaliacao.avaliar_alvos: dois fors + _dot → matmul.
"""
import json
import sqlite3


# ---------------------------------------------------------------------------
# 1) GET /pregoes — equivalência da LISTAGEM contra o cálculo per-item antigo
# ---------------------------------------------------------------------------

def _resumo_pregao_antigo(con: sqlite3.Connection, p: sqlite3.Row) -> dict:
    """Réplica EXATA do _resumo_pregao pré-otimização (1+3N queries por pregão).

    Congela o comportamento de referência: a listagem otimizada tem de bater
    campo a campo com isto.
    """
    contagens = con.execute(
        """SELECT COUNT(*) total,
                  SUM(match_confirmado) confirmados,
                  SUM(CASE WHEN produto_id IS NOT NULL AND match_confirmado=0
                      THEN 1 ELSE 0 END) sugeridos,
                  SUM(valor_total) valor_itens
           FROM itens_pregao WHERE pregao_id=?""", (p["id"],)
    ).fetchone()
    hab = con.execute(
        """SELECT COUNT(*) total,
                  SUM(CASE WHEN status_usuario!='ok' THEN 1 ELSE 0 END) pendentes,
                  SUM(CASE WHEN verificada=0 THEN 1 ELSE 0 END) nao_verificadas
           FROM habilitacao WHERE pregao_id=?""", (p["id"],)
    ).fetchone()
    arquivos = con.execute(
        "SELECT id, titulo, tipo, url, caminho_local, baixado_em FROM arquivos WHERE pregao_id=?",
        (p["id"],),
    ).fetchall()
    d = dict(p)
    json_busca = d.pop("json_busca", None)
    d["json_busca"] = json.loads(json_busca) if json_busca else None
    d["itens_total"] = contagens["total"] or 0
    d["itens_confirmados"] = contagens["confirmados"] or 0
    d["itens_sugeridos"] = contagens["sugeridos"] or 0
    d["valor_itens"] = contagens["valor_itens"]
    d["cobertura"] = (d["itens_confirmados"] / d["itens_total"]) if d["itens_total"] else 0
    d["habilitacao_total"] = hab["total"] or 0
    d["habilitacao_pendentes"] = hab["pendentes"] or 0
    d["habilitacao_nao_verificadas"] = hab["nao_verificadas"] or 0
    d["arquivos"] = [dict(a) for a in arquivos]
    d["sincronizado"] = bool(d.get("sincronizado_em"))
    return d


def _semear_pregoes_variados(con: sqlite3.Connection) -> None:
    """Vários pregões com itens/habilitacao/arquivos VARIADOS (incl. zerados)."""
    # Pregão A: 3 itens (1 confirmado, 1 sugerido), 2 hab, 1 arquivo, valores
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, uf, "
                "valor_global, descoberto_em) VALUES "
                "('1',2026,1,'NC-A','SP',1000,'2026-06-01 00:00:00')")
    a = con.execute("SELECT id FROM pregoes WHERE numero_controle='NC-A'").fetchone()["id"]
    con.execute("INSERT INTO catalogo_produtos (id, nome, custo_unit) VALUES (1,'P1',10)")
    con.execute("INSERT INTO itens_pregao (pregao_id, numero, descricao, valor_total, "
                "produto_id, match_confirmado) VALUES (?,1,'i1',100,1,1)", (a,))
    con.execute("INSERT INTO itens_pregao (pregao_id, numero, descricao, valor_total, "
                "produto_id, match_confirmado) VALUES (?,2,'i2',200,1,0)", (a,))
    con.execute("INSERT INTO itens_pregao (pregao_id, numero, descricao, valor_total) "
                "VALUES (?,3,'i3',NULL)", (a,))
    con.execute("INSERT INTO habilitacao (pregao_id, requisito, categoria, status_usuario, "
                "verificada) VALUES (?,'r1','fiscal','ok',1)", (a,))
    con.execute("INSERT INTO habilitacao (pregao_id, requisito, categoria, status_usuario, "
                "verificada) VALUES (?,'r2','juridica','pendente',0)", (a,))
    con.execute("INSERT INTO arquivos (pregao_id, titulo, tipo, url, caminho_local, "
                "baixado_em) VALUES (?,'Edital','Edital','http://x/1','/tmp/1','2026-06-02')", (a,))

    # Pregão B: SEM itens, SEM hab, 2 arquivos, json_busca preenchido
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, uf, json_busca, "
                "descoberto_em) VALUES ('2',2026,2,'NC-B','RJ',?, '2026-06-03 00:00:00')",
                (json.dumps({"q": "audio"}),))
    b = con.execute("SELECT id FROM pregoes WHERE numero_controle='NC-B'").fetchone()["id"]
    con.execute("INSERT INTO arquivos (pregao_id, titulo, tipo, url) "
                "VALUES (?,'A1','Edital','http://x/2')", (b,))
    con.execute("INSERT INTO arquivos (pregao_id, titulo, tipo, url) "
                "VALUES (?,'A2','Anexo','http://x/3')", (b,))

    # Pregão C: 1 item (sigiloso, sem produto), 1 hab nao_verificada, sem arquivo
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, "
                "descoberto_em) VALUES ('3',2026,3,'NC-C','2026-06-04 00:00:00')")
    c = con.execute("SELECT id FROM pregoes WHERE numero_controle='NC-C'").fetchone()["id"]
    con.execute("INSERT INTO itens_pregao (pregao_id, numero, descricao, sigiloso) "
                "VALUES (?,1,'sig',1)", (c,))
    con.execute("INSERT INTO habilitacao (pregao_id, requisito, categoria, status_usuario, "
                "verificada) VALUES (?,'r','tecnica','ok',0)", (c,))

    # Pregão D: totalmente vazio (itens/hab/arquivos zerados)
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, "
                "descoberto_em) VALUES ('4',2026,4,'NC-D','2026-06-05 00:00:00')")
    con.commit()


def test_listar_equivale_ao_calculo_per_item(client, con):
    """GET /pregoes (otimizado) == _resumo_pregao_antigo por pregão, campo a campo."""
    _semear_pregoes_variados(con)

    novo = client.get("/pregoes").json()

    # referência: aplica o resumo antigo na MESMA ordem (descoberto_em DESC)
    linhas = con.execute(
        "SELECT * FROM pregoes ORDER BY descoberto_em DESC").fetchall()
    esperado = [_resumo_pregao_antigo(con, p) for p in linhas]

    assert len(novo) == len(esperado) == 4
    # JSON round-trip iguala tipos (ints vs bools) — compara o contrato de saída
    assert json.loads(json.dumps(novo)) == json.loads(json.dumps(esperado))


def test_listar_filtros_e_ordem_equivalem(client, con):
    """Com filtro de UF e ordenação por valor a saída segue idêntica à referência."""
    _semear_pregoes_variados(con)

    novo = client.get("/pregoes?ordem=valor").json()
    # o router parte da ordem do SQL (descoberto_em DESC) e reordena por valor;
    # a referência precisa da MESMA ordem-base para o tie-break (sort estável).
    linhas = con.execute(
        "SELECT * FROM pregoes ORDER BY descoberto_em DESC").fetchall()
    ref = [_resumo_pregao_antigo(con, p) for p in linhas]
    # mesma ordenação por valor efetivo que o router aplica
    ref.sort(key=lambda d: (
        (d["valor_global"] if d.get("valor_global") is not None
         else d.get("valor_itens")) is None,
        -((d["valor_global"] if d.get("valor_global") is not None
           else d.get("valor_itens")) or 0)))
    assert json.loads(json.dumps(novo)) == json.loads(json.dumps(ref))


def test_detalhe_inalterado_apos_otimizacao(client, con):
    """GET /pregoes/{id} (detalhe) usa _resumo_pregao — deve seguir idêntico."""
    _semear_pregoes_variados(con)
    a = con.execute("SELECT id FROM pregoes WHERE numero_controle='NC-A'").fetchone()["id"]
    p = con.execute("SELECT * FROM pregoes WHERE id=?", (a,)).fetchone()
    esperado = _resumo_pregao_antigo(con, p)
    novo = client.get(f"/pregoes/{a}").json()
    assert json.loads(json.dumps(novo)) == json.loads(json.dumps(esperado))


# ---------------------------------------------------------------------------
# 2) fiscal.fiscal_do_pregao — equivalência LEFT JOIN vs SELECT-por-item
# ---------------------------------------------------------------------------

def _fiscal_antigo(con: sqlite3.Connection, pregao_id: int) -> dict:
    """Réplica EXATA do fiscal_do_pregao pré-otimização (1 SELECT/produto)."""
    from app.services import fiscal
    pregao = con.execute("SELECT uf FROM pregoes WHERE id=?", (pregao_id,)).fetchone()
    cfg = fiscal.config_fiscal(con)
    itens = con.execute(
        "SELECT * FROM itens_pregao WHERE pregao_id=? ORDER BY numero", (pregao_id,)
    ).fetchall()
    resultado = []
    prontos = 0
    cobertos = 0
    for it in itens:
        produto = None
        if it["produto_id"] and it["match_confirmado"]:
            produto = con.execute(
                "SELECT * FROM catalogo_produtos WHERE id=?", (it["produto_id"],)
            ).fetchone()
        f = fiscal.fiscal_do_item(it, produto, pregao["uf"] if pregao else None, cfg)
        f["item_id"] = it["id"]
        f["numero"] = it["numero"]
        f["tem_produto"] = produto is not None
        if produto is not None:
            cobertos += 1
            if f["pronto"]:
                prontos += 1
        resultado.append(f)
    return {
        "itens": resultado, "prontos": prontos, "cobertos": cobertos,
        "total": len(itens), "regime": cfg.get("regime_tributario"),
        "uf_origem": cfg.get("uf_origem"),
        "aviso": ("Sugestões fiscais (NCM, CFOP, CST/CSOSN) são apoio, não orientação "
                  "contábil. Confirme com seu contador antes de emitir a nota."),
    }


def _montar_fiscal(con: sqlite3.Connection, uf_pregao="SP") -> int:
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, uf) "
                "VALUES ('1',2026,1,'NC-1',?)", (uf_pregao,))
    pregao_id = con.execute("SELECT id FROM pregoes").fetchone()["id"]
    con.execute("""INSERT INTO catalogo_produtos
        (id, nome, custo_unit, ncm, unidade, csosn, cst)
        VALUES (1,'Microfone',800,'8518.10.00','UN','102','060')""")
    # item 1: NCM do PNCP + match confirmado (produto entra)
    con.execute("""INSERT INTO itens_pregao
        (pregao_id, numero, descricao, unidade, ncm_pncp, produto_id, match_confirmado)
        VALUES (?,1,'Mic','Unidade','8518.99.99',1,1)""", (pregao_id,))
    # item 2: sem NCM do PNCP (vem do catálogo), match confirmado
    con.execute("""INSERT INTO itens_pregao
        (pregao_id, numero, descricao, unidade, produto_id, match_confirmado)
        VALUES (?,2,'Mic 2','Unidade',1,1)""", (pregao_id,))
    # item 3: produto SUGERIDO (não confirmado) → produto NÃO entra na conta
    con.execute("""INSERT INTO itens_pregao
        (pregao_id, numero, descricao, unidade, produto_id, match_confirmado)
        VALUES (?,3,'Mic 3','Unidade',1,0)""", (pregao_id,))
    # item 4: sem match → faltam dados
    con.execute("""INSERT INTO itens_pregao (pregao_id, numero, descricao)
        VALUES (?,4,'Canaleta')""", (pregao_id,))
    con.commit()
    return pregao_id


def test_fiscal_left_join_equivale_ao_select_por_item(con):
    from app.services import fiscal
    pregao_id = _montar_fiscal(con)
    for regime in ("simples", "presumido"):
        con.execute("UPDATE config SET valor=? WHERE chave='regime_tributario'", (regime,))
        con.commit()
        antigo = _fiscal_antigo(con, pregao_id)
        novo = fiscal.fiscal_do_pregao(con, pregao_id)
        assert novo == antigo, f"divergência no regime {regime}"


def test_fiscal_left_join_uf_diferente(con):
    from app.services import fiscal
    pregao_id = _montar_fiscal(con, uf_pregao="GO")
    assert fiscal.fiscal_do_pregao(con, pregao_id) == _fiscal_antigo(con, pregao_id)


# ---------------------------------------------------------------------------
# 3) matmul — equivalência matching.sugerir_matches e avaliacao.avaliar_alvos
# ---------------------------------------------------------------------------

def test_matching_matmul_equivale_ao_dot_loop(con):
    """sugerir_matches com embed FAKE (listas Python): mesmas sugestões/scores."""
    from app.services import matching
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,1,'NC-1')")
    pid = con.execute("SELECT id FROM pregoes").fetchone()["id"]
    con.execute("INSERT INTO catalogo_produtos (id, nome, custo_unit) VALUES (1,'A',10)")
    con.execute("INSERT INTO catalogo_produtos (id, nome, custo_unit) VALUES (2,'B',20)")
    con.execute("INSERT INTO catalogo_produtos (id, nome, custo_unit) VALUES (3,'C',30)")
    con.execute("INSERT INTO itens_pregao (pregao_id, numero, descricao) "
                "VALUES (?,1,'casa A')", (pid,))
    con.execute("INSERT INTO itens_pregao (pregao_id, numero, descricao) "
                "VALUES (?,2,'casa B mas recusa B')", (pid,))
    # item 2 recusou o produto 2 (B): a recusa tem de ser mascarada antes do argmax
    con.execute("UPDATE itens_pregao SET produtos_recusados='[2]' WHERE numero=2")
    con.commit()

    vetores = {
        "passage: A": [1.0, 0.0, 0.0],
        "passage: B": [0.0, 1.0, 0.0],
        "passage: C": [0.0, 0.0, 1.0],
        "query: casa A": [0.95, 0.30, 0.0],          # melhor = A (0.95) ≥ 0.90
        "query: casa B mas recusa B": [0.0, 1.0, 0.0],  # melhor seria B, mas recusado
    }

    def embed(textos):
        return [vetores[t] for t in textos]

    n = matching.sugerir_matches(con, pid, embed=embed)
    i1 = con.execute("SELECT produto_id, match_score FROM itens_pregao WHERE numero=1").fetchone()
    i2 = con.execute("SELECT produto_id, match_score FROM itens_pregao WHERE numero=2").fetchone()
    # item1 → produto A com score 0.95 arredondado a 4 casas
    assert i1["produto_id"] == 1
    assert i1["match_score"] == round(0.95, 4)
    # item2: B recusado; sobra A(0.0) e C(0.0) < threshold → nada sugerido
    assert i2["produto_id"] is None
    assert n == 1


def test_avaliacao_matmul_equivale_ao_dot_loop(con, cliente_fake):
    """avaliar_alvos com embed FAKE: aderentes/receita idênticos ao loop _dot."""
    from app.services import avaliacao

    con.execute("INSERT INTO catalogo_produtos (nome, custo_unit, ativo) "
                "VALUES ('Palanque tipo T', 20, 1)")
    con.commit()

    class EmbedFake:
        def __call__(self, textos):
            out = []
            for t in textos:
                if t.startswith("passage: "):
                    out.append([1.0, 0.0])
                elif "0,10x0,10x2,20" in t:
                    out.append([1.0, 0.0])
                else:
                    out.append([0.0, 1.0])
            return out

    alvos = [{"cnpj": "01613770000172", "ano": 2026, "seq": 67,
              "numero_controle": "A"}]
    r = avaliacao.avaliar_alvos(con, alvos, cliente=cliente_fake, embed=EmbedFake())
    av = r["avaliados"]["A"]
    # mesma fixture do test_p6: só 1 aderente, receita = 46.59 × 100
    assert av["itens_aderentes"] == 1
    assert av["receita_aderente"] == 46.59 * 100
    assert av["itens_total"] == 4
