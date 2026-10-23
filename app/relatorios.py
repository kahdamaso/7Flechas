"""Relatórios (Fase 3): frequência dos médiuns, retornos e giras/atendimentos.

Todos recebem um período [de, ate] (datas inclusivas) e devolvem estruturas
simples, usadas tanto pelas telas quanto pela exportação em CSV.
"""

import csv
import io
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from .models import (
    CATEGORIAS_MEDIUNS,
    Conversa,
    Entidade,
    Gira,
    Inscricao,
    Pessoa,
    Presenca,
    Retorno,
)

DIAS_PADRAO = 90


def periodo(de=None, ate=None):
    """Período padrão: os últimos 90 dias até hoje."""
    ate = ate or date.today()
    de = de or (ate - timedelta(days=DIAS_PADRAO))
    if de > ate:
        de, ate = ate, de
    return de, ate


def _limites(de, ate):
    return datetime.combine(de, time.min), datetime.combine(ate, time.max)


def _giras(de, ate):
    return Gira.query.filter(Gira.data >= de, Gira.data <= ate).order_by(Gira.data).all()


def _pct(parte, total):
    return round(100 * parte / total) if total else None


# ---------------------------------------------------------------------------
# Frequência dos médiuns
# ---------------------------------------------------------------------------


@dataclass
class LinhaFrequencia:
    pessoa: Pessoa
    giras: int          # giras com chamada em que essa pessoa deveria estar
    presentes: int
    faltas: int
    sem_registro: int
    atendimentos: int   # conversas atendidas pelas entidades dela
    cambonou: int       # conversas em que foi cambone

    @property
    def marcadas(self):
        return self.presentes + self.faltas

    @property
    def percentual(self):
        # só conta as giras em que a pessoa foi marcada na chamada (SIM ou NÃO);
        # quem ficou sem marcação não é tratado como falta
        return _pct(self.presentes, self.marcadas)


def frequencia(de, ate, categoria=None):
    """Frequência de cada médium nas giras do período que tiveram chamada.

    Colaboradores só são contados nas giras públicas (não vêm na quarta).
    """
    giras = _giras(de, ate)
    ids_giras = [g.id for g in giras]
    presencas = Presenca.query.filter(Presenca.gira_id.in_(ids_giras or [0])).all()
    com_chamada = {p.gira_id for p in presencas}
    giras = [g for g in giras if g.id in com_chamada]
    marcacoes = {(p.gira_id, p.pessoa_id): p.presente for p in presencas}

    conversas = Conversa.query.filter(Conversa.gira_id.in_([g.id for g in giras] or [0]),
                                      Conversa.situacao == "atendido").all()
    por_medium = Counter(c.entidade.medium_id for c in conversas if c.entidade)
    por_cambone = Counter(c.cambone_id for c in conversas if c.cambone_id)

    ids_marcados = {pid for (_, pid) in marcacoes}
    consulta = Pessoa.query.filter(Pessoa.categoria.in_(CATEGORIAS_MEDIUNS))
    if categoria in CATEGORIAS_MEDIUNS:
        consulta = consulta.filter(Pessoa.categoria == categoria)
    linhas = []
    for p in consulta.order_by(Pessoa.nome).all():
        if not p.ativo and p.id not in ids_marcados:
            continue
        devidas = [g for g in giras if g.publica or p.categoria != "Colaborador"]
        sim = sum(1 for g in devidas if marcacoes.get((g.id, p.id)) is True)
        nao = sum(1 for g in devidas if marcacoes.get((g.id, p.id)) is False)
        linhas.append(LinhaFrequencia(
            pessoa=p, giras=len(devidas), presentes=sim, faltas=nao,
            sem_registro=len(devidas) - sim - nao,
            atendimentos=por_medium.get(p.id, 0), cambonou=por_cambone.get(p.id, 0),
        ))
    # menor frequência primeiro: é quem precisa de atenção
    linhas.sort(key=lambda l: (l.percentual if l.percentual is not None else 101, l.pessoa.nome))
    return {"giras": giras, "linhas": linhas}


# ---------------------------------------------------------------------------
# Retornos
# ---------------------------------------------------------------------------


def retornos(de, ate):
    inicio, fim = _limites(de, ate)
    criados = Retorno.query.filter(Retorno.registrado_em >= inicio, Retorno.registrado_em <= fim).all()
    concluidos_no_periodo = Retorno.query.filter(
        Retorno.situacao == "concluido", Retorno.concluido_em >= inicio, Retorno.concluido_em <= fim
    ).count()
    pendentes = Retorno.query.filter_by(situacao="pendente").all()
    situacoes = Counter(r.situacao for r in criados)

    por_entidade = {}
    for r in criados:
        chave_ent = r.entidade_id or 0
        item = por_entidade.setdefault(chave_ent, {"entidade": r.entidade, "criados": 0,
                                                   "concluido": 0, "pendente": 0, "cancelado": 0})
        item["criados"] += 1
        item[r.situacao] += 1
    ranking = sorted(por_entidade.values(), key=lambda i: (-i["criados"], i["entidade"].rotulo
                                                            if i["entidade"] else ""))
    return {
        "criados": len(criados),
        "situacoes": situacoes,
        "taxa_conclusao": _pct(situacoes["concluido"], len(criados)),
        "concluidos_no_periodo": concluidos_no_periodo,
        "pendentes_agora": len(pendentes),
        "atrasados_agora": sum(1 for r in pendentes if r.atrasado),
        "por_entidade": ranking,
    }


# ---------------------------------------------------------------------------
# Giras e atendimentos
# ---------------------------------------------------------------------------


def giras_e_atendimentos(de, ate):
    giras = _giras(de, ate)
    ids = [g.id for g in giras] or [0]
    inscricoes = Inscricao.query.filter(Inscricao.gira_id.in_(ids)).all()
    conversas = Conversa.query.filter(Conversa.gira_id.in_(ids)).all()
    presencas = Presenca.query.filter(Presenca.gira_id.in_(ids), Presenca.presente.is_(True)).all()
    retornos_gerados = Counter(
        r.conversa_origem.gira_id
        for r in Retorno.query.join(Conversa, Retorno.conversa_origem_id == Conversa.id)
        .filter(Conversa.gira_id.in_(ids))
    )

    por_gira = []
    for g in giras:
        insc_g = [i for i in inscricoes if i.gira_id == g.id]
        conv_g = [c for c in conversas if c.gira_id == g.id]
        por_gira.append({
            "gira": g,
            "presentes": sum(1 for p in presencas if p.gira_id == g.id),
            "inscritos": len(insc_g),
            "consulentes": sum(1 for i in insc_g if i.categoria == "Consulente"),
            "atendidos": sum(1 for c in conv_g if c.situacao == "atendido"),
            "recusas": sum(1 for c in conv_g if c.situacao == "nao_quis"),
            "retornos": retornos_gerados.get(g.id, 0),
        })

    atendidas = [c for c in conversas if c.situacao == "atendido" and c.entidade]
    por_entidade = Counter(c.entidade_id for c in atendidas)
    entidades = {e.id: e for e in Entidade.query.filter(Entidade.id.in_(list(por_entidade) or [0]))}
    por_linha = Counter(c.linha.nome for c in atendidas)

    # pessoas que vieram pela primeira vez no período
    primeira_vez = {}
    for i in Inscricao.query.join(Gira).order_by(Gira.data).all():
        primeira_vez.setdefault(i.pessoa_id, i)
    novos = [i for i in primeira_vez.values() if de <= i.gira.data <= ate]

    pessoas_atendidas = {i.pessoa_id for i in inscricoes}
    return {
        "por_gira": por_gira,
        "total_giras": len(giras),
        "pessoas_atendidas": len(pessoas_atendidas),
        "inscricoes": len(inscricoes),
        "conversas": len(atendidas),
        "por_entidade": [(entidades[eid], n) for eid, n in por_entidade.most_common()],
        "por_linha": por_linha.most_common(),
        "novos": sorted(novos, key=lambda i: (i.gira.data, i.pessoa.nome)),
        "categorias": Counter(i.categoria for i in inscricoes),
    }


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def para_csv(cabecalho, linhas):
    """CSV com ';' e BOM, que o Excel em português abre direto com acentos corretos."""
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";")
    escritor.writerow(cabecalho)
    escritor.writerows(linhas)
    return "﻿" + saida.getvalue()
