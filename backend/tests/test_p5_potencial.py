"""P5 — potencial aderente, enriquecimento na descoberta e filtros de valor.

- migração v5 (sobre v4 populado, idempotente);
- analisar_pregao persiste itens_aderentes/receita_aderente (sugerido conta;
  sem produto não; sigiloso sem lance não; receita = Σ preço×qtd);
- rodar_busca enriquece pregões novos + antigos-sem-itens (cliente/embed fakes)
  e tolera falha de um;
- GET /pregoes filtra por faixa de valor e ordena por potencial/valor/prazo;
  422 em ordem inválida.

O embed é SEMPRE fake aqui — o e5 real baixa modelo (proibido em teste).
"""
import sqlite3

import pytest

from app import db
from app.services import analise, descoberta


# embed determinístico que casa "palanque" no catálogo (cos 1.0) e nada mais
def _embed(textos):
    saida = []
    for t in textos:
        corpo = t.split(": ", 1)[-1].lower()
        saida.append((1.0, 0.0) if "palanque" in corpo or "mourão" in corpo
                     else (0.0, 1.0))
    return saida


# ---------- migração v5 ----------

def test_migracao_v5_potencial_aderente(tmp_path):
    """v5 sobre v4 populado: preserva dados, ganha receita_aderente e
    itens_aderentes em pregoes. Idempotente."""
    caminho = tmp_path / "radar.db"
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    # banco até v4 (com dados): roda as 4 primeiras migrações na mão
    for i, script in enumerate(db.MIGRACOES[:4], start=1):
        con.executescript(script)
        con.execute(f"PRAGMA user_version = {i}")
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, veredito, "
                "lucro_potencial) VALUES ('1',2026,1,'NC-1','vale',1234.0)")
    pid = con.execute("SELECT id FROM pregoes").fetchone()["id"]
    con.execute("INSERT INTO itens_pregao (pregao_id, numero, descricao, "
                "lance_previsto) VALUES (?,1,'Item A',55)", (pid,))
    con.commit(); con.close()

    c2 = db.abrir(caminho)                      # migra v4 → v5
    cols = {r[1] for r in c2.execute("PRAGMA table_info(pregoes)")}
    assert "receita_aderente" in cols
    assert "itens_aderentes" in cols
    # dados v4 preservados
    assert c2.execute("SELECT veredito FROM pregoes").fetchone()["veredito"] == "vale"
    assert c2.execute("SELECT lance_previsto FROM itens_pregao").fetchone()[
        "lance_previsto"] == 55
    # colunas novas começam nulas (ainda não analisado)
    assert c2.execute("SELECT receita_aderente FROM pregoes").fetchone()[
        "receita_aderente"] is None
    assert c2.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRACOES)

    # idempotente
    db.migrar(c2)
    assert c2.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRACOES)
    c2.close()


# ---------- aderência em analisar_pregao ----------

def _montar(con):
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,1,'NC-1')")
    pid = con.execute("SELECT id FROM pregoes").fetchone()["id"]
    con.execute("INSERT INTO catalogo_produtos (id, nome, custo_unit) "
                "VALUES (1,'Prod A',100)")
    # item 1: produto SUGERIDO (não confirmado) — aderente conta mesmo assim
    con.execute("""INSERT INTO itens_pregao
        (pregao_id, numero, descricao, qtd, valor_unit_estimado, produto_id, match_confirmado)
        VALUES (?,1,'Item A',20,150,1,0)""", (pid,))
    # item 2: SEM produto — não é aderente
    con.execute("""INSERT INTO itens_pregao
        (pregao_id, numero, descricao, qtd, valor_unit_estimado)
        VALUES (?,2,'Item B',5,80)""", (pid,))
    con.commit()
    return pid


def test_aderente_conta_sugerido_e_ignora_sem_produto(con):
    pid = _montar(con)
    r = analise.analisar_pregao(con, pid)
    # só item1 (produto sugerido) é aderente; receita = teto 150 × 20 = 3000
    assert r["itens_aderentes"] == 1
    assert r["receita_aderente"] == pytest.approx(3000.0)
    # persistido nas colunas novas
    row = con.execute("SELECT itens_aderentes, receita_aderente FROM pregoes "
                      "WHERE id=?", (pid,)).fetchone()
    assert row["itens_aderentes"] == 1
    assert row["receita_aderente"] == pytest.approx(3000.0)


def test_aderente_confirmado_tambem_conta(con):
    pid = _montar(con)
    con.execute("UPDATE itens_pregao SET match_confirmado=1 WHERE numero=1")
    con.commit()
    r = analise.analisar_pregao(con, pid)
    assert r["itens_aderentes"] == 1
    assert r["receita_aderente"] == pytest.approx(3000.0)


def test_aderente_usa_preco_esperado_com_desagio(con):
    """receita aderente segue o preço esperado (P4): deságio 10% → 150×0.9."""
    pid = _montar(con)
    con.execute("INSERT OR REPLACE INTO config (chave, valor) "
                "VALUES ('desagio_esperado','0.10')")
    con.commit()
    r = analise.analisar_pregao(con, pid)
    # preço esperado = 150×0.9 = 135 → receita 135×20 = 2700
    assert r["receita_aderente"] == pytest.approx(2700.0)


def test_aderente_sigiloso_sem_lance_nao_conta(con):
    """Item com produto sugerido mas sigiloso e sem lance → sem preço esperado
    → não é aderente (princípio 1: não inventa valor)."""
    pid = _montar(con)
    con.execute("""INSERT INTO itens_pregao
        (pregao_id, numero, descricao, qtd, valor_unit_estimado, sigiloso,
         produto_id, match_confirmado)
        VALUES (?,3,'Sigiloso',10,NULL,1,1,0)""", (pid,))
    con.commit()
    r = analise.analisar_pregao(con, pid)
    # só item1 aderente; o sigiloso sem lance fica fora
    assert r["itens_aderentes"] == 1
    assert r["receita_aderente"] == pytest.approx(3000.0)
    # com lance, o sigiloso passa a ser aderente
    con.execute("UPDATE itens_pregao SET lance_previsto=70 WHERE numero=3")
    con.commit()
    r2 = analise.analisar_pregao(con, pid)
    assert r2["itens_aderentes"] == 2
    assert r2["receita_aderente"] == pytest.approx(3000.0 + 70 * 10)


def test_sem_aderente_persiste_null(con):
    """Nenhum item com produto → itens_aderentes 0, receita_aderente NULL."""
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,1,'NC-1')")
    pid = con.execute("SELECT id FROM pregoes").fetchone()["id"]
    con.execute("""INSERT INTO itens_pregao
        (pregao_id, numero, descricao, qtd, valor_unit_estimado)
        VALUES (?,1,'Item',5,80)""", (pid,))
    con.commit()
    r = analise.analisar_pregao(con, pid)
    assert r["itens_aderentes"] == 0
    assert r["receita_aderente"] is None
    assert con.execute("SELECT receita_aderente FROM pregoes WHERE id=?", (pid,)
                       ).fetchone()["receita_aderente"] is None


# ---------- enriquecimento na descoberta ----------

def _criar_busca(con) -> int:
    cur = con.execute(
        "INSERT INTO buscas_salvas (nome, termos, ufs) VALUES (?,?,?)",
        ("AV SP", "áudio", "SP"))
    con.commit()
    return cur.lastrowid


def test_rodar_busca_enriquece_novos(con, cliente_fake):
    """Com enriquecer=True, a rodada já puxa os itens (API 4.2) de cada pregão
    novo — sem precisar abrir um a um. embed fake (e5 real é proibido)."""
    busca_id = _criar_busca(con)
    r = descoberta.rodar_busca(con, busca_id, cliente_fake, enriquecer=True,
                               embed=_embed)
    assert r["novos"] == 10
    assert r["enriquecidos"] == 10          # todos os novos enriquecidos
    # cliente.itens chamado uma vez por pregão novo
    assert cliente_fake.chamadas["itens"] == 10
    # itens persistidos (fixture tem 4 itens por pregão)
    total_itens = con.execute("SELECT COUNT(*) c FROM itens_pregao").fetchone()["c"]
    assert total_itens == 10 * 4


def test_rodar_busca_enriquece_antigos_sem_itens(con, cliente_fake):
    """Pregão DESTA busca já no banco mas sem itens entra no enriquecimento
    mesmo não sendo novo nesta rodada."""
    busca_id = _criar_busca(con)
    # pregão antigo desta busca, sem itens
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, busca_id, novo) "
                "VALUES ('99',2025,9,'NC-ANTIGO',?,0)", (busca_id,))
    con.commit()
    # primeira rodada (cache cru) — sem hits novos repetidos: força só o antigo
    r = descoberta.rodar_busca(con, busca_id, cliente_fake, enriquecer=True,
                               embed=_embed)
    # o antigo-sem-itens foi enriquecido (entre os alvos)
    antigo = con.execute("SELECT id FROM pregoes WHERE numero_controle='NC-ANTIGO'"
                         ).fetchone()["id"]
    assert con.execute("SELECT COUNT(*) c FROM itens_pregao WHERE pregao_id=?",
                       (antigo,)).fetchone()["c"] == 4


def test_rodar_busca_tolera_falha_de_um(con):
    """Falha ao enriquecer UM pregão não derruba a rodada: os demais seguem."""
    class ClienteFalhaUm:
        """itens() falha só para o segundo pregão (seq=2)."""
        def __init__(self):
            self.itens_chamado = 0

        def buscar(self, **kw):
            return {"items": [
                {"numero_controle_pncp": "NC-A", "orgao_cnpj": "1",
                 "ano": 2026, "numero_sequencial": 1},
                {"numero_controle_pncp": "NC-B", "orgao_cnpj": "2",
                 "ano": 2026, "numero_sequencial": 2},
                {"numero_controle_pncp": "NC-C", "orgao_cnpj": "3",
                 "ano": 2026, "numero_sequencial": 3},
            ]}

        def itens(self, cnpj, ano, seq, usar_cache=True):
            self.itens_chamado += 1
            if seq == 2:
                raise RuntimeError("PNCP fora do ar para este pregão")
            return [{"numeroItem": 1, "descricao": "x", "quantidade": 1,
                     "valorUnitarioEstimado": 10, "valorTotal": 10}]

    busca_id = _criar_busca(con)
    cli = ClienteFalhaUm()
    r = descoberta.rodar_busca(con, busca_id, cli, enriquecer=True, embed=_embed)
    assert r["novos"] == 3
    # tentou os 3; 2 enriquecidos com sucesso (o que falhou não conta)
    assert cli.itens_chamado == 3
    assert r["enriquecidos"] == 2
    # os dois OK têm itens; o que falhou não
    ok_a = con.execute("SELECT id FROM pregoes WHERE numero_controle='NC-A'"
                       ).fetchone()["id"]
    falha_b = con.execute("SELECT id FROM pregoes WHERE numero_controle='NC-B'"
                          ).fetchone()["id"]
    assert con.execute("SELECT COUNT(*) c FROM itens_pregao WHERE pregao_id=?",
                       (ok_a,)).fetchone()["c"] == 1
    assert con.execute("SELECT COUNT(*) c FROM itens_pregao WHERE pregao_id=?",
                       (falha_b,)).fetchone()["c"] == 0


def test_enriquecer_false_nao_puxa_itens(con, cliente_fake):
    """enriquecer=False mantém o comportamento M1 (só persiste hits)."""
    busca_id = _criar_busca(con)
    r = descoberta.rodar_busca(con, busca_id, cliente_fake, enriquecer=False)
    assert r["enriquecidos"] == 0
    assert cliente_fake.chamadas["itens"] == 0
    assert con.execute("SELECT COUNT(*) c FROM itens_pregao").fetchone()["c"] == 0


# ---------- GET /pregoes: faixa de valor e ordenação ----------

def _pregao(con, nc, **kw):
    cols = ", ".join(kw)
    ph = ", ".join("?" for _ in kw)
    con.execute(
        f"INSERT INTO pregoes (cnpj, ano, seq, numero_controle, {cols}) "
        f"VALUES ('1',2026,1,?,{ph})", (nc, *kw.values()))
    con.commit()
    return con.execute("SELECT id FROM pregoes WHERE numero_controle=?", (nc,)
                       ).fetchone()["id"]


def test_get_pregoes_faixa_de_valor(client, con):
    # seq distintos para não colidir no UNIQUE — usamos valor_global direto
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, valor_global) "
                "VALUES ('1',2026,1,'NC-1',500)")
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, valor_global) "
                "VALUES ('1',2026,2,'NC-2',5000)")
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, valor_global) "
                "VALUES ('1',2026,3,'NC-3',50000)")
    con.commit()
    # faixa 1000..10000 inclusive → só NC-2 (5000)
    saida = client.get("/pregoes?valor_min=1000&valor_max=10000").json()
    assert [p["numero_controle"] for p in saida] == ["NC-2"]
    # só piso 5000 → NC-2 e NC-3
    saida2 = client.get("/pregoes?valor_min=5000").json()
    assert {p["numero_controle"] for p in saida2} == {"NC-2", "NC-3"}


def test_get_pregoes_faixa_sem_valor_fica_fora(client, con):
    """Pregão sem valor efetivo não entra numa faixa com piso (não inventa)."""
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,1,'NC-SEM')")
    con.commit()
    assert client.get("/pregoes?valor_min=100").json() == []
    # sem faixa: aparece normalmente
    assert len(client.get("/pregoes").json()) == 1


def test_get_pregoes_faixa_usa_valor_itens_como_fallback(client, con):
    """Sem valor_global, o valor efetivo é Σ valor_total dos itens."""
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,1,'NC-IT')")
    pid = con.execute("SELECT id FROM pregoes").fetchone()["id"]
    con.execute("INSERT INTO itens_pregao (pregao_id, numero, descricao, "
                "valor_total) VALUES (?,1,'x',3000)", (pid,))
    con.commit()
    assert [p["numero_controle"]
            for p in client.get("/pregoes?valor_min=1000&valor_max=5000").json()
            ] == ["NC-IT"]


def test_get_pregoes_ordem_potencial(client, con):
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, "
                "receita_aderente, itens_aderentes) VALUES ('1',2026,1,'NC-baixo',100,1)")
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, "
                "receita_aderente, itens_aderentes) VALUES ('1',2026,2,'NC-alto',9000,2)")
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,3,'NC-nulo')")
    con.commit()
    saida = client.get("/pregoes?ordem=potencial").json()
    # receita desc; nulo no fim
    assert [p["numero_controle"] for p in saida] == ["NC-alto", "NC-baixo", "NC-nulo"]


def test_get_pregoes_ordem_valor(client, con):
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, valor_global) "
                "VALUES ('1',2026,1,'NC-meio',5000)")
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, valor_global) "
                "VALUES ('1',2026,2,'NC-alto',9000)")
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,3,'NC-semvalor')")
    con.commit()
    saida = client.get("/pregoes?ordem=valor").json()
    # valor desc; sem valor no fim
    assert [p["numero_controle"] for p in saida] == ["NC-alto", "NC-meio", "NC-semvalor"]


def test_get_pregoes_ordem_prazo(client, con):
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, data_fim_vigencia) "
                "VALUES ('1',2026,1,'NC-tarde','2026-12-31')")
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, data_fim_vigencia) "
                "VALUES ('1',2026,2,'NC-cedo','2026-06-15')")
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,3,'NC-semprazo')")
    con.commit()
    saida = client.get("/pregoes?ordem=prazo").json()
    # data asc (mais cedo primeiro); sem prazo no fim
    assert [p["numero_controle"] for p in saida] == ["NC-cedo", "NC-tarde", "NC-semprazo"]


def test_get_pregoes_ordem_recente_default(client, con):
    """Sem ordem (default recente): descoberto_em DESC — último inserido primeiro."""
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, descoberto_em) "
                "VALUES ('1',2026,1,'NC-velho','2026-01-01 00:00:00')")
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle, descoberto_em) "
                "VALUES ('1',2026,2,'NC-novo','2026-06-01 00:00:00')")
    con.commit()
    saida = client.get("/pregoes").json()
    assert [p["numero_controle"] for p in saida] == ["NC-novo", "NC-velho"]


def test_get_pregoes_ordem_invalida_422(client, con):
    assert client.get("/pregoes?ordem=qualquer").status_code == 422
