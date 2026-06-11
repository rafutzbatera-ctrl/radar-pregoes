"""M3 — extrator heurístico LOCAL (sem IA).

Edital sintético realista com seção de habilitação; valida requisitos,
categorias, páginas, dedupe, facultatividade, markdown e — crucial — que TODOS
os excertos passam no gate de citação (princípios 1 e 2: nunca inventa)."""
from app.services.extratores import heuristico
from app.services.habilitacao import verificar_citacao

EDITAL = [
    # página 1 — preâmbulo, sem exigências
    ("EDITAL DE PREGÃO ELETRÔNICO Nº 7/2026\n"
     "Objeto: aquisição de equipamentos de áudio e vídeo.\n"
     "Considerando a Lei 14.133/2021, a Administração torna público o certame.\n"
     "8. DA PROPOSTA\n"
     "8.1 A proposta deverá ter validade mínima de 60 (sessenta) dias, "
     "contados da data de sua apresentação."),
    # página 2 — seção de habilitação com vários documentos
    ("9. DA HABILITAÇÃO\n"
     "9.1 Para fins de habilitação, o licitante deverá apresentar os documentos "
     "a seguir relacionados.\n"
     "9.2 Certidão conjunta negativa de débitos relativos a tributos federais e "
     "à Dívida Ativa da União (RFB/PGFN).\n"
     "9.3 Certificado de Regularidade do FGTS (CRF), comprovando regularidade "
     "perante o Fundo de Garantia do Tempo de Serviço.\n"
     "9.4 Certidão Negativa de Débitos Trabalhistas (CNDT).\n"
     "9.5 Ato constitutivo, estatuto ou contrato social em vigor, devidamente "
     "registrado.\n"
     "9.6 Declaração de que não emprega menor de dezoito anos em trabalho "
     "noturno, nos termos do inciso XXXIII do art. 7º da Constituição.\n"
     "9.7 Atestado de capacidade técnica, comprovando aptidão para o "
     "fornecimento, emitido por pessoa jurídica de direito público ou privado.\n"
     "9.8 Balanço patrimonial do último exercício social, já exigível, que "
     "comprove a boa situação financeira da empresa.\n"
     "9.9 Certidão negativa de falência ou recuperação judicial expedida pelo "
     "distribuidor da sede do licitante."),
    # página 3 — outra exigência fiscal + uma facultativa
    ("9.10 Prova de regularidade para com a Fazenda Estadual, mediante "
     "apresentação de certidão relativa ao ICMS.\n"
     "9.11 A apresentação de garantia da proposta é facultativa, a critério do "
     "licitante.\n"
     "10. DAS DISPOSIÇÕES FINAIS\n"
     "10.1 Os casos omissos serão resolvidos pela autoridade competente."),
]


def _por_requisito(reqs):
    return {r.requisito: r for r in reqs}


def test_extrai_requisitos_e_categorias():
    reqs = heuristico.extrair(EDITAL)
    d = _por_requisito(reqs)

    assert "Certidão negativa de débitos federais (RFB/PGFN)" in d
    assert d["Certidão negativa de débitos federais (RFB/PGFN)"].categoria == "fiscal"
    assert "Certificado de regularidade do FGTS (CRF)" in d
    assert d["Certificado de regularidade do FGTS (CRF)"].categoria == "fiscal"
    assert "Certidão negativa de débitos trabalhistas (CNDT)" in d
    assert "Regularidade fiscal estadual" in d
    assert d["Regularidade fiscal estadual"].categoria == "fiscal"

    assert "Ato constitutivo / contrato social em vigor" in d
    assert d["Ato constitutivo / contrato social em vigor"].categoria == "juridica"
    assert "Declaração de que não emprega menor" in d
    assert d["Declaração de que não emprega menor"].categoria == "juridica"

    assert "Atestado de capacidade técnica" in d
    assert d["Atestado de capacidade técnica"].categoria == "tecnica"

    assert "Balanço patrimonial do último exercício" in d
    assert d["Balanço patrimonial do último exercício"].categoria == "economico_financeira"
    assert "Certidão negativa de falência" in d
    assert d["Certidão negativa de falência"].categoria == "economico_financeira"

    assert "Validade mínima da proposta" in d
    assert d["Validade mínima da proposta"].categoria == "proposta"


def test_paginas_corretas():
    d = _por_requisito(heuristico.extrair(EDITAL))
    # validade da proposta está na página 1 (seção 8)
    assert d["Validade mínima da proposta"].pagina == 1
    # documentos de habilitação na página 2
    assert d["Certificado de regularidade do FGTS (CRF)"].pagina == 2
    assert d["Atestado de capacidade técnica"].pagina == 2
    # ICMS na página 3
    assert d["Regularidade fiscal estadual"].pagina == 3


def test_todos_excertos_passam_no_gate():
    """Princípios 1 e 2: o excerto é cópia literal → o gate de citação aceita TODOS."""
    for r in heuristico.extrair(EDITAL):
        assert verificar_citacao(r.excerto, EDITAL), f"falhou no gate: {r.requisito!r}"


def test_dedupe_mesmo_requisito_uma_vez():
    paginas = [
        "9. DA HABILITAÇÃO\n"
        "9.1 Deverá apresentar Certificado de Regularidade do FGTS (CRF).\n"
        "9.2 Reiteramos: deverá comprovar regularidade do FGTS mediante o CRF.",
    ]
    reqs = heuristico.extrair(paginas)
    nomes = [r.requisito for r in reqs]
    assert nomes.count("Certificado de regularidade do FGTS (CRF)") == 1


def test_documento_sem_habilitacao_lista_vazia():
    paginas = [
        "EDITAL\nObjeto: compra de cadeiras.\nConsiderando a legislação vigente.",
        "Cronograma do certame e datas relevantes para os interessados.",
    ]
    assert heuristico.extrair(paginas) == []


def test_facultativo_marca_obrigatorio_false():
    d = _por_requisito(heuristico.extrair(EDITAL))
    assert d["Garantia (proposta/contratual)"].obrigatorio is False


def test_markdown_ainda_casa():
    """pymupdf4llm injeta **negrito** e # headings — a marcação não atrapalha."""
    paginas = [
        "# 9. DA HABILITAÇÃO\n"
        "**9.2** Deverá apresentar **Certidão Negativa de Débitos Trabalhistas "
        "(CNDT)** comprovando a regularidade trabalhista.",
    ]
    reqs = heuristico.extrair(paginas)
    nomes = [r.requisito for r in reqs]
    assert "Certidão negativa de débitos trabalhistas (CNDT)" in nomes
    # excerto sem os asteriscos, mas ainda passa no gate (normalização)
    cndt = next(r for r in reqs if r.requisito.startswith("Certidão negativa de débitos trab"))
    assert "*" not in cndt.excerto
    assert verificar_citacao(cndt.excerto, paginas)


def test_glossario_apos_habilitacao_nao_vira_requisito():
    """A região de habilitação tem FIM: um glossário/anexo depois do heading não
    pode dispensar o gatilho de exigência e gerar requisito-fantasma.

    A linha de glossário "FGTS: Fundo de Garantia..." casa o padrão do FGTS, mas
    é só uma definição — sem gatilho e FORA da região, não vira requisito. Só o
    requisito real (com gatilho, dentro da seção 9) entra na lista.
    """
    paginas = [
        "9. DA HABILITAÇÃO\n"
        "9.1 O licitante deverá apresentar o Certificado de Regularidade do "
        "FGTS (CRF) em vigor.\n"
        "ANEXO II — GLOSSÁRIO\n"
        "FGTS: Fundo de Garantia do Tempo de Serviço, sigla mencionada neste "
        "edital.",
    ]
    reqs = heuristico.extrair(paginas)
    nomes = [r.requisito for r in reqs]
    assert nomes == ["Certificado de regularidade do FGTS (CRF)"]
    assert nomes.count("Certificado de regularidade do FGTS (CRF)") == 1


def test_regiao_habilitacao_tem_prioridade_no_dedupe():
    """Mesmo requisito fora e dentro da seção: fica a ocorrência da habilitação."""
    paginas = [
        # menção fora da seção (considerandos), página 1
        "Considerando que o FGTS deve estar regular, a Administração exige "
        "comprovação adequada no momento oportuno.",
        # seção de habilitação propriamente dita, página 2
        "9. DA HABILITAÇÃO\n"
        "9.3 O licitante deverá apresentar o Certificado de Regularidade do "
        "FGTS (CRF) em vigor.",
    ]
    reqs = heuristico.extrair(paginas)
    crf = next(r for r in reqs if r.requisito == "Certificado de regularidade do FGTS (CRF)")
    assert crf.pagina == 2  # ficou a ocorrência da região de habilitação
