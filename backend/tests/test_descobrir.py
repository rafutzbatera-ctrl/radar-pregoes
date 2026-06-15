"""Feature — PNCP ao vivo: explorar a busca do PNCP sem persistir + importar.

Usa o cliente_fake (fixture real de busca) monkeypatchado em pncp.cliente,
sem bater na API.
"""
from app import pncp as pncp_mod
from app.services import matching as matching_mod


def _patch_pncp(monkeypatch, cliente):
    monkeypatch.setattr(pncp_mod, "cliente", lambda: cliente)


def test_descobrir_retorna_total_e_itens_adaptados(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    r = client.get("/descobrir?q=áudio&ufs=SP")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["total"] == 39       # fixture real: total nacional do hit
    assert corpo["pagina"] == 1
    assert corpo["tamanho"] == 50
    assert len(corpo["itens"]) == 10  # fixture real: 10 hits
    item = corpo["itens"][0]
    # campos adaptados para o cartão
    for campo in ("numero_controle", "titulo", "orgao", "uf", "cnpj", "ano", "seq",
                  "ja_no_radar", "pregao_id", "hit"):
        assert campo in item
    assert item["ja_no_radar"] is False
    assert item["pregao_id"] is None
    # hit cru preservado para reenviar no importar
    assert item["hit"]["numero_controle_pncp"] == item["numero_controle"]


def test_descobrir_q_vazio_nao_quebra(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    r = client.get("/descobrir")
    assert r.status_code == 200
    # P7: q vazio + recebendo + edital → fonte EM MASSA (§4.4); total da consulta
    corpo = r.json()
    assert corpo["fonte"] == "consulta"
    assert corpo["total"] == 4874


def test_descobrir_marca_ja_no_radar(client, con, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    # pega o numero_controle do primeiro hit e insere localmente
    hit = cliente_fake.buscar("áudio")["items"][0]
    nc = hit["numero_controle_pncp"]
    con.execute(
        "INSERT INTO pregoes (cnpj, ano, seq, numero_controle) VALUES (?,?,?,?)",
        (hit["orgao_cnpj"], int(hit["ano"]), int(hit["numero_sequencial"]), nc),
    )
    con.commit()
    local_id = con.execute(
        "SELECT id FROM pregoes WHERE numero_controle=?", (nc,)
    ).fetchone()["id"]

    itens = client.get("/descobrir?q=áudio").json()["itens"]
    achado = next(i for i in itens if i["numero_controle"] == nc)
    assert achado["ja_no_radar"] is True
    assert achado["pregao_id"] == local_id


def test_importar_cria_pregao_e_e_idempotente(client, con, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    itens = client.get("/descobrir?q=áudio").json()["itens"]
    alvo = itens[0]

    r = client.post("/descobrir/importar", json={
        "numero_controle": alvo["numero_controle"], "hit": alvo["hit"],
    })
    assert r.status_code == 200
    pregao = r.json()
    assert pregao["numero_controle"] == alvo["numero_controle"]
    assert pregao["novo"] == 1
    assert pregao["link_pncp"].startswith("https://pncp.gov.br/app/editais/")
    assert pregao["busca_id"] is None
    assert con.execute("SELECT COUNT(*) c FROM pregoes").fetchone()["c"] == 1

    # repetir não duplica e retorna o existente (mesmo id)
    r2 = client.post("/descobrir/importar", json={
        "numero_controle": alvo["numero_controle"], "hit": alvo["hit"],
    })
    assert r2.status_code == 200
    assert r2.json()["id"] == pregao["id"]
    assert con.execute("SELECT COUNT(*) c FROM pregoes").fetchone()["c"] == 1


def test_descobrir_pncp_fora_retorna_503(client, monkeypatch):
    class ClienteQuebrado:
        def buscar(self, *a, **k):
            raise RuntimeError("PNCP indisponível após 5 tentativas")

    _patch_pncp(monkeypatch, ClienteQuebrado())
    r = client.get("/descobrir?q=áudio")
    assert r.status_code == 503


# --------- filtros avançados + chips de palavras-chave ---------

class ClienteCapturador:
    """Devolve hits controlados por termo e registra os kwargs de cada buscar."""

    def __init__(self, por_termo=None, total_por_termo=39):
        self.por_termo = por_termo or {}
        self.total_por_termo = total_por_termo
        self.buscas = []

    def buscar(self, q="", ufs="", status="", pagina=1, tamanho=50, usar_cache=True,
               tipos_documento="edital", ordenacao="-data", modalidades="", esferas=""):
        self.buscas.append({
            "q": q, "ufs": ufs, "status": status, "pagina": pagina,
            "tipos_documento": tipos_documento, "ordenacao": ordenacao,
            "modalidades": modalidades, "esferas": esferas,
        })
        items = self.por_termo.get(q, [])
        return {"items": items, "total": self.total_por_termo}


def _hit(nc, title="t", description="d", orgao="o"):
    return {
        "numero_controle_pncp": nc, "title": title, "description": description,
        "orgao_nome": orgao, "orgao_cnpj": "00000000000000", "ano": "2026",
        "numero_sequencial": "1",
    }


def test_descobrir_repassa_kwargs_e_status_todos(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    r = client.get("/descobrir?q=áudio&status=todos&tipos_documento=ata"
                   "&ordenacao=relevancia&modalidades=6,8&esferas=M,F")
    assert r.status_code == 200
    # a busca do PNCP só aceita UM valor por filtro (csv → total=0 silencioso,
    # verificado 12/06/2026): modalidades × esferas viram produto cartesiano
    pares = sorted((b["modalidades"], b["esferas"]) for b in cliente_fake.buscas)
    assert pares == [("6", "F"), ("6", "M"), ("8", "F"), ("8", "M")]
    for chamada in cliente_fake.buscas:
        assert chamada["status"] == "todos"  # "todos" repassado (e nunca omitido)
        assert chamada["tipos_documento"] == "ata"
        assert chamada["ordenacao"] == "relevancia"


# --------- fan-out por modalidade/UF/esfera na busca textual (12/06/2026) ---------

def test_busca_multi_modalidades_uma_chamada_por_id(client, monkeypatch):
    # modalidades=6,8 com 1 termo → 2 chamadas (nunca csv); total = soma e segue
    # EXATO (cada pregão tem uma única modalidade — eixos disjuntos)
    cli = ClienteCapturador(por_termo={"notebook": [_hit("A")]}, total_por_termo=10)
    _patch_pncp(monkeypatch, cli)
    r = client.get("/descobrir?q=notebook&modalidades=6,8")
    corpo = r.json()
    assert sorted(b["modalidades"] for b in cli.buscas) == ["6", "8"]
    assert all(b["q"] == "notebook" for b in cli.buscas)
    assert corpo["total"] == 20
    assert corpo["total_exato"] is True


def test_busca_fanout_cartesiano_uf_esfera(client, monkeypatch):
    # ufs=SP,RJ × esferas=M,F → 4 chamadas, cada uma com valor ÚNICO por filtro
    cli = ClienteCapturador(por_termo={"x": [_hit("A")]}, total_por_termo=5)
    _patch_pncp(monkeypatch, cli)
    r = client.get("/descobrir?q=x&ufs=SP,RJ&esferas=M,F")
    pares = sorted((b["ufs"], b["esferas"]) for b in cli.buscas)
    assert pares == [("RJ", "F"), ("RJ", "M"), ("SP", "F"), ("SP", "M")]
    assert r.json()["total"] == 20


def test_busca_excesso_de_ufs_descarta_filtro(client, monkeypatch):
    # >4 UFs → sem filtro server-side (mesmo padrão do bulk) e total vira "até N"
    cli = ClienteCapturador(por_termo={"x": [_hit("A")]})
    _patch_pncp(monkeypatch, cli)
    r = client.get("/descobrir?q=x&ufs=SP,RJ,MG,PR,SC")
    assert [b["ufs"] for b in cli.buscas] == [""]
    assert r.json()["total_exato"] is False


def test_busca_todas_as_esferas_descarta_filtro(client, monkeypatch):
    # >3 esferas (= praticamente todas) → sem filtro server-side
    cli = ClienteCapturador(por_termo={"x": [_hit("A")]})
    _patch_pncp(monkeypatch, cli)
    r = client.get("/descobrir?q=x&esferas=F,E,M,D")
    assert [b["esferas"] for b in cli.buscas] == [""]
    assert r.json()["total_exato"] is False


def test_busca_estouro_de_chamadas_descarta_ufs_preserva_modalidades(client, monkeypatch):
    # 2 termos × 5 modalidades × 3 UFs = 30 > teto (25) → descarta o eixo UF;
    # modalidades ficam (carregam o "só compra de bens") e termos são sagrados
    cli = ClienteCapturador(por_termo={"a": [_hit("A")], "b": [_hit("B")]})
    _patch_pncp(monkeypatch, cli)
    r = client.get("/descobrir?q=a&q=b&modalidades=4,5,6,7,8&ufs=SP,RJ,MG")
    assert len(cli.buscas) == 10                       # 2 termos × 5 modalidades
    assert all(b["ufs"] == "" for b in cli.buscas)
    assert {b["modalidades"] for b in cli.buscas} == {"4", "5", "6", "7", "8"}
    assert r.json()["total_exato"] is False


def test_descobrir_multi_termo_n_chamadas_e_dedup(client, monkeypatch):
    # termo1 e termo2 compartilham o hit "B" → deve aparecer uma vez só
    cli = ClienteCapturador(por_termo={
        "microfone": [_hit("A"), _hit("B")],
        "caixa de som": [_hit("B"), _hit("C")],
    })
    _patch_pncp(monkeypatch, cli)
    r = client.get("/descobrir?q=microfone&q=caixa de som")
    assert r.status_code == 200
    corpo = r.json()
    # duas consultas (uma por termo)
    assert [b["q"] for b in cli.buscas] == ["microfone", "caixa de som"]
    # dedup por numero_controle: A, B, C (não A, B, B, C)
    ncs = [i["numero_controle"] for i in corpo["itens"]]
    assert ncs == ["A", "B", "C"]
    # total = soma dos totais por termo; total_exato false (>1 termo)
    assert corpo["total"] == 78
    assert corpo["total_exato"] is False


def test_descobrir_multi_termo_round_robin(client, monkeypatch):
    # intercala: 1º de cada termo, depois 2º de cada — não enviesa para o 1º
    cli = ClienteCapturador(por_termo={
        "x": [_hit("X1"), _hit("X2")],
        "y": [_hit("Y1"), _hit("Y2")],
    })
    _patch_pncp(monkeypatch, cli)
    r = client.get("/descobrir?q=x&q=y")
    ncs = [i["numero_controle"] for i in r.json()["itens"]]
    assert ncs == ["X1", "Y1", "X2", "Y2"]


def test_descobrir_exclusao_normaliza_acento(client, monkeypatch):
    # excluir "usado" deve derrubar hit com "ÚSADO" (via normalização sem acento)
    cli = ClienteCapturador(por_termo={
        "projetor": [
            _hit("OK", title="Projetor novo"),
            _hit("FORA", title="Projetor ÚSADO em leilão"),
        ],
    }, total_por_termo=2)
    _patch_pncp(monkeypatch, cli)
    r = client.get("/descobrir?q=projetor&excluir=usado")
    corpo = r.json()
    ncs = [i["numero_controle"] for i in corpo["itens"]]
    assert ncs == ["OK"]                    # FORA derrubado pela exclusão
    assert corpo["total_exato"] is False    # exclusão presente → não exato


def test_descobrir_total_exato_termo_unico(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    # 1 termo, sem exclusão → exato
    assert client.get("/descobrir?q=áudio").json()["total_exato"] is True
    # sem termo nenhum → ainda exato
    assert client.get("/descobrir").json()["total_exato"] is True


def test_descobrir_excesso_de_termos_422(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    qs = "&".join(f"q=t{i}" for i in range(6))   # 6 termos > 5
    assert client.get("/descobrir?" + qs).status_code == 422


def test_descobrir_status_invalido_422(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    assert client.get("/descobrir?status=banana").status_code == 422


def test_descobrir_modalidade_invalida_422(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    assert client.get("/descobrir?modalidades=99").status_code == 422


def test_descobrir_esfera_invalida_422(client, cliente_fake, monkeypatch):
    _patch_pncp(monkeypatch, cliente_fake)
    assert client.get("/descobrir?esferas=X").status_code == 422


# --------- so_bens: pós-filtro aquisição-aware (classificador) ---------

class ClienteBulkCapturador:
    """Fake da fonte EM MASSA (§4.4): devolve registros controlados e registra
    o tamanhoPagina de cada consulta (a API trava em 50 — sem bump)."""

    def __init__(self, registros):
        self.registros = registros
        self.consultas = []

    def consulta_propostas(self, data_final, modalidade="", uf="", pagina=1,
                           tamanho=50, usar_cache=True):
        self.consultas.append({"tamanho": tamanho, "modalidade": modalidade, "uf": uf})
        return {"data": self.registros, "totalRegistros": len(self.registros)}


def _reg(nc, objeto, numero="1"):
    return {
        "numeroControlePNCP": nc,
        "objetoCompra": objeto,
        "orgaoEntidade": {"cnpj": "00000000000000", "razaoSocial": "Órgão X"},
        "unidadeOrgao": {"ufSigla": "SP", "municipioNome": "São Paulo"},
        "tipoInstrumentoConvocatorioNome": "Edital",
        "numeroCompra": numero, "anoCompra": 2026, "sequencialCompra": 1,
        "modalidadeNome": "Pregão Eletrônico",
        "valorTotalEstimado": 1000.0,
    }


def test_so_bens_derruba_servico_concessao_na_fonte_bulk(client, monkeypatch):
    # 3 registros: 1 bem (aquisição), 1 serviço (prestação), 1 concessão (credenciamento)
    cli = ClienteBulkCapturador([
        _reg("BEM", "Aquisição de notebooks para a Secretaria de Educação"),
        _reg("SERV", "Prestação de serviços de limpeza e conservação do prédio"),
        _reg("CONC", "Credenciamento de instituições financeiras"),
    ])
    _patch_pncp(monkeypatch, cli)
    r = client.get("/descobrir?so_bens=true")
    corpo = r.json()
    assert corpo["fonte"] == "consulta"
    ncs = [i["numero_controle"] for i in corpo["itens"]]
    assert ncs == ["BEM"]                 # serviço e concessão derrubados
    assert corpo["total_exato"] is False  # pós-filtro → não exato


def test_so_bens_mantem_tamanho_pagina_no_teto_da_api(client, monkeypatch):
    # a API de Consulta trava tamanhoPagina em 50 (60+ → 400, verificado
    # 13/06/2026): so_bens NÃO sobe a página; quem compensa é o fan-out
    cli = ClienteBulkCapturador([_reg("BEM", "Aquisição de cadeiras")])
    _patch_pncp(monkeypatch, cli)
    client.get("/descobrir?so_bens=true")
    assert all(c["tamanho"] == 50 for c in cli.consultas)
    cli.consultas.clear()
    client.get("/descobrir")
    assert all(c["tamanho"] == 50 for c in cli.consultas)


def test_so_bens_off_nao_filtra(client, monkeypatch):
    cli = ClienteBulkCapturador([
        _reg("BEM", "Aquisição de notebooks"),
        _reg("SERV", "Prestação de serviços de vigilância"),
    ])
    _patch_pncp(monkeypatch, cli)
    ncs = [i["numero_controle"] for i in client.get("/descobrir").json()["itens"]]
    assert set(ncs) == {"BEM", "SERV"}      # sem so_bens, nada é cortado


def test_so_bens_filtra_tambem_na_busca_textual(client, monkeypatch):
    # na fonte textual o pós-filtro usa title + description do hit
    cli = ClienteCapturador(por_termo={"x": [
        _hit("BEM", title="Aquisição de microfones", description="equipamento de áudio"),
        _hit("SERV", title="Prestação de serviços de consultoria", description="gestão"),
    ]}, total_por_termo=2)
    _patch_pncp(monkeypatch, cli)
    ncs = [i["numero_controle"] for i in client.get("/descobrir?q=x&so_bens=true").json()["itens"]]
    assert ncs == ["BEM"]


# --------- re-rank LOCAL opcional (e5) da página corrente ---------

def _fake_embed_por_palavra(textos):
    """Embed determinístico 2D: o eixo escolhido depende de uma palavra-chave no
    texto. Vetores unitários → produto escalar = cosseno. "microfone" aponta p/
    o eixo 0, "cadeira" p/ o eixo 1; a query "microfone" casa 1.0 com microfone
    e 0.0 com cadeira (ordena microfone acima)."""
    import numpy as np
    vets = []
    for t in textos:
        low = t.lower()
        if "microfone" in low:
            vets.append([1.0, 0.0])
        elif "cadeira" in low:
            vets.append([0.0, 1.0])
        else:
            vets.append([0.7071, 0.7071])
    return np.asarray(vets, dtype=float)


def test_rerank_reordena_por_similaridade(client, monkeypatch):
    # PNCP devolve cadeira ANTES de microfone; com rerank=true e termo
    # "microfone" o microfone deve subir (similaridade local), sem mudar quais
    # hits vêm nem o total.
    cli = ClienteCapturador(por_termo={"microfone": [
        _hit("CADEIRA", title="Aquisição de cadeiras", description="mobiliário"),
        _hit("MIC", title="Aquisição de microfone", description="áudio"),
    ]}, total_por_termo=2)
    _patch_pncp(monkeypatch, cli)
    monkeypatch.setattr(matching_mod, "embed_padrao", _fake_embed_por_palavra)
    r = client.get("/descobrir?q=microfone&ordenacao=relevancia&rerank=true")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["rerank_aplicado"] is True
    ncs = [i["numero_controle"] for i in corpo["itens"]]
    assert ncs == ["MIC", "CADEIRA"]          # microfone subiu
    assert corpo["total"] == 2                # total oficial intacto


def test_rerank_anexa_score_e_flag(client, monkeypatch):
    cli = ClienteCapturador(por_termo={"microfone": [
        _hit("MIC", title="microfone", description="áudio"),
        _hit("CAD", title="cadeira", description="mobiliário"),
    ]}, total_por_termo=2)
    _patch_pncp(monkeypatch, cli)
    monkeypatch.setattr(matching_mod, "embed_padrao", _fake_embed_por_palavra)
    corpo = client.get("/descobrir?q=microfone&ordenacao=relevancia&rerank=true").json()
    assert corpo["rerank_aplicado"] is True
    assert "rerank_motivo" not in corpo
    for it in corpo["itens"]:
        assert "rerank_score" in it
        assert isinstance(it["rerank_score"], float)
    # o microfone (score ~1.0) acima da cadeira (~0.0)
    assert corpo["itens"][0]["numero_controle"] == "MIC"
    assert corpo["itens"][0]["rerank_score"] > corpo["itens"][1]["rerank_score"]


def test_rerank_e5_indisponivel_degrada_gracioso(client, monkeypatch):
    # embed lança → ordem ORIGINAL do PNCP, status 200, rerank_aplicado=false + motivo
    cli = ClienteCapturador(por_termo={"microfone": [
        _hit("A", title="cadeira"),
        _hit("B", title="microfone"),
    ]}, total_por_termo=2)
    _patch_pncp(monkeypatch, cli)

    def _boom(textos):
        raise RuntimeError("e5 não carregou")

    monkeypatch.setattr(matching_mod, "embed_padrao", _boom)
    r = client.get("/descobrir?q=microfone&ordenacao=relevancia&rerank=true")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["rerank_aplicado"] is False
    assert corpo["rerank_motivo"] == "e5_indisponivel"
    ncs = [i["numero_controle"] for i in corpo["itens"]]
    assert ncs == ["A", "B"]                  # ordem original preservada
    assert all("rerank_score" not in i for i in corpo["itens"])


def test_rerank_off_mantem_ordem_e_sem_score(client, monkeypatch):
    cli = ClienteCapturador(por_termo={"microfone": [
        _hit("A", title="cadeira"),
        _hit("B", title="microfone"),
    ]}, total_por_termo=2)
    _patch_pncp(monkeypatch, cli)
    # sem rerank → não chama o e5; ordem intacta, sem score
    corpo = client.get("/descobrir?q=microfone&ordenacao=relevancia").json()
    assert corpo["rerank_aplicado"] is False
    assert corpo["rerank_motivo"] == "desligado"
    ncs = [i["numero_controle"] for i in corpo["itens"]]
    assert ncs == ["A", "B"]
    assert all("rerank_score" not in i for i in corpo["itens"])


def test_rerank_ignorado_quando_ordenacao_por_data(client, monkeypatch):
    # usuário escolheu ordenacao=-data (default) → re-rank NÃO aplica (respeita escolha)
    cli = ClienteCapturador(por_termo={"x": [_hit("A"), _hit("B")]}, total_por_termo=2)
    _patch_pncp(monkeypatch, cli)
    corpo = client.get("/descobrir?q=x&rerank=true").json()
    assert corpo["rerank_aplicado"] is False
    assert corpo["rerank_motivo"] == "ordenacao_explicita"


def test_rerank_ignorado_sem_termo_na_fonte_consulta(client, monkeypatch):
    # sem termo → fonte "consulta"/bulk; re-rank não toca essa fonte
    cli = ClienteBulkCapturador([_reg("BEM", "Aquisição de cadeiras")])
    _patch_pncp(monkeypatch, cli)
    corpo = client.get("/descobrir?rerank=true&ordenacao=relevancia").json()
    assert corpo["fonte"] == "consulta"
    assert corpo["rerank_aplicado"] is False
    assert corpo["rerank_motivo"] == "sem_termo"


# --------- hit malformado: 422 (não 500) e segurança cnpj/ano/seq ---------

def test_importar_hit_cnpj_malformado_da_422(client, con):
    """cnpj fora de ^\\d{14}$ (path traversal / letras) → 422, sem gravar pregão
    nem montar URL/diretório com o cnpj malicioso."""
    hit = _hit("NC-EVIL")
    hit["orgao_cnpj"] = "../../../etc"
    r = client.post("/descobrir/importar", json={"numero_controle": "NC-EVIL", "hit": hit})
    assert r.status_code == 422
    assert con.execute("SELECT COUNT(*) c FROM pregoes").fetchone()["c"] == 0


def test_importar_hit_ano_invalido_da_422(client, con):
    """ano/seq não-conversíveis para int → 422 (antes era 500 do ValueError)."""
    hit = _hit("NC-BAD")
    hit["ano"] = "abc"
    r = client.post("/descobrir/importar", json={"numero_controle": "NC-BAD", "hit": hit})
    assert r.status_code == 422
    assert con.execute("SELECT COUNT(*) c FROM pregoes").fetchone()["c"] == 0

    hit2 = _hit("NC-BAD2")
    hit2["numero_sequencial"] = "12.5"
    r2 = client.post("/descobrir/importar", json={"numero_controle": "NC-BAD2", "hit": hit2})
    assert r2.status_code == 422


def test_descoberta_pula_hit_malformado_sem_quebrar_lote(con):
    """Na descoberta agendada, um hit malformado é pulado (não derruba o lote
    nem grava pregão com cnpj/ano inválido)."""
    from app.services import descoberta

    busca_id = con.execute(
        "INSERT INTO buscas_salvas (nome, termos, ufs) VALUES ('b','x','SP')"
    ).lastrowid
    con.commit()

    bom = _hit("NC-OK")
    ruim = _hit("NC-RUIM")
    ruim["orgao_cnpj"] = "../evil"

    class ClienteMisto:
        def buscar(self, q="", **k):
            return {"items": [ruim, bom], "total": 2}

    r = descoberta.rodar_busca(con, busca_id, ClienteMisto(), enriquecer=False)
    ncs = [p["numero_controle"]
           for p in con.execute("SELECT numero_controle FROM pregoes")]
    assert ncs == ["NC-OK"]            # só o hit válido entrou
    assert r["novos"] == 1
