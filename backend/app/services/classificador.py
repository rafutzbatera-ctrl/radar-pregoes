"""Classificador aquisição-aware: "só compra de bens" pelo TEXTO do objeto.

O filtro "Só compra de bens" do front já restringe as MODALIDADES na origem
(Concorrências, Pregões, Dispensa), mas dentro dessas modalidades ainda vaza
serviço/concessão: credenciamento, prestação de serviços, registro de preço de
serviço, concessão de uso, contratação de clínica/operadora etc. Este módulo
classifica o TEXTO do objeto (título + descrição) com uma régua de termos,
sintetizada e validada contra um corpus REAL rotulado de 97 objetos do PNCP
(gabarito em tests/fixtures/corpus_rotulado.json).

Regra (ordem importa):
  1. normaliza (minúsculas, sem acento, espaços colapsados);
  2. se casa algum HARD_EXCLUDE → False (concessão/credenciamento/leilão/
     publicidade etc. são 100% serviço-concessão nestes dados; nunca aparecem
     em compra de bens — derrubam sempre, mesmo que o texto também cite
     "aquisição", p.ex. credenciamento-para-bens, exclusão aceita pelo dono);
  3. senão, se casa algum SERVICO e NÃO casa nenhum BENS → False;
  4. senão → True.

Princípio sagrado: o pior erro é matar compra de bens (falso-positivo de
exclusão). Por isso a lista BENS (override "aquisic", gêneros, medicamento,
peças) protege a captura mesmo em objetos mistos (peças + mão de obra).

Decisão do dono: registro de preço NÃO é tratado especial — entra na mesma
régua (SRP de aquisição FICA via "aquisic"; SRP de serviço SAI via SERVICO).
"""
import re
import unicodedata

# Hard-exclude: termos que, sozinhos, caracterizam serviço/concessão sem
# exceção nestes dados — derrubam ANTES de qualquer override de bens.
HARD_EXCLUDE = [
    "concessao",
    "credenciamento",
    "credenciar",
    "permissao de uso",
    "comodato",
    "chamamento publico",
    "manejo florestal",
    "leilao",
    "pre-qualificacao",
    "pre qualificacao",
    "agencia de propaganda",
    "agencia de publicidade",
    "publicidade e propaganda",
    "servicos de publicidade",
]

# Serviço: derruba só quando NÃO há indicador de bens (regra 3).
SERVICO = [
    "prestacao de servico",
    "prestacao dos servico",
    "prestar servico",
    "servicos bancarios",
    "servicos financeiros",
    "servicos medicos",
    "servicos de saude",
    "plano de saude",
    "operadora de plano",
    "assistencia medica",
    "instituicao financeira",
    "folha de pagamento",
    "folha de salario",
    "consultoria",
    "assessoramento",
    "empresa especializada de engenharia",
    "empresa de engenharia",
    "obras",
    "obra -",
    "construcao",
    "reforma",
    "implantacao",
    "execucao de",
    "manutencao",
    "projeto executivo",
    "projeto basico",
    "projeto de",
    "licenciamento de uso",
    "software",
    "cenografia",
    "ornamentacao",
    "ambientacao decorativa",
    "limpeza",
    "asseio",
    "conservacao do",
    "manutencao preventiva",
    "exploracao comercial",
    "exploracao de produtos",
    "acesso a internet",
    "servicos de acesso",
    "transmissao em radio",
    "streaming",
    "veiculacao",
    "regime de locacao",
    "locacao de",
    "rastreio",
    "monitoramento",
    "telemetria",
    "exames laboratoriais",
    "instrutor de",
]
# Nota (13/06/2026): "manutencao", "obras", "implantacao", "execucao de" são
# amplos DE PROPÓSITO — só derrubam quando NÃO há override de bens, então
# "aquisição de peças para manutenção" / "...para obras" seguem MANTIDOS via
# "aquisic". Apertam o vazamento de serviço puro (manutenção de balança, obras
# de contenção, implantação de campo, execução de melhorias) sem matar compra.

# Bens: override que protege a precisão sagrada (não matar compra de bens).
BENS = [
    "aquisic",
    "compra de",
    "genero aliment",
    "generos aliment",
    "medicamento",
    "recarga",
    "pecas e acessorios",
    "pecas e materiais",
    "materiais de construcao",
    "material de construcao",
]

# múltiplos espaços/quebras → um espaço só
_ESPACOS = re.compile(r"\s+")


def normalizar(texto: str) -> str:
    """Minúsculas, sem acento (NFD + remove Mn) e espaços colapsados."""
    semacento = "".join(
        c for c in unicodedata.normalize("NFD", texto or "")
        if unicodedata.category(c) != "Mn"
    )
    return _ESPACOS.sub(" ", semacento.lower()).strip()


def _casa_algum(texto_norm: str, termos: list[str]) -> bool:
    return any(t in texto_norm for t in termos)


def e_compra_de_bens(texto: str) -> bool:
    """True se o objeto é compra de bens; False se serviço/concessão.

    Régua validada em corpus real (97 objetos): recall de bens ≥ 0,90,
    remoção de serviço+concessão ≥ 0,75.
    """
    t = normalizar(texto)
    if not t:
        return False
    if _casa_algum(t, HARD_EXCLUDE):
        return False
    if _casa_algum(t, SERVICO) and not _casa_algum(t, BENS):
        return False
    return True
