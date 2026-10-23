"""Regras da gira (Fase 2) com dados fictícios."""

from datetime import date, timedelta

import pytest

from app import gira as regras
from app.extensions import db
from app.models import (
    Conversa,
    Entidade,
    Gira,
    Linha,
    Parentesco,
    PedidoSeteFlechas,
    Pessoa,
    Presenca,
    Retorno,
)

from .conftest import recarregar

SEXTA = date(2026, 10, 30)
QUARTA = date(2026, 10, 28)
RESP = "Secretaria"


def _linha(nome):
    return Linha.query.filter_by(nome=nome).one()


def _pessoa(nome, categoria="Consulente", incorpora=False):
    p = Pessoa(nome=nome, categoria=categoria, incorpora=incorpora)
    db.session.add(p)
    db.session.flush()
    return p


@pytest.fixture
def casa(app):
    """Médiuns, entidades e consulentes de uma casa fictícia."""
    c = {}
    c["igor"] = _pessoa("Igor Chefe", "Corrente", True)
    c["ana"] = _pessoa("Ana Medium", "Corrente", True)
    c["bia"] = _pessoa("Bia Medium", "Corrente", True)
    c["carlos"] = _pessoa("Carlos Faltou", "Corrente", True)
    c["leo"] = _pessoa("Leo Corrente", "Corrente", True)
    c["rui"] = _pessoa("Rui Auxiliar", "Auxiliar")
    c["joao"] = _pessoa("Joao Consulente")
    c["maria"] = _pessoa("Maria Consulente")
    caboclo, exu = _linha("Caboclo"), _linha("Exu")
    for chave_ent, medium, linha, nome in [
        ("sete", "igor", caboclo, "7 Flechas"), ("tranca", "igor", exu, "Tranca Rua"),
        ("jurema", "ana", caboclo, "Jurema"), ("exu_bia", "bia", exu, None),
        ("pena", "carlos", caboclo, "Pena Branca"),
    ]:
        c[chave_ent] = Entidade(medium=c[medium], linha=linha, nome=nome)
        db.session.add(c[chave_ent])
    Parentesco.criar(c["joao"], c["ana"], "Cônjuge/Namorado(a)")
    c["gira"] = Gira(data=SEXTA, tipo="Sexta")
    db.session.add(c["gira"])
    db.session.commit()
    for nome in ("igor", "ana", "bia"):
        regras.marcar_presenca(c["gira"], c[nome], True, RESP)
    regras.marcar_presenca(c["gira"], c["carlos"], False, RESP)
    return c


def _inscrever(c, nome, linhas=(), pedidos=(), gira=None):
    insc, _ = regras.inscrever(gira or c["gira"], c[nome], [_linha(l).id for l in linhas],
                               list(pedidos), RESP)
    return insc


def test_tipo_sugerido_pelo_dia():
    assert regras.tipo_sugerido(SEXTA) == "Sexta"
    assert regras.tipo_sugerido(QUARTA) == "Quarta"
    assert regras.tipo_sugerido(date(2026, 11, 1)) == "Especial"


def test_entidades_em_terra_so_de_quem_esta_presente(casa):
    em_terra = {e.rotulo for e in regras.entidades_em_terra(casa["gira"])}
    assert em_terra == {"7 Flechas", "Tranca Rua", "Jurema", "Exu de Bia"}


def test_quarta_so_auxiliar_e_corrente(casa):
    quarta = Gira(data=QUARTA, tipo="Quarta")
    db.session.add(quarta)
    db.session.commit()
    with pytest.raises(regras.ErroGira, match="quarta"):
        _inscrever(casa, "joao", gira=quarta)
    assert _inscrever(casa, "rui", ["Exu"], gira=quarta).categoria == "Auxiliar"


def test_fila_ordem_e_bloqueio_por_parentesco(casa):
    joao = _inscrever(casa, "joao")
    maria = _inscrever(casa, "maria")
    rui = _inscrever(casa, "rui", ["Exu"])          # auxiliar: só a linha escolhida
    leo = _inscrever(casa, "leo", ["Caboclo"])       # chegou por último, mas incorpora
    assert joao.todas_linhas and not rui.todas_linhas

    s = regras.sugestoes(casa["gira"], casa["jurema"])
    assert [i.pessoa.nome for i in s.fila] == ["Leo Corrente", "Maria Consulente"]
    assert [(i.pessoa.nome, m) for i, m in s.bloqueados] == [("Joao Consulente", "parente de Ana")]

    s = regras.sugestoes(casa["gira"], casa["exu_bia"])
    assert [i.pessoa.nome for i in s.fila] == ["Joao Consulente", "Maria Consulente", "Rui Auxiliar"]
    # o próprio médium não aparece na fila das suas entidades
    _inscrever(casa, "bia", ["Exu"])
    assert "Bia Medium" not in [i.pessoa.nome for i in regras.sugestoes(casa["gira"], casa["exu_bia"]).fila]
    assert leo  # usado acima


def test_chamar_e_encerrar(casa):
    joao, maria = _inscrever(casa, "joao"), _inscrever(casa, "maria")
    g = casa["gira"]
    with pytest.raises(regras.ErroGira, match="parente"):
        regras.chamar(g, casa["jurema"], joao, RESP)
    conversa = regras.chamar(g, casa["jurema"], maria, RESP)
    assert conversa.situacao == "chamado"
    # mesma entidade ocupada / mesma pessoa ocupada
    with pytest.raises(regras.ErroGira, match="já está atendendo"):
        regras.chamar(g, casa["jurema"], joao, RESP, liberacao_parentesco="teste")
    with pytest.raises(regras.ErroGira, match="já está conversando"):
        regras.chamar(g, casa["sete"], maria, RESP)
    # quem está em atendimento não aparece em outras filas
    assert maria not in regras.sugestoes(g, casa["sete"]).fila

    regras.encerrar(conversa, "atendido", RESP)
    with pytest.raises(regras.ErroGira, match="já foi encerrada"):
        regras.encerrar(conversa, "atendido", RESP)
    # já passou na linha de Caboclo: sai da fila de Caboclo, continua na de Exu
    assert maria not in regras.sugestoes(g, casa["sete"]).fila
    assert maria in regras.sugestoes(g, casa["exu_bia"]).fila

    # parentesco liberado manualmente fica registrado
    liberada = regras.chamar(g, casa["jurema"], joao, RESP, liberacao_parentesco="Liberado pelo Sete Flechas")
    assert liberada.liberacao_parentesco == "Liberado pelo Sete Flechas"


def test_medium_ausente_nao_atende(casa):
    maria = _inscrever(casa, "maria")
    with pytest.raises(regras.ErroGira, match="não está marcado"):
        regras.chamar(casa["gira"], casa["pena"], maria, RESP)


def test_retorno_do_pedido_ate_a_conclusao(casa):
    g = casa["gira"]
    maria = _inscrever(casa, "maria")
    conversa = regras.chamar(g, casa["tranca"], maria, RESP)
    regras.definir_cambone(g, casa["tranca"], casa["rui"])
    regras.encerrar(conversa, "atendido", RESP, retorno_em=SEXTA + timedelta(days=7),
                    retorno_obs="trazer vela")
    retorno = Retorno.query.one()
    assert retorno.situacao == "pendente" and retorno.entidade == casa["tranca"]
    assert retorno.observacao == "trazer vela" and retorno.pessoa == casa["maria"]

    # próxima gira: o retorno aparece primeiro, mesmo ela já tendo passado em Exu antes
    proxima = Gira(data=SEXTA + timedelta(days=7), tipo="Sexta")
    db.session.add(proxima)
    db.session.commit()
    regras.marcar_presenca(proxima, casa["igor"], True, RESP)
    assert regras.retornos_previstos(proxima) == [retorno]
    insc = _inscrever(casa, "maria", gira=proxima)
    s = regras.sugestoes(proxima, casa["tranca"])
    assert [i for i, _ in s.retornos] == [insc] and insc not in s.fila

    volta = regras.chamar(proxima, casa["tranca"], insc, RESP)
    assert volta.retorno == retorno
    regras.encerrar(volta, "atendido", RESP)
    assert recarregar(Retorno, retorno.id).situacao == "concluido"


def test_retorno_com_medium_ausente_continua_pendente(casa):
    g = casa["gira"]
    maria = _inscrever(casa, "maria")
    regras.encerrar(regras.chamar(g, casa["jurema"], maria, RESP), "atendido", RESP,
                    retorno_em=SEXTA + timedelta(days=7))
    proxima = Gira(data=SEXTA + timedelta(days=7), tipo="Sexta")
    db.session.add(proxima)
    db.session.commit()
    regras.marcar_presenca(proxima, casa["ana"], False, RESP)
    assert casa["jurema"] not in regras.entidades_em_terra(proxima)
    assert Retorno.query.one().situacao == "pendente"


def test_pedidos_ao_sete_flechas(casa):
    g = casa["gira"]
    insc = _inscrever(casa, "maria", pedidos=[("Orientação espiritual", None),
                                              ("Autorização para entidade", casa["exu_bia"].id)])
    s = regras.sugestoes(g, casa["sete"])
    assert [i for i, _ in s.sete_flechas] == [insc]

    conversa = regras.chamar(g, casa["sete"], insc, RESP)
    autorizacao = PedidoSeteFlechas.query.filter_by(tipo="Autorização para entidade").one()
    regras.decidir_autorizacao(autorizacao, True, RESP)
    regras.encerrar(conversa, "atendido", RESP)
    orientacao = PedidoSeteFlechas.query.filter_by(tipo="Orientação espiritual").one()
    assert orientacao.situacao == "atendido" and autorizacao.situacao == "autorizado"

    s = regras.sugestoes(g, casa["exu_bia"])
    assert [i for i, _ in s.autorizados] == [insc]


def test_recusa_e_ausencia(casa):
    g = casa["gira"]
    joao, maria = _inscrever(casa, "joao"), _inscrever(casa, "maria")
    regras.recusar_linha(g, joao, _linha("Exu"), RESP)
    assert joao not in regras.sugestoes(g, casa["exu_bia"]).fila
    # não estava quando chamado: volta para o fim da fila
    regras.encerrar(regras.chamar(g, casa["exu_bia"], maria, RESP), "ausente", RESP)
    _inscrever(casa, "rui", ["Exu"])
    assert [i.pessoa.nome for i in regras.sugestoes(g, casa["exu_bia"]).fila] == [
        "Rui Auxiliar", "Maria Consulente"]


def test_chamada_sim_nao_e_limpar(casa):
    g = casa["gira"]
    regras.marcar_presenca(g, casa["leo"], True, RESP)
    regras.marcar_presenca(g, casa["leo"], False, RESP)
    assert Presenca.query.filter_by(gira_id=g.id, pessoa_id=casa["leo"].id).one().presente is False
    regras.marcar_presenca(g, casa["leo"], None, RESP)
    assert Presenca.query.filter_by(gira_id=g.id, pessoa_id=casa["leo"].id).first() is None


# --- telas -------------------------------------------------------------------


def test_fluxo_completo_pelas_telas(client, casa):
    g = casa["gira"]
    gid = g.id
    for url in ["/giras/", "/giras/nova", f"/giras/{gid}", f"/giras/{gid}/editar", f"/giras/{gid}/chamada",
                f"/giras/{gid}/inscricao", f"/giras/{gid}/atendimento", f"/giras/{gid}/mapa", "/retornos/",
                "/retornos/?filtro=atrasados", "/"]:
        assert client.get(url).status_code == 200, url

    # chamada pelo toque (fetch)
    resp = client.post(f"/giras/{gid}/chamada/{casa['leo'].id}", data={"presente": "sim"},
                       headers={"X-Requested-With": "fetch"})
    assert resp.json == {"ok": True, "presente": "sim"}

    # inscrição com alerta de parentesco
    pagina = client.get(f"/giras/{gid}/inscricao/{casa['joao'].id}").get_data(as_text=True)
    assert "Parentes na casa" in pagina and "em terra" in pagina
    client.post(f"/giras/{gid}/inscricao/{casa['joao'].id}", data={"pedidos": ["Consagrar pano"]})
    client.post(f"/giras/{gid}/inscricao/{casa['leo'].id}", data={"linhas": [str(_linha("Caboclo").id)]})
    assert "Joao Consulente" in client.get(f"/giras/{gid}/inscricao").get_data(as_text=True)

    # painel da entidade: sugere, chama, encerra com retorno
    ent = casa["sete"]
    pagina = client.get(f"/giras/{gid}/entidade/{ent.id}").get_data(as_text=True)
    assert "Pedidos ao Sete Flechas" in pagina and "Joao Consulente" in pagina
    insc_joao = next(i for i in recarregar(Gira, gid).inscricoes if i.pessoa_id == casa["joao"].id)
    client.post(f"/giras/{gid}/entidade/{ent.id}/cambone", data={"cambone_id": casa["rui"].id})
    client.post(f"/giras/{gid}/entidade/{ent.id}/chamar", data={"inscricao_id": insc_joao.id})
    conversa = Conversa.query.filter_by(situacao="chamado").one()
    assert conversa.cambone == casa["rui"] and conversa.registrado_por == "Secretaria"
    assert "Conversando agora" in client.get(f"/giras/{gid}/entidade/{ent.id}").get_data(as_text=True)
    client.post(f"/giras/{gid}/conversas/{conversa.id}/encerrar", data={
        "situacao": "atendido", "teve_retorno": "on", "retorno_em": "2026-11-06", "retorno_obs": "banho"})
    r = Retorno.query.one()
    assert r.data_prevista == date(2026, 11, 6) and r.cambone == casa["rui"]

    # aparece no prontuário e na lista de retornos
    assert "Tranca Rua" not in client.get("/retornos/").get_data(as_text=True)
    assert "7 Flechas" in client.get("/retornos/").get_data(as_text=True)
    pagina = client.get(f"/pessoas/{casa['joao'].id}?aba=giras").get_data(as_text=True)
    assert "Consagrar pano" in pagina and "Atendido" in pagina
    client.post(f"/retornos/{r.id}/situacao", data={"situacao": "cancelado"})
    assert recarregar(Retorno, r.id).situacao == "cancelado"
    assert "Mapa" in client.get(f"/giras/{gid}/mapa").get_data(as_text=True)


def test_nova_gira_sugere_tipo_e_evita_duplicada(client, app):
    client.post("/giras/nova", data={"data": "2026-11-04", "tipo": "Quarta"})
    g = Gira.query.one()
    assert g.tipo == "Quarta" and g.atualizado_por == "Secretaria"
    resp = client.post("/giras/nova", data={"data": "2026-11-04", "tipo": "Quarta"})
    assert "Já existe uma gira" in resp.get_data(as_text=True)
    client.post("/giras/nova", data={"data": "2026-11-04", "tipo": "Especial", "confirmar": "on"})
    assert Gira.query.count() == 2
