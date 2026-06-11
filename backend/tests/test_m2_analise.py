"""M2 — conta de margem/lucro/veredito bate com planilha de referência;
item sem match (ou sem confirmação) NÃO entra na soma."""
import pytest

from app.services import analise


def _montar(con):
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1', 2026, 1, 'NC-1')")
    pregao_id = con.execute("SELECT id FROM pregoes").fetchone()["id"]
    con.execute("INSERT INTO catalogo_produtos (id, nome, custo_unit) VALUES (1,'Prod A',100)")
    con.execute("INSERT INTO catalogo_produtos (id, nome, custo_unit) VALUES (2,'Prod B',50)")
    # item 1: confirmado — entra na conta
    con.execute("""INSERT INTO itens_pregao
        (pregao_id, numero, descricao, qtd, valor_unit_estimado, produto_id, match_confirmado)
        VALUES (?,1,'Item A',20,150,1,1)""", (pregao_id,))
    # item 2: apenas SUGERIDO — fica fora da conta
    con.execute("""INSERT INTO itens_pregao
        (pregao_id, numero, descricao, qtd, valor_unit_estimado, produto_id, match_confirmado)
        VALUES (?,2,'Item B',5,80,2,0)""", (pregao_id,))
    # item 3: sem match — fora, visível e cinza
    con.execute("""INSERT INTO itens_pregao
        (pregao_id, numero, descricao, qtd, valor_unit_estimado)
        VALUES (?,3,'Item C',2,60)""", (pregao_id,))
    con.commit()
    return pregao_id


def test_planilha_de_referencia(con):
    pregao_id = _montar(con)
    r = analise.analisar_pregao(con, pregao_id)

    # planilha: só item 1 confirmado → lucro = (150-100)*20 = 1000
    assert r["lucro_potencial"] == pytest.approx(1000.0)
    # margem ponderada = margem do único item = 50/150
    assert r["margem_media"] == pytest.approx(50 / 150)
    assert r["itens_confirmados"] == 1
    assert r["cobertura"] == pytest.approx(1 / 3)
    # margem 33% ≥ 20% mas cobertura 33% < 60% → não é "vale";
    # margem ≥ 8% e lucro ≥ 300 → não é "nao_vale" → "talvez"
    assert r["veredito"] == "talvez"


def test_confirmar_segundo_item_muda_agregados_e_veredito(con):
    pregao_id = _montar(con)
    con.execute("UPDATE itens_pregao SET match_confirmado=1 WHERE numero=2")
    con.commit()
    r = analise.analisar_pregao(con, pregao_id)

    # lucro = 1000 + (80-50)*5 = 1150
    assert r["lucro_potencial"] == pytest.approx(1150.0)
    # margem ponderada por valor: (1/3*3000 + 0.375*400) / 3400
    esperada = ((50 / 150) * 3000 + 0.375 * 400) / 3400
    assert r["margem_media"] == pytest.approx(esperada)
    assert r["cobertura"] == pytest.approx(2 / 3)
    # margem ~33,8% ≥ 20%, cobertura 66,7% ≥ 60%, lucro 1150 ≥ 1000 → vale
    assert r["veredito"] == "vale"


def test_item_sem_match_nunca_soma(con):
    pregao_id = _montar(con)
    r1 = analise.analisar_pregao(con, pregao_id)
    # dar valor absurdo ao item sem match não muda nada
    con.execute("UPDATE itens_pregao SET valor_unit_estimado=999999 WHERE numero=3")
    con.commit()
    r2 = analise.analisar_pregao(con, pregao_id)
    assert r1["lucro_potencial"] == r2["lucro_potencial"]
    assert r1["margem_media"] == r2["margem_media"]


def test_item_sigiloso_confirmado_fica_fora_do_dinheiro(con):
    pregao_id = _montar(con)
    con.execute(
        """INSERT INTO itens_pregao
           (pregao_id, numero, descricao, qtd, valor_unit_estimado, sigiloso,
            produto_id, match_confirmado)
           VALUES (?,4,'Item sigiloso',12,NULL,1,1,1)""", (pregao_id,))
    con.commit()
    r = analise.analisar_pregao(con, pregao_id)
    assert r["lucro_potencial"] == pytest.approx(1000.0)  # inalterado
    assert r["itens_confirmados"] == 2  # mas conta na cobertura


def test_sem_itens_confirmados_nao_ha_veredito(con):
    pregao_id = _montar(con)
    con.execute("UPDATE itens_pregao SET match_confirmado=0")
    con.commit()
    r = analise.analisar_pregao(con, pregao_id)
    assert r["veredito"] is None
    assert r["lucro_potencial"] is None


def test_nao_vale_por_margem_baixa(con):
    pregao_id = _montar(con)
    con.execute("UPDATE itens_pregao SET valor_unit_estimado=105 WHERE numero=1")
    con.commit()
    r = analise.analisar_pregao(con, pregao_id)
    # margem (105-100)/105 ≈ 4,8% < 8% → nao_vale
    assert r["veredito"] == "nao_vale"
