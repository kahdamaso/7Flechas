"""Relatórios (Fase 3) e cópia de segurança."""

import sqlite3
from datetime import date, timedelta

from app import gira as regras
from app import relatorios as rel
from app.backup import fazer_backup
from app.extensions import db
from app.models import Gira

from .test_gira import QUARTA, RESP, SEXTA, _inscrever, casa  # noqa: F401  (fixture)


def _uma_gira_completa(casa):
    """Sexta: igor/ana/bia SIM, carlos NÃO. Maria fala com Jurema (retorno) e Tranca Rua."""
    g = casa["gira"]
    maria = _inscrever(casa, "maria")
    _inscrever(casa, "joao")
    regras.definir_cambone(g, casa["jurema"], casa["rui"])
    regras.encerrar(regras.chamar(g, casa["jurema"], maria, RESP), "atendido", RESP,
                    retorno_em=SEXTA + timedelta(days=7))
    regras.encerrar(regras.chamar(g, casa["tranca"], maria, RESP), "atendido", RESP)
    return g


def test_frequencia(casa):
    _uma_gira_completa(casa)
    quarta = Gira(data=QUARTA, tipo="Quarta")
    db.session.add(quarta)
    db.session.commit()
    regras.marcar_presenca(quarta, casa["ana"], False, RESP)
    regras.marcar_presenca(quarta, casa["igor"], True, RESP)

    dados = rel.frequencia(QUARTA, SEXTA)
    por_nome = {l.pessoa.nome: l for l in dados["linhas"]}
    ana = por_nome["Ana Medium"]
    assert (ana.giras, ana.presentes, ana.faltas, ana.percentual) == (2, 1, 1, 50)
    assert por_nome["Igor Chefe"].percentual == 100 and por_nome["Igor Chefe"].atendimentos == 1
    assert por_nome["Carlos Faltou"].percentual == 0
    rui = por_nome["Rui Auxiliar"]
    assert rui.cambonou == 1 and rui.sem_registro == 2 and rui.percentual is None  # nunca marcado
    # menor frequência primeiro
    assert dados["linhas"][0].percentual == 0
    assert [l.pessoa.nome for l in rel.frequencia(QUARTA, SEXTA, "Auxiliar")["linhas"]] == ["Rui Auxiliar"]


def test_retornos_e_giras(casa):
    _uma_gira_completa(casa)
    hoje = date.today()
    r = rel.retornos(hoje - timedelta(days=1), hoje)
    assert r["criados"] == 1 and r["pendentes_agora"] == 1 and r["taxa_conclusao"] == 0
    assert r["por_entidade"][0]["entidade"] == casa["jurema"]

    gi = rel.giras_e_atendimentos(SEXTA, SEXTA)
    assert gi["total_giras"] == 1 and gi["conversas"] == 2 and gi["pessoas_atendidas"] == 2
    linha = gi["por_gira"][0]
    assert (linha["presentes"], linha["inscritos"], linha["atendidos"], linha["retornos"]) == (3, 2, 2, 1)
    assert {p.pessoa.nome for p in gi["novos"]} == {"Maria Consulente", "Joao Consulente"}
    assert dict(gi["por_linha"]) == {"Caboclo": 1, "Exu": 1}


def test_telas_e_csv(client, casa):
    _uma_gira_completa(casa)
    periodo = f"de={QUARTA.isoformat()}&ate={SEXTA.isoformat()}"
    for nome in ["", "frequencia", "retornos", "giras"]:
        assert client.get(f"/relatorios/{nome}?{periodo}").status_code == 200, nome
    resp = client.get(f"/relatorios/frequencia?{periodo}&formato=csv")
    assert resp.mimetype == "text/csv"
    texto = resp.get_data(as_text=True)
    assert texto.startswith("﻿Nome;Categoria") and "Ana Medium;Corrente;1;1;0;0;100" in texto
    assert "attachment" in resp.headers["Content-Disposition"]
    assert "Jurema" in client.get(f"/relatorios/retornos?formato=csv").get_data(as_text=True)


def test_backup(tmp_path):
    banco = tmp_path / "tuc7fj.db"
    with sqlite3.connect(banco) as con:
        con.execute("create table t (x)")
        con.execute("insert into t values (42)")
    pasta = tmp_path / "copias"
    for _ in range(3):
        copia = fazer_backup(f"sqlite:///{banco}", pasta=pasta, manter=2)
    assert len(list(pasta.glob("*.db"))) == 2  # só as 2 mais recentes
    with sqlite3.connect(copia) as con:
        assert con.execute("select x from t").fetchone() == (42,)
    assert fazer_backup("sqlite:///:memory:") is None
