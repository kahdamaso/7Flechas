from datetime import date

import pytest

from app.importacao import importar
from app.models import Atendimento, Consulente, Entidade, Linha, Medium, Presenca, Sessao

from .conftest import FIXTURES


@pytest.fixture
def dados(app):
    importar([FIXTURES])


def test_todas_as_telas_abrem(client, dados):
    sessao = Sessao.query.filter_by(data=date(2026, 8, 2)).one()
    medium = Medium.query.first()
    consulente = Consulente.query.first()
    entidade = Entidade.query.first()
    at = sessao.atendimentos[0]
    urls = [
        "/", "/mediuns/", "/mediuns/?situacao=todos&grupo=Corrente&q=ana", "/mediuns/novo",
        f"/mediuns/{medium.id}", f"/mediuns/{medium.id}/editar",
        "/consulentes/", "/consulentes/?q=123", "/consulentes/novo",
        f"/consulentes/{consulente.id}", f"/consulentes/{consulente.id}/editar",
        "/entidades/", "/entidades/nova", f"/entidades/{entidade.id}/editar",
        "/sessoes/", "/sessoes/nova", f"/sessoes/{sessao.id}", f"/sessoes/{sessao.id}/editar",
        f"/sessoes/{sessao.id}/presenca", f"/sessoes/{sessao.id}/atendimentos/novo",
        f"/sessoes/{sessao.id}/atendimentos/{at.id}/editar",
    ]
    for url in urls:
        resp = client.get(url)
        assert resp.status_code == 200, url
    assert "Sultão das Matas" in client.get(f"/sessoes/{sessao.id}").get_data(as_text=True)


def test_crud_consulente(client, app):
    resp = client.post("/consulentes/novo", data={"nome": "Fulano Teste", "cpf": "529.982.247-25",
                                                   "telefone": "31 99999-0000", "cidade": "Betim"})
    assert resp.status_code == 302
    c = Consulente.query.filter_by(nome="Fulano Teste").one()
    assert c.cpf == "52998224725" and c.telefone == "31999990000"

    # CPF duplicado é recusado
    resp = client.post("/consulentes/novo", data={"nome": "Outro", "cpf": "52998224725"})
    assert resp.status_code == 200 and "CPF já cadastrado" in resp.get_data(as_text=True)

    client.post(f"/consulentes/{c.id}/editar", data={"nome": "Fulano Editado", "cpf": ""})
    assert db_get(Consulente, c.id).nome == "Fulano Editado"
    client.post(f"/consulentes/{c.id}/excluir")
    assert db_get(Consulente, c.id) is None


def test_crud_medium_com_entidades(client, app):
    caboclo = Linha.query.filter_by(nome="Caboclo").one()
    client.post("/entidades/nova", data={"nome": "Pena Dourada", "linha_id": caboclo.id})
    ent = Entidade.query.filter_by(nome="Pena Dourada").one()
    client.post("/mediuns/novo", data={"nome": "Médium Novo", "grupo": "Auxiliar", "ativo": "on",
                                       "entidades": [str(ent.id)]})
    m = Medium.query.filter_by(nome="Médium Novo").one()
    assert m.grupo == "Auxiliar" and [v.entidade.nome for v in m.entidades] == ["Pena Dourada"]

    client.post(f"/mediuns/{m.id}/editar", data={"nome": "Médium Novo", "grupo": "Corrente"})
    m = db_get(Medium, m.id)
    assert m.entidades == [] and m.ativo is False
    client.post(f"/mediuns/{m.id}/excluir")
    assert db_get(Medium, m.id) is None


def test_fluxo_sessao_presenca_atendimento(client, app):
    a = Medium(nome="Médium A", grupo="Corrente")
    b = Medium(nome="Médium B", grupo="Corrente")
    exu = Linha.query.filter_by(nome="Exu").one()
    tranca = Entidade(nome="Tranca Rua", linha=exu)
    from app.extensions import db
    db.session.add_all([a, b, tranca])
    db.session.commit()

    resp = client.post("/sessoes/nova", data={"data": "2026-10-23", "tipo": "Gira de Exu"})
    sessao = Sessao.query.filter_by(data=date(2026, 10, 23)).one()
    assert resp.headers["Location"].endswith(f"/sessoes/{sessao.id}/presenca")

    client.post(f"/sessoes/{sessao.id}/presenca", data={
        f"status_{a.id}": "presente", f"status_{b.id}": "falta", f"just_{b.id}": "Doente"})
    pres = {p.medium.nome: p for p in Presenca.query.filter_by(sessao_id=sessao.id)}
    assert pres["Médium A"].presente and not pres["Médium B"].presente
    assert pres["Médium B"].justificativa == "Doente"

    # consulente novo digitado pelo nome é cadastrado na hora
    client.post(f"/sessoes/{sessao.id}/atendimentos/novo", data={
        "categoria": "Consulente", "consulente": "Visitante Novo", "retorno": "Tranca Rua",
        f"ent_{exu.id}": str(tranca.id), f"med_{exu.id}": str(a.id),
    })
    at = Atendimento.query.filter_by(sessao_id=sessao.id).one()
    assert at.consulente.nome == "Visitante Novo" and at.retorno == "Tranca Rua"
    [man] = at.manifestacoes
    assert man.entidade.nome == "Tranca Rua" and man.medium_responsavel.nome == "Médium A"

    # edição: troca para "Geral" e seleciona o consulente existente pelo "(#id)"
    client.post(f"/sessoes/{sessao.id}/atendimentos/{at.id}/editar", data={
        "categoria": "Consulente", "consulente": f"Visitante Novo (#{at.consulente_id})",
        f"ent_{exu.id}": "geral",
    })
    at = db_get(Atendimento, at.id)
    assert Consulente.query.filter_by(nome="Visitante Novo").count() == 1
    assert at.manifestacoes[0].geral and at.manifestacoes[0].medium_responsavel is None

    # atendimento sem pessoa é recusado
    resp = client.post(f"/sessoes/{sessao.id}/atendimentos/novo", data={"categoria": "Corrente"})
    assert resp.status_code == 200
    assert Atendimento.query.filter_by(sessao_id=sessao.id).count() == 1

    client.post(f"/sessoes/{sessao.id}/excluir")
    assert Atendimento.query.count() == 0 and Presenca.query.count() == 0


def db_get(modelo, id):
    from app.extensions import db
    db.session.expire_all()
    return db.session.get(modelo, id)
