from datetime import date

from app.importacao import importar
from app.models import (
    Atendimento,
    Consulente,
    Entidade,
    Medium,
    Presenca,
    Sessao,
)
from app.utils import normalizar_cpf

from .conftest import FIXTURES


def _manifestacoes(nome):
    at = next(a for a in Atendimento.query.all() if a.pessoa_nome == nome)
    return {m.linha.nome: m for m in at.manifestacoes}


def test_normalizar_cpf():
    assert normalizar_cpf("123.456.789-09") == "12345678909"
    assert normalizar_cpf("1234567890") == "01234567890"  # zero à esquerda perdido no Excel
    assert normalizar_cpf("111.111.111-11") is None
    assert normalizar_cpf("abc") is None


def test_importa_consulentes(app):
    rel = importar([FIXTURES / "TUC7FJ_CONSULENTE.csv"])
    maria = Consulente.query.filter_by(cpf="12345678909").one()
    assert maria.nome == "Maria de Teste Souza"
    assert maria.cidade == "Belo Horizonte" and maria.uf == "MG"
    assert maria.data_nascimento == date(1980, 3, 5)
    assert maria.telefone == "31988887777"
    assert maria.observacoes == "voltou"  # linha duplicada completou o cadastro
    joao = Consulente.query.filter_by(nome="João Exemplo").one()  # arquivo em cp1252
    assert joao.cpf == "01234567890" and joao.telefone == "3133334444"
    assert joao.data_nascimento is None
    assert Consulente.query.filter_by(nome="CPF Ruim da Silva").one().cpf is None
    assert Consulente.query.count() == 3
    assert any("CPF inválido" in a for a in rel.avisos)
    assert any("31/02/1990" in a for a in rel.avisos)


def test_importa_retorno_mediuns(app):
    importar([FIXTURES / "TUC7FJ_RETORNO_MEDIUNS.csv"])
    ana = Medium.query.filter_by(nome="Ana Ficticia Lima").one()
    assert sorted(v.entidade.nome for v in ana.entidades) == [
        "Maria Padilha", "Pai Joaquim", "Pena Branca", "Tranca Rua"
    ]
    bruno = Medium.query.filter_by(nome="Bruno Exemplo Rocha").one()
    assert sorted(v.entidade.nome for v in bruno.entidades) == ["Marabô", "Pena Verde", "Ubirajara"]
    carla = Medium.query.filter_by(nome="Carla Modelo").one()
    assert carla.grupo == "Auxiliar"
    assert [v.entidade.nome for v in carla.entidades] == ["Cigana Rosa"]  # "x" ignorado


def test_importacao_completa(app):
    rel = importar([FIXTURES])
    sessao = Sessao.query.filter_by(data=date(2026, 8, 2)).one()
    assert len(sessao.atendimentos) == 5

    # célula com nome do médium ('Ana') -> médium + a entidade dele naquela linha
    m = _manifestacoes("Bruno Teste Dias")["Exu"]
    assert m.medium_responsavel.nome == "Ana Ficticia Lima"
    assert m.entidade.nome == "Tranca Rua"

    # célula com nome da entidade -> entidade + único médium que a trabalha
    m = _manifestacoes("Davi Colaborador")
    assert m["Caboclo"].entidade.nome == "Pena Branca"
    assert m["Caboclo"].medium_responsavel.nome == "Ana Ficticia Lima"
    # 'Bruno' é ambíguo (dois médiuns): mantém só o texto
    assert m["Exu"].entidade is None and m["Exu"].medium_responsavel is None
    assert m["Exu"].descricao == "Bruno"
    assert any("'Bruno'" in a for a in rel.avisos)

    maria = _manifestacoes("Maria de Teste Souza")
    assert maria["Caboclo"].entidade.nome == "Sultão das Matas"  # correção de digitação
    assert maria["Preto Velho"].geral is True
    assert maria["Exu"].entidade.nome == "Zé Caveira"
    assert maria["Pombo Gira"].entidade.nome == "Maria Quitéria"
    # consulente da sessão é o mesmo do cadastro, não um duplicado
    assert Consulente.query.filter_by(nome_chave="maria de teste souza").count() == 1

    nova = Atendimento.query.join(Consulente).filter(Consulente.nome == "Pessoa Nova").one()
    assert nova.parentesco == "CRIANÇA VAI COM MARIA"
    assert _manifestacoes("Pessoa Nova")["Caboclo"].medium_responsavel.nome == "Bruno Exemplo Rocha"

    ana_at = _manifestacoes("Ana Ficticia Lima")
    assert ana_at["7 Flechas"].descricao == "Orientação Espiritual"
    assert Atendimento.query.filter_by(medium_id=Medium.query.filter_by(
        nome="Bruno Teste Dias").one().id).one().retorno == "Tranca Rua"


def test_presenca(app):
    rel = importar([FIXTURES])
    bruno_e = Medium.query.filter_by(nome="Bruno Exemplo Rocha").one()
    s1 = Sessao.query.filter_by(data=date(2026, 8, 2)).one()
    s2 = Sessao.query.filter_by(data=date(2026, 8, 16)).one()
    # planilha de presença prevalece sobre a presença deduzida da sessão
    assert Presenca.query.filter_by(sessao=s1, medium=bruno_e).one().presente is False
    p = Presenca.query.filter_by(sessao=s2, medium=bruno_e).one()
    assert p.presente is False and p.justificativa == "Falta justificada"
    davi = Medium.query.filter_by(nome="Davi Colaborador").one()
    assert davi.grupo == "Colaborador"
    assert Presenca.query.filter_by(sessao=s1, medium=davi).one().presente
    assert any("'?'" in a for a in rel.avisos)


def test_reimportacao_idempotente(app):
    importar([FIXTURES])
    totais = (Consulente.query.count(), Medium.query.count(), Entidade.query.count(),
              Atendimento.query.count())
    rel = importar([FIXTURES])
    assert any("já tem atendimentos" in a for a in rel.avisos)
    assert totais == (Consulente.query.count(), Medium.query.count(), Entidade.query.count(),
                      Atendimento.query.count())
    importar([FIXTURES], substituir=True)
    assert Atendimento.query.count() == totais[3]
