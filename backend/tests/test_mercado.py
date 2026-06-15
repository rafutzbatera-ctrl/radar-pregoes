"""Agregações de inteligência de mercado (Dores #8/#9) sobre resultados_itens.

Insere linhas direto na tabela (a coleta real é testada em test_resultados.py)
e valida historico_precos, concorrentes e os endpoints GET. Princípio nº 1 e
honestidade da amostra: N sempre exposto; sem dados → resposta vazia explícita.
"""
import statistics

from app.services import mercado


def _inserir(con, **kw):
    """Insere uma linha em resultados_itens com defaults sobrescrevíveis."""
    cols = {
        "pregao_id": 1, "cnpj": "01613770000172", "ano": 2026, "seq": 67,
        "numero_item": 1, "descricao": "Caixa de som amplificada",
        "ncm": "85182200", "unidade": "UN", "qtd_homologada": 2,
        "valor_estimado_unit": 1000.0, "valor_homologado_unit": 800.0,
        "desagio_real_pct": 0.20, "vencedor_cnpj": "11111111000111",
        "vencedor_nome": "Alfa Audio LTDA", "vencedor_porte": "ME",
        "data_resultado": "2026-05-01", "orgao_nome": "Prefeitura X",
        "uf": "SP", "coletado_em": "2026-06-15",
    }
    cols.update(kw)
    campos = ", ".join(cols)
    marks = ", ".join("?" for _ in cols)
    con.execute(f"INSERT INTO resultados_itens({campos}) VALUES ({marks})",
                tuple(cols.values()))
    con.commit()


# ---------- historico_precos ----------

def test_historico_por_ncm(con):
    _inserir(con, numero_item=1, ncm="85182200", valor_homologado_unit=800.0,
             desagio_real_pct=0.20, data_resultado="2026-05-01")
    _inserir(con, numero_item=2, ncm="85182200", valor_homologado_unit=600.0,
             desagio_real_pct=0.40, data_resultado="2026-05-03")
    _inserir(con, numero_item=3, ncm="85182200", valor_homologado_unit=1000.0,
             desagio_real_pct=None, data_resultado="2026-05-02")
    # ncm diferente: não deve entrar
    _inserir(con, numero_item=4, ncm="99999999", valor_homologado_unit=50.0,
             data_resultado="2026-05-09")

    out = mercado.historico_precos(con, ncm="85182200")
    assert out["amostra"] == 3
    r = out["resumo"]
    assert r["preco_unit_min"] == 600.0
    assert r["preco_unit_max"] == 1000.0
    assert r["preco_unit_mediana"] == statistics.median([800.0, 600.0, 1000.0])
    # deságio médio só sobre não-nulos: (0.20 + 0.40)/2 = 0.30
    assert abs(r["desagio_medio_pct"] - 0.30) < 1e-9
    # ordenação por data desc
    datas = [it["data_resultado"] for it in out["itens"]]
    assert datas == sorted(datas, reverse=True)


def test_historico_por_termo_match_palavras(con):
    _inserir(con, numero_item=1, descricao="Caixa de som AMPLIFICADA 200W",
             ncm="111", valor_homologado_unit=500.0)
    _inserir(con, numero_item=2, descricao="Microfone sem fio",
             ncm="222", valor_homologado_unit=300.0)
    # acento + caixa: 'áudio' deve casar com termo 'audio'
    _inserir(con, numero_item=3, descricao="Mesa de áudio digital",
             ncm="333", valor_homologado_unit=900.0)

    # termo 'caixa som' casa só o item 1 (todas as palavras presentes)
    out = mercado.historico_precos(con, termo="caixa som")
    assert out["amostra"] == 1
    assert out["itens"][0]["descricao"].startswith("Caixa de som")

    # termo 'audio' (sem acento) casa o item 3 (áudio normalizado)
    out2 = mercado.historico_precos(con, termo="audio")
    assert out2["amostra"] == 1
    assert "udio" in out2["itens"][0]["descricao"]


def test_historico_so_homologado_nao_nulo(con):
    _inserir(con, numero_item=1, valor_homologado_unit=800.0)
    _inserir(con, numero_item=2, valor_homologado_unit=None)
    out = mercado.historico_precos(con)
    assert out["amostra"] == 1


def test_historico_termo_sem_match(con):
    _inserir(con, numero_item=1, descricao="Caixa de som")
    out = mercado.historico_precos(con, termo="helicoptero")
    assert out == {"amostra": 0, "resumo": None, "itens": []}


def test_historico_vazio(con):
    out = mercado.historico_precos(con)
    assert out == {"amostra": 0, "resumo": None, "itens": []}


def test_historico_limite(con):
    for i in range(5):
        _inserir(con, numero_item=i + 1, valor_homologado_unit=100.0 + i,
                 data_resultado=f"2026-05-0{i + 1}")
    out = mercado.historico_precos(con, limite=2)
    assert out["amostra"] == 5  # amostra é o total, não o truncado
    assert len(out["itens"]) == 2


# ---------- concorrentes ----------

def test_concorrentes_agrega(con):
    # Alfa: 2 itens, 2 órgãos, SP+RJ, deságio 0.20 e 0.40 (média 0.30)
    _inserir(con, numero_item=1, vencedor_cnpj="A", vencedor_nome="Alfa",
             vencedor_porte="ME", desagio_real_pct=0.20,
             valor_homologado_unit=800.0, qtd_homologada=2,
             orgao_nome="Org1", uf="SP")
    _inserir(con, numero_item=2, vencedor_cnpj="A", vencedor_nome="Alfa",
             vencedor_porte="ME", desagio_real_pct=0.40,
             valor_homologado_unit=100.0, qtd_homologada=3,
             orgao_nome="Org2", uf="RJ")
    # Beta: 1 item
    _inserir(con, numero_item=3, vencedor_cnpj="B", vencedor_nome="Beta",
             vencedor_porte="EPP", desagio_real_pct=0.10,
             valor_homologado_unit=50.0, qtd_homologada=1,
             orgao_nome="Org1", uf="SP")
    # linha com vencedor nulo é ignorada
    _inserir(con, numero_item=4, vencedor_cnpj=None, vencedor_nome=None)

    out = mercado.concorrentes(con)
    assert out["amostra_itens"] == 3  # ignorou a nula
    concs = out["concorrentes"]
    # ordenado por n_vitorias desc → Alfa primeiro
    assert concs[0]["cnpj"] == "A"
    alfa = concs[0]
    assert alfa["nome"] == "Alfa"
    assert alfa["porte"] == "ME"
    assert alfa["n_vitorias"] == 2
    assert abs(alfa["desagio_medio_pct"] - 0.30) < 1e-9
    # valor_total = 800*2 + 100*3 = 1900
    assert alfa["valor_total_homologado"] == 1900.0
    assert alfa["n_orgaos"] == 2
    assert alfa["ufs"] == ["RJ", "SP"]


def test_concorrentes_nome_porte_mais_frequente(con):
    # mesmo cnpj com nomes/portes variando: pega o mais frequente
    _inserir(con, numero_item=1, vencedor_cnpj="A", vencedor_nome="Alfa SA",
             vencedor_porte=None)
    _inserir(con, numero_item=2, vencedor_cnpj="A", vencedor_nome="Alfa SA",
             vencedor_porte="ME")
    _inserir(con, numero_item=3, vencedor_cnpj="A", vencedor_nome="Alfa LTDA",
             vencedor_porte="ME")
    out = mercado.concorrentes(con)
    c = out["concorrentes"][0]
    assert c["nome"] == "Alfa SA"   # 2x vs 1x
    assert c["porte"] == "ME"       # ignora None, ME é o mais frequente


def test_concorrentes_filtro_uf(con):
    _inserir(con, numero_item=1, vencedor_cnpj="A", uf="SP")
    _inserir(con, numero_item=2, vencedor_cnpj="B", uf="RJ")
    out = mercado.concorrentes(con, uf="SP")
    assert out["amostra_itens"] == 1
    assert out["concorrentes"][0]["cnpj"] == "A"


def test_concorrentes_filtro_termo(con):
    _inserir(con, numero_item=1, vencedor_cnpj="A", descricao="Caixa de som")
    _inserir(con, numero_item=2, vencedor_cnpj="B", descricao="Microfone")
    out = mercado.concorrentes(con, termo="microfone")
    assert out["amostra_itens"] == 1
    assert out["concorrentes"][0]["cnpj"] == "B"


def test_concorrentes_vazio(con):
    out = mercado.concorrentes(con)
    assert out == {"amostra_itens": 0, "concorrentes": []}


def test_concorrentes_valor_total_none_quando_falta_dado(con):
    _inserir(con, numero_item=1, vencedor_cnpj="A",
             valor_homologado_unit=None, qtd_homologada=None,
             desagio_real_pct=None)
    out = mercado.concorrentes(con)
    c = out["concorrentes"][0]
    assert c["valor_total_homologado"] is None
    assert c["desagio_medio_pct"] is None


# ---------- endpoints GET ----------

def test_endpoint_precos_ok(con, client):
    _inserir(con, numero_item=1, descricao="Caixa de som", ncm="85182200")
    r = client.get("/mercado/precos")
    assert r.status_code == 200
    body = r.json()
    assert body["amostra"] == 1
    assert set(body["resumo"]) == {
        "preco_unit_min", "preco_unit_mediana", "preco_unit_max",
        "desagio_medio_pct", "amostra_desagio", "unidades",
    }
    assert "itens" in body

    r2 = client.get("/mercado/precos", params={"q": "caixa", "ncm": "85182200"})
    assert r2.status_code == 200
    assert r2.json()["amostra"] == 1

    r3 = client.get("/mercado/precos", params={"q": "inexistente"})
    assert r3.status_code == 200
    assert r3.json() == {"amostra": 0, "resumo": None, "itens": []}


def test_endpoint_concorrentes_ok(con, client):
    _inserir(con, numero_item=1, vencedor_cnpj="A", uf="SP",
             descricao="Caixa de som")
    r = client.get("/mercado/concorrentes")
    assert r.status_code == 200
    body = r.json()
    assert body["amostra_itens"] == 1
    c = body["concorrentes"][0]
    assert set(c) == {
        "cnpj", "nome", "porte", "n_vitorias", "desagio_medio_pct",
        "n_com_desagio", "valor_total_homologado", "n_com_valor",
        "n_orgaos", "ufs",
    }

    r2 = client.get("/mercado/concorrentes", params={"uf": "SP", "q": "caixa"})
    assert r2.status_code == 200
    assert r2.json()["amostra_itens"] == 1

    r3 = client.get("/mercado/concorrentes", params={"uf": "RJ"})
    assert r3.status_code == 200
    assert r3.json() == {"amostra_itens": 0, "concorrentes": []}
