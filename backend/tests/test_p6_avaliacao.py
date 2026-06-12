"""P6 — Avaliação sob demanda no modo PNCP ao vivo (valor real + potencial).

Tudo EM MEMÓRIA: o cliente_fake serve a fixture real de itens (4 palanques) e o
embed é SEMPRE fake (nunca o e5 real). Confere valor/aderentes/receita contra a
fixture, o deságio da config, catálogo vazio (embed não é chamado), falha por
alvo, limites (>40 → 422, vazio → 422) e que NADA persiste.
"""
import pytest

from app import pncp as pncp_mod
from app.services import avaliacao

# fixture real itens_01613770000172_2026_67.json (4 palanques, todos não sigilosos):
# valorTotal: 4659 + 43840 + 18504 + 76180
VALOR_ITENS = 4659.0 + 43840.0 + 18504.0 + 76180.0  # 143183.0
# item 1: valorUnitarioEstimado 46.59 × quantidade 100 = 4659.0 (no teto)
RECEITA_ITEM1_TETO = 46.59 * 100


def _patch_pncp(monkeypatch, cliente):
    monkeypatch.setattr(pncp_mod, "cliente", lambda: cliente)


def test_avaliar_conta_itens_de_servico(con):
    """materialOuServico S/M oficial alimenta o filtro 'só compra de bens' (P9)."""
    class ClienteMisto:
        def itens(self, cnpj, ano, seq):
            return [
                {"numeroItem": 1, "descricao": "Serviço de manutenção predial",
                 "materialOuServico": "S", "valorTotal": 100.0,
                 "valorUnitarioEstimado": 100.0, "quantidade": 1},
                {"numeroItem": 2, "descricao": "Cabo HDMI 5 m",
                 "materialOuServico": "M", "valorTotal": 50.0,
                 "valorUnitarioEstimado": 50.0, "quantidade": 1},
            ]

    r = avaliacao.avaliar_alvos(
        con, [{"cnpj": "1", "ano": 2026, "seq": 1, "numero_controle": "NC-MISTO"}],
        cliente=ClienteMisto(), embed=lambda ts: [(0.0, 1.0) for _ in ts],
    )
    av = r["avaliados"]["NC-MISTO"]
    assert av["itens_total"] == 2
    assert av["itens_servico"] == 1


def _add_produto(con, nome="Palanque tipo T", custo=20.0):
    con.execute(
        "INSERT INTO catalogo_produtos (nome, custo_unit, ativo) VALUES (?,?,1)",
        (nome, custo),
    )
    con.commit()


class EmbedFake:
    """Casa SÓ o 1º item (palanque tipo T) ≥0.90; os demais ficam <0.90.

    Produtos viram vetor [1,0]; o item cuja descrição começa com o palanque
    tipo T 0,10x0,10x2,20 (numeroItem 1) também vira [1,0] (cosseno 1.0); os
    outros itens viram [0,1] (cosseno 0). Conta chamadas para provar que o
    catálogo vazio nunca dispara embed.
    """

    def __init__(self):
        self.chamadas = 0

    def __call__(self, textos):
        self.chamadas += 1
        out = []
        for t in textos:
            if t.startswith("passage: "):
                out.append([1.0, 0.0])
            elif "0,10x0,10x2,20" in t:   # numeroItem 1 (único aderente)
                out.append([1.0, 0.0])
            else:
                out.append([0.0, 1.0])
        return out


class EmbedExplode:
    """Levanta se chamado — prova que catálogo vazio pula o matching."""

    def __call__(self, textos):
        raise AssertionError("embed não deveria ser chamado com catálogo vazio")


class ClienteParcial:
    """itens() funciona, mas levanta para um cnpj específico (falha por alvo)."""

    def __init__(self, itens, cnpj_quebra):
        self._itens = itens
        self._cnpj_quebra = cnpj_quebra
        self.chamadas = 0

    def itens(self, cnpj, ano, seq, usar_cache=True):
        self.chamadas += 1
        if cnpj == self._cnpj_quebra:
            raise RuntimeError("PNCP indisponível para este pregão")
        return self._itens


def _alvos(*ncs):
    return [{"cnpj": "0161377000017" + str(i), "ano": 2026, "seq": 67 + i,
             "numero_controle": nc} for i, nc in enumerate(ncs)]


# --------- serviço: valor/aderentes/receita contra a fixture real ---------

def test_avaliar_dois_alvos_valor_aderentes_receita(con, cliente_fake):
    _add_produto(con)
    embed = EmbedFake()
    alvos = _alvos("A", "B")
    r = avaliacao.avaliar_alvos(con, alvos, cliente=cliente_fake, embed=embed)

    assert set(r["avaliados"]) == {"A", "B"}
    assert r["erros"] == {}
    for nc in ("A", "B"):
        av = r["avaliados"][nc]
        assert av["valor_itens"] == VALOR_ITENS
        assert av["itens_total"] == 4
        assert av["itens_aderentes"] == 1          # só o palanque tipo T casa ≥0.90
        assert av["receita_aderente"] == pytest.approx(RECEITA_ITEM1_TETO)
    # embed do catálogo 1× + itens 1× por alvo (catálogo fora do loop de alvos)
    assert embed.chamadas == 1 + len(alvos)
    # NADA persistiu
    assert con.execute("SELECT COUNT(*) c FROM pregoes").fetchone()["c"] == 0
    assert con.execute("SELECT COUNT(*) c FROM itens_pregao").fetchone()["c"] == 0


def test_avaliar_respeita_desagio_da_config(con, cliente_fake):
    _add_produto(con)
    con.execute("UPDATE config SET valor='0.10' WHERE chave='desagio_esperado'")
    con.commit()
    r = avaliacao.avaliar_alvos(con, _alvos("A"), cliente=cliente_fake, embed=EmbedFake())
    av = r["avaliados"]["A"]
    # preço esperado = teto × (1 − 0,10); receita = 46.59 × 0.9 × 100
    assert av["receita_aderente"] == pytest.approx(RECEITA_ITEM1_TETO * 0.9)


def test_avaliar_catalogo_vazio_zero_aderentes_sem_embed(con, cliente_fake):
    # catálogo vazio → 0 aderentes, receita null, embed NUNCA chamado
    r = avaliacao.avaliar_alvos(con, _alvos("A"), cliente=cliente_fake, embed=EmbedExplode())
    av = r["avaliados"]["A"]
    assert av["itens_total"] == 4
    assert av["valor_itens"] == VALOR_ITENS
    assert av["itens_aderentes"] == 0
    assert av["receita_aderente"] is None


def test_avaliar_alvo_que_falha_entra_em_erros(con, cliente_fake):
    _add_produto(con)
    itens = cliente_fake.itens("x", 2026, 67)   # fixture real (4 palanques)
    cli = ClienteParcial(itens, cnpj_quebra="01613770000170")  # cnpj do 1º alvo
    r = avaliacao.avaliar_alvos(con, _alvos("A", "B"), cliente=cli, embed=EmbedFake())
    assert "A" in r["erros"]                       # 1º alvo falhou
    assert "A" not in r["avaliados"]
    assert "B" in r["avaliados"]                   # 2º avaliado normalmente
    assert r["avaliados"]["B"]["itens_total"] == 4


# --------- endpoint: limites e contrato ---------

def test_avaliar_endpoint_dois_alvos(client, con, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    _add_produto(con)
    # embed real seria caríssimo no endpoint; substitui pelo fake no serviço
    monkeypatch.setattr(avaliacao.matching, "embed_padrao", EmbedFake())
    corpo = {"alvos": [
        {"cnpj": "01613770000172", "ano": 2026, "seq": 67, "numero_controle": "A"},
        {"cnpj": "01613770000172", "ano": 2026, "seq": 68, "numero_controle": "B"},
    ]}
    r = client.post("/descobrir/avaliar", json=corpo)
    assert r.status_code == 200
    dados = r.json()
    assert dados["avaliados"]["A"]["itens_aderentes"] == 1
    assert dados["avaliados"]["A"]["valor_itens"] == VALOR_ITENS
    assert dados["erros"] == {}
    # endpoint não persiste
    assert con.execute("SELECT COUNT(*) c FROM pregoes").fetchone()["c"] == 0


def test_avaliar_endpoint_excesso_422(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    alvos = [{"cnpj": "0", "ano": 2026, "seq": i, "numero_controle": str(i)}
             for i in range(41)]                   # 41 > 40
    r = client.post("/descobrir/avaliar", json={"alvos": alvos})
    assert r.status_code == 422


def test_avaliar_endpoint_vazio_422(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    r = client.post("/descobrir/avaliar", json={"alvos": []})
    assert r.status_code == 422
