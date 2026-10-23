"""Regras de negócio da gira (Fase 2).

Fluxo de atendimento
--------------------
1. Chamada: médiuns marcados SIM. As entidades desses médiuns estão "em terra".
2. Inscrição: a pessoa dá o nome. Consulente/Colaborador passam em todas as
   linhas; Auxiliar/Corrente escolhem as linhas (GERAL). Pedidos ao Sete
   Flechas (orientação, consagração, autorização para entidade específica).
3. Atendimento: o cambone diz o nome da entidade que está cambonando. O
   sistema encerra a conversa anterior dela (perguntando se teve retorno) e
   sugere quem chamar, nesta ordem:
     a) inscritos com retorno pendente com essa entidade;
     b) inscritos com pedido ao Sete Flechas (se a entidade é o Sete Flechas);
     c) inscritos autorizados pelo Sete Flechas a falar com essa entidade;
     d) fila da linha: quem ainda não passou nela; quem incorpora primeiro,
        depois por ordem de chegada.
   Ficam de fora: quem já está conversando com outra entidade, o próprio médium
   da entidade e os parentes dele (estes aparecem como bloqueados).
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import (
    CATEGORIAS_QUARTA,
    CATEGORIAS_TODAS_LINHAS,
    CamboneGira,
    Conversa,
    Entidade,
    Gira,
    Inscricao,
    InscricaoLinha,
    Parentesco,
    PedidoSeteFlechas,
    Pessoa,
    Presenca,
    Retorno,
)
from .utils import chave

NOMES_SETE_FLECHAS = {"7 flechas", "sete flechas", "7flechas", "caboclo 7 flechas",
                      "caboclo sete flechas"}
DIAS_RETORNO_PADRAO = 7


class ErroGira(Exception):
    """Operação recusada por uma regra da gira (mensagem pronta para o usuário)."""


# ---------------------------------------------------------------------------
# Consultas básicas
# ---------------------------------------------------------------------------


def eh_sete_flechas(entidade):
    return entidade is not None and chave(entidade.nome) in NOMES_SETE_FLECHAS


def tipo_sugerido(dia):
    """Quarta -> gira interna; sexta -> pública; outros dias -> especial."""
    return {2: "Quarta", 4: "Sexta"}.get(dia.weekday(), "Especial")


def proxima_gira():
    return (Gira.query.filter(Gira.data >= date.today(), Gira.encerrada.is_(False))
            .order_by(Gira.data, Gira.id).first())


def presentes_ids(gira):
    return {p.pessoa_id for p in Presenca.query.filter_by(gira_id=gira.id, presente=True)}


def entidades_em_terra(gira):
    """Entidades ativas dos médiuns marcados SIM na chamada."""
    ids = presentes_ids(gira)
    if not ids:
        return []
    entidades = (Entidade.query.join(Pessoa)
                 .filter(Entidade.medium_id.in_(ids), Entidade.ativa.is_(True)).all())
    return sorted(entidades, key=lambda e: (e.linha.ordem, chave(e.rotulo)))


def parentes_ids(pessoa_id):
    lacos = Parentesco.query.filter(
        (Parentesco.pessoa_a_id == pessoa_id) | (Parentesco.pessoa_b_id == pessoa_id)
    )
    return {l.pessoa_b_id if l.pessoa_a_id == pessoa_id else l.pessoa_a_id for l in lacos}


def retornos_pendentes(pessoa_id):
    return (Retorno.query.filter_by(pessoa_id=pessoa_id, situacao="pendente")
            .order_by(Retorno.data_prevista).all())


def conversa_aberta_da_entidade(gira, entidade):
    return Conversa.query.filter_by(gira_id=gira.id, entidade_id=entidade.id,
                                    situacao="chamado").first()


def conversa_aberta_da_inscricao(inscricao):
    return Conversa.query.filter_by(inscricao_id=inscricao.id, situacao="chamado").first()


def cambone_da_entidade(gira, entidade):
    registro = CamboneGira.query.filter_by(gira_id=gira.id, entidade_id=entidade.id).first()
    return registro.cambone if registro else None


def retornos_previstos(gira):
    """Retornos pendentes com data até o dia da gira (os atrasados também)."""
    return (Retorno.query.filter(Retorno.situacao == "pendente", Retorno.data_prevista <= gira.data)
            .order_by(Retorno.data_prevista).all())


# ---------------------------------------------------------------------------
# Chamada
# ---------------------------------------------------------------------------


def marcar_presenca(gira, pessoa, presente, responsavel):
    """presente: True (SIM), False (NÃO) ou None (limpa a marcação)."""
    registro = Presenca.query.filter_by(gira_id=gira.id, pessoa_id=pessoa.id).first()
    if presente is None:
        if registro:
            db.session.delete(registro)
    else:
        if registro is None:
            registro = Presenca(gira_id=gira.id, pessoa_id=pessoa.id, presente=presente)
            db.session.add(registro)
        registro.presente = presente
        registro.registrado_por = responsavel
    try:
        db.session.commit()
    except IntegrityError:  # outro aparelho criou o mesmo registro no mesmo instante
        db.session.rollback()
        return marcar_presenca(gira, pessoa, presente, responsavel)
    return registro


# ---------------------------------------------------------------------------
# Inscrição
# ---------------------------------------------------------------------------


def pode_inscrever(gira, pessoa):
    if not pessoa.ativo:
        return f"{pessoa.nome} está com o cadastro inativo."
    if gira.tipo == "Quarta" and pessoa.categoria not in CATEGORIAS_QUARTA:
        return "Na gira de quarta só são atendidos Auxiliares e membros da Corrente."
    return None


def inscrever(gira, pessoa, linhas_ids, pedidos, responsavel, observacao=None, inscricao=None):
    """Cria (ou atualiza) a inscrição.

    ``pedidos``: lista de (tipo, entidade_id|None) para o Sete Flechas.
    """
    erro = pode_inscrever(gira, pessoa)
    if erro:
        raise ErroGira(erro)
    if inscricao is None:
        inscricao = Inscricao.query.filter_by(gira_id=gira.id, pessoa_id=pessoa.id).first()
    nova = inscricao is None
    if nova:
        inscricao = Inscricao(gira_id=gira.id, pessoa_id=pessoa.id, categoria=pessoa.categoria,
                              registrado_por=responsavel)
        db.session.add(inscricao)
    inscricao.todas_linhas = inscricao.categoria in CATEGORIAS_TODAS_LINHAS
    inscricao.observacao = observacao
    if not inscricao.todas_linhas:
        escolhidas = set(linhas_ids)
        for item in list(inscricao.linhas):
            if item.linha_id not in escolhidas:
                inscricao.linhas.remove(item)
        for linha_id in escolhidas - inscricao.ids_linhas:
            inscricao.linhas.append(InscricaoLinha(linha_id=linha_id))
    # pedidos novos (os já registrados ficam como estão)
    existentes = {(p.tipo, p.entidade_id) for p in inscricao.pedidos}
    for tipo, entidade_id in pedidos:
        if (tipo, entidade_id) not in existentes:
            inscricao.pedidos.append(PedidoSeteFlechas(tipo=tipo, entidade_id=entidade_id,
                                                       registrado_por=responsavel))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ErroGira(f"{pessoa.nome} acabou de ser inscrito(a) em outro aparelho.")
    return inscricao, nova


# ---------------------------------------------------------------------------
# Sugestões de quem chamar
# ---------------------------------------------------------------------------


@dataclass
class Sugestoes:
    retornos: list = field(default_factory=list)      # (inscricao, retorno)
    sete_flechas: list = field(default_factory=list)  # (inscricao, [pedidos])
    autorizados: list = field(default_factory=list)   # (inscricao, pedido)
    fila: list = field(default_factory=list)          # inscricao
    bloqueados: list = field(default_factory=list)    # (inscricao, motivo)

    @property
    def total(self):
        return len(self.retornos) + len(self.sete_flechas) + len(self.autorizados) + len(self.fila)


def sugestoes(gira, entidade):
    inscricoes = Inscricao.query.filter_by(gira_id=gira.id).all()
    ocupados = {c.inscricao_id for c in Conversa.query.filter_by(gira_id=gira.id, situacao="chamado")}
    parentes_do_medium = parentes_ids(entidade.medium_id)
    conversas = Conversa.query.filter_by(gira_id=gira.id).all()
    ja_passou_linha = {(c.inscricao_id, c.linha_id) for c in conversas
                       if c.situacao in ("atendido", "nao_quis")}
    ausente_na_linha = {(c.inscricao_id, c.linha_id) for c in conversas if c.situacao == "ausente"}
    atendido_pela_entidade = {c.inscricao_id for c in conversas
                              if c.entidade_id == entidade.id and c.situacao == "atendido"}
    sete_flechas = eh_sete_flechas(entidade)

    s = Sugestoes()
    ja_listados = set()
    for insc in inscricoes:
        if insc.id in ocupados or insc.pessoa_id == entidade.medium_id:
            continue
        if insc.pessoa_id in parentes_do_medium:
            s.bloqueados.append((insc, f"parente de {entidade.medium.nome_curto}"))
            continue
        retorno = next((r for r in retornos_pendentes(insc.pessoa_id) if r.entidade_id == entidade.id),
                       None)
        if retorno:
            s.retornos.append((insc, retorno))
            ja_listados.add(insc.id)
            continue
        if sete_flechas:
            pendentes = [p for p in insc.pedidos if p.situacao == "pendente"]
            if pendentes:
                s.sete_flechas.append((insc, pendentes))
                ja_listados.add(insc.id)
                continue
        autorizacao = next((p for p in insc.pedidos if p.entidade_id == entidade.id
                            and p.situacao == "autorizado"), None)
        if autorizacao and insc.id not in atendido_pela_entidade:
            s.autorizados.append((insc, autorizacao))
            ja_listados.add(insc.id)
            continue
        quer_a_linha = insc.todas_linhas or entidade.linha_id in insc.ids_linhas
        if quer_a_linha and (insc.id, entidade.linha_id) not in ja_passou_linha:
            s.fila.append(insc)

    # quem incorpora conversa primeiro; quem estava ausente quando chamado vai para o fim
    s.fila.sort(key=lambda i: ((i.id, entidade.linha_id) in ausente_na_linha,
                               not i.pessoa.incorpora, i.chegada, i.id))
    s.retornos.sort(key=lambda par: (par[1].data_prevista, par[0].chegada))
    s.sete_flechas.sort(key=lambda par: par[0].chegada)
    return s


# ---------------------------------------------------------------------------
# Atendimento
# ---------------------------------------------------------------------------


def definir_cambone(gira, entidade, cambone):
    registro = CamboneGira.query.filter_by(gira_id=gira.id, entidade_id=entidade.id).first()
    if registro is None:
        registro = CamboneGira(gira_id=gira.id, entidade_id=entidade.id)
        db.session.add(registro)
    registro.cambone = cambone
    db.session.commit()


def chamar(gira, entidade, inscricao, responsavel, liberacao_parentesco=None):
    """Registra que a pessoa foi chamada para conversar com a entidade."""
    if gira.encerrada:
        raise ErroGira("Esta gira já foi encerrada.")
    if inscricao.gira_id != gira.id:
        raise ErroGira("Inscrição de outra gira.")
    if inscricao.pessoa_id == entidade.medium_id:
        raise ErroGira("A pessoa é o próprio médium desta entidade.")
    if inscricao.pessoa_id in parentes_ids(entidade.medium_id) and not liberacao_parentesco:
        raise ErroGira(f"{inscricao.pessoa.nome} é parente de {entidade.medium.nome}: "
                       "não pode conversar com esta entidade.")
    if entidade.medium_id not in presentes_ids(gira):
        raise ErroGira(f"{entidade.medium.nome} não está marcado(a) como presente na chamada.")
    retorno = next((r for r in retornos_pendentes(inscricao.pessoa_id) if r.entidade_id == entidade.id),
                   None)
    conversa = Conversa(
        gira_id=gira.id, inscricao_id=inscricao.id, linha_id=entidade.linha_id,
        entidade_id=entidade.id, cambone=cambone_da_entidade(gira, entidade),
        retorno=retorno, liberacao_parentesco=liberacao_parentesco, registrado_por=responsavel,
    )
    db.session.add(conversa)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if conversa_aberta_da_entidade(gira, entidade):
            raise ErroGira(f"{entidade.rotulo} já está atendendo alguém (registrado em outro aparelho).")
        raise ErroGira(f"{inscricao.pessoa.nome} já está conversando com outra entidade.")
    return conversa


def encerrar(conversa, situacao, responsavel, retorno_em=None, retorno_obs=None):
    """Fecha a conversa. ``retorno_em`` (data) cria um novo retorno pendente."""
    if situacao not in ("atendido", "nao_quis", "ausente"):
        raise ErroGira("Situação inválida.")
    if conversa.situacao != "chamado":
        raise ErroGira("Esta conversa já foi encerrada (talvez em outro aparelho).")
    conversa.situacao = situacao
    conversa.encerrado_em = datetime.now()
    pessoa_id = conversa.inscricao.pessoa_id
    if situacao == "atendido":
        if conversa.retorno and conversa.retorno.situacao == "pendente":
            conversa.retorno.situacao = "concluido"
            conversa.retorno.concluido_em = datetime.now()
        if eh_sete_flechas(conversa.entidade):
            for pedido in conversa.inscricao.pedidos:
                if pedido.situacao == "pendente" and pedido.entidade_id is None:
                    pedido.situacao = "atendido"
        if retorno_em:
            db.session.add(Retorno(
                pessoa_id=pessoa_id, entidade_id=conversa.entidade_id, cambone_id=conversa.cambone_id,
                conversa_origem=conversa, data_prevista=retorno_em, observacao=retorno_obs,
                registrado_por=responsavel,
            ))
    db.session.commit()
    return conversa


def recusar_linha(gira, inscricao, linha, responsavel):
    """A pessoa não quer passar nessa linha (sai da fila dela)."""
    db.session.add(Conversa(
        gira_id=gira.id, inscricao_id=inscricao.id, linha_id=linha.id, situacao="nao_quis",
        encerrado_em=datetime.now(), registrado_por=responsavel,
    ))
    db.session.commit()


def decidir_autorizacao(pedido, autorizar, responsavel):
    pedido.situacao = "autorizado" if autorizar else "negado"
    pedido.registrado_por = responsavel
    db.session.commit()


def data_retorno_padrao(gira):
    return gira.data + timedelta(days=DIAS_RETORNO_PADRAO)
