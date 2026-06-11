"""M3 — gate de citação: derruba excerto adulterado; lista vazia é aceita;
status do usuário sobrevive à re-extração."""
from app.services.habilitacao import (RequisitoHabilitacao, aplicar_gate,
                                      persistir, verificar_citacao)

PAGINAS = [
    "EDITAL DE PREGÃO ELETRÔNICO Nº 1/2026\nObjeto: aquisição de equipamentos.",
    ("9. DA HABILITAÇÃO\n9.1 A proposta deverá ter validade mínima de 60 "
     "(sessenta) dias, contados da data de sua apresentação.\n"
     "9.2 Prova de regularidade relativa ao Fundo de Garantia do Tempo de "
     "Serviço (FGTS), mediante apresentação do Certificado de Regularidade "
     "do FGTS — CRF."),
]


def test_citacao_literal_passa():
    assert verificar_citacao(
        "A proposta deverá ter validade mínima de 60 (sessenta) dias", PAGINAS
    )


def test_normalizacao_caixa_e_espacos():
    assert verificar_citacao(
        "  a PROPOSTA   deverá ter\nvalidade mínima de 60 (sessenta) dias ", PAGINAS
    )


def test_excerto_adulterado_cai():
    """Teste exigido no CLAUDE.md M3: gate derruba excerto adulterado."""
    assert not verificar_citacao(
        "A proposta deverá ter validade mínima de 90 (noventa) dias", PAGINAS
    )


def test_excerto_vazio_cai():
    assert not verificar_citacao("   ", PAGINAS)


def test_gate_nao_funde_tokens_por_negrito():
    """Marcação só some em fronteira de token e vira espaço: `60**dias**` no doc
    casa o excerto correto `60 dias`, mas rejeita o fabricado `60dias`."""
    assert not verificar_citacao("60dias", ["prazo de 60**dias** corridos"])
    assert verificar_citacao("60 dias", ["prazo de 60**dias** corridos"])


def test_gate_underscore_nao_funde_tokens():
    """`a_b_c` no doc não pode casar o fabricado `abc` (underscore = separador)."""
    assert not verificar_citacao("abc", ["a_b_c"])


def _requisitos():
    return [
        RequisitoHabilitacao(
            requisito="Proposta com validade mínima de 60 dias",
            categoria="proposta", obrigatorio=True, pagina=2,
            excerto="A proposta deverá ter validade mínima de 60 (sessenta) dias, "
                    "contados da data de sua apresentação.",
        ),
        RequisitoHabilitacao(
            requisito="Requisito inventado pelo LLM",
            categoria="outros", obrigatorio=False, pagina=2,
            excerto="Exige-se garantia contratual de 10% do valor.",  # não está no PDF
        ),
    ]


def test_gate_marca_verificada_por_requisito():
    saida = aplicar_gate(_requisitos(), PAGINAS)
    assert saida[0]["verificada"] is True
    assert saida[1]["verificada"] is False  # nunca descartado em silêncio


def test_lista_vazia_aceita(con):
    """CLAUDE.md M3: lista vazia é permitida (edital sem seção de habilitação)."""
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,1,'NC-1')")
    pregao_id = con.execute("SELECT id FROM pregoes").fetchone()["id"]
    assert persistir(con, pregao_id, []) == 0
    assert con.execute("SELECT COUNT(*) c FROM habilitacao").fetchone()["c"] == 0


def test_persistir_preserva_status_do_usuario(con):
    con.execute("INSERT INTO pregoes (cnpj, ano, seq, numero_controle) "
                "VALUES ('1',2026,1,'NC-1')")
    pregao_id = con.execute("SELECT id FROM pregoes").fetchone()["id"]
    verificados = aplicar_gate(_requisitos(), PAGINAS)
    persistir(con, pregao_id, verificados)
    con.execute(
        "UPDATE habilitacao SET status_usuario='ok' "
        "WHERE requisito='Proposta com validade mínima de 60 dias'"
    )
    con.commit()
    # re-extração (ex.: re-sincronizar) não pode zerar o checklist do usuário
    persistir(con, pregao_id, verificados)
    ln = con.execute(
        "SELECT status_usuario FROM habilitacao "
        "WHERE requisito='Proposta com validade mínima de 60 dias'"
    ).fetchone()
    assert ln["status_usuario"] == "ok"
