"""Classificador aquisição-aware "só compra de bens" — casos de dor + métricas.

Dois blocos:
1. Casos unitários explícitos da lista de dor do dono (devem SAIR / devem FICAR).
2. Métricas sobre o corpus REAL rotulado (tests/fixtures/corpus_rotulado.json,
   97 objetos): recall de bens (não matar compra de bens — sagrado) e taxa de
   remoção de serviço+concessão. Em falha, imprime os objetos divergentes.
"""
import json
import pathlib

from app.services.classificador import e_compra_de_bens, normalizar

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


# --------- normalização ---------

def test_normalizar_minuscula_sem_acento_espacos_colapsados():
    assert normalizar("AQUISIÇÃO  DE\n MEDICAMENTOS") == "aquisicao de medicamentos"
    assert normalizar("  Pré-qualificação ") == "pre-qualificacao"
    assert normalizar(None) == ""


# --------- casos de dor do dono: o que DEVE SAIR (False) ---------

def test_credenciamento_sai():
    assert e_compra_de_bens("Credenciamento de veículos 100% elétricos") is False


def test_prestacao_de_servicos_sai():
    assert e_compra_de_bens(
        "Prestação de serviços de limpeza e conservação do prédio"
    ) is False


def test_pre_qualificacao_sai():
    assert e_compra_de_bens(
        "Pré-qualificação de empresas para futura contratação"
    ) is False


def test_contratacao_de_clinica_internacao_sai():
    # clínica/internação cai por "prestacao de servico" sem indicador de bens
    assert e_compra_de_bens(
        "Contratação de Clínica para prestação de serviços de internação hospitalar"
    ) is False


def test_concessao_de_uso_sai():
    assert e_compra_de_bens(
        "Concessão de Uso de Espaço Público para exploração comercial de lojas"
    ) is False


def test_srp_de_servico_sai():
    # registro de preço NÃO é especial: SRP de serviço sai na mesma régua
    assert e_compra_de_bens(
        "Registro de preços para prestação de serviços de vigilância armada"
    ) is False


# --------- casos de dor do dono: o que DEVE FICAR (True) ---------

def test_srp_de_aquisicao_de_uniformes_fica():
    # registro de preço de AQUISIÇÃO fica na mesma régua
    assert e_compra_de_bens(
        "Registro de preços para aquisição de uniformes"
    ) is True


def test_aquisicao_de_ar_condicionado_fica():
    assert e_compra_de_bens(
        "Contratação de empresa para aquisição de ar-condicionado"
    ) is True


def test_aquisicao_de_notebooks_fica():
    assert e_compra_de_bens("Aquisição de notebooks") is True


# --------- métricas sobre o corpus real rotulado (gabarito versionado) ---------

def _carregar_corpus():
    corpus = json.loads((FIXTURES / "corpus_rotulado.json").read_text(encoding="utf-8"))
    assert len(corpus) == 97, f"corpus deve ter 97 objetos, tem {len(corpus)}"
    for r in corpus:
        assert r["label"] in ("bens", "servico", "concessao"), r["label"]
    return corpus


def test_recall_bens_nao_mata_compra_de_bens():
    """Sagrado: dos label=bens, ≥ 0.90 devem ser e_compra_de_bens=True.

    Exceção aceitável (decisão do dono): credenciamento-para-bens, que sai pelo
    hard_exclude. Falso-positivo em bens (matar compra) é o pior erro.
    """
    corpus = _carregar_corpus()
    bens = [r for r in corpus if r["label"] == "bens"]
    capturados = [r for r in bens if e_compra_de_bens(r["objeto"])]
    perdidos = [r["objeto"] for r in bens if not e_compra_de_bens(r["objeto"])]
    recall = len(capturados) / len(bens)
    assert recall >= 0.90, (
        f"recall_bens={recall:.3f} < 0.90 — compra de bens sendo MORTA.\n"
        f"objetos perdidos ({len(perdidos)}):\n" + "\n".join(f"  - {o}" for o in perdidos)
    )


def test_remocao_servico_concessao():
    """Dos label∈{servico,concessao}, ≥ 0.75 devem ser e_compra_de_bens=False."""
    corpus = _carregar_corpus()
    ruido = [r for r in corpus if r["label"] in ("servico", "concessao")]
    removidos = [r for r in ruido if not e_compra_de_bens(r["objeto"])]
    vazaram = [r["objeto"] for r in ruido if e_compra_de_bens(r["objeto"])]
    taxa = len(removidos) / len(ruido)
    assert taxa >= 0.75, (
        f"remocao_servico_concessao={taxa:.3f} < 0.75 — muito ruído passando.\n"
        f"objetos que vazaram ({len(vazaram)}):\n" + "\n".join(f"  - {o}" for o in vazaram)
    )
