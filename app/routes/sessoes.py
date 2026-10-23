import re
from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import func

from ..extensions import db
from ..models import (
    CATEGORIAS_ATENDIMENTO,
    GRUPOS_MEDIUM,
    Atendimento,
    Consulente,
    Linha,
    Manifestacao,
    Medium,
    Presenca,
    Sessao,
)
from .forms import campo, campo_data, campo_int

bp = Blueprint("sessoes", __name__, url_prefix="/sessoes")

TIPOS_SESSAO = ["Gira", "Gira de Caboclo", "Gira de Exu", "Gira de Preto Velho", "Desenvolvimento",
                "Consagração", "Festa", "Outra"]


@bp.route("/")
def lista():
    presentes = (
        db.session.query(Presenca.sessao_id, func.count(Presenca.id))
        .filter(Presenca.presente.is_(True)).group_by(Presenca.sessao_id)
    )
    atendidos = db.session.query(Atendimento.sessao_id, func.count(Atendimento.id)).group_by(
        Atendimento.sessao_id
    )
    return render_template(
        "sessoes/lista.html",
        sessoes=Sessao.query.order_by(Sessao.data.desc()).all(),
        presentes=dict(presentes.all()),
        atendidos=dict(atendidos.all()),
    )


def _salvar_sessao(sessao):
    data_sessao = campo_data("data")
    if not data_sessao:
        flash("Informe uma data válida.", "danger")
        return False
    sessao.data = data_sessao
    sessao.tipo = campo("tipo") or "Gira"
    sessao.descricao = campo("descricao")
    sessao.observacoes = campo("observacoes")
    db.session.add(sessao)
    db.session.commit()
    return True


@bp.route("/nova", methods=["GET", "POST"])
def nova():
    sessao = Sessao(data=date.today(), tipo="Gira")
    if request.method == "POST":
        if _salvar_sessao(sessao):
            flash("Sessão criada. Marque a presença dos médiuns.", "success")
            return redirect(url_for(".presenca", id=sessao.id))
    return render_template("sessoes/form.html", sessao=sessao, tipos=TIPOS_SESSAO, titulo="Nova sessão")


@bp.route("/<int:id>/editar", methods=["GET", "POST"])
def editar(id):
    sessao = db.get_or_404(Sessao, id)
    if request.method == "POST" and _salvar_sessao(sessao):
        flash("Sessão atualizada.", "success")
        return redirect(url_for(".detalhe", id=id))
    return render_template("sessoes/form.html", sessao=sessao, tipos=TIPOS_SESSAO,
                           titulo=f"Editar sessão de {sessao.data:%d/%m/%Y}")


@bp.route("/<int:id>/excluir", methods=["POST"])
def excluir(id):
    sessao = db.get_or_404(Sessao, id)
    db.session.delete(sessao)
    db.session.commit()
    flash("Sessão excluída.", "success")
    return redirect(url_for(".lista"))


@bp.route("/<int:id>")
def detalhe(id):
    sessao = db.get_or_404(Sessao, id)
    linhas = Linha.query.order_by(Linha.ordem).all()
    usadas = {m.linha_id for a in sessao.atendimentos for m in a.manifestacoes}
    presentes = sorted((p for p in sessao.presencas if p.presente), key=lambda p: p.medium.nome)
    ausentes = sorted((p for p in sessao.presencas if not p.presente), key=lambda p: p.medium.nome)
    return render_template(
        "sessoes/detalhe.html", sessao=sessao, presentes=presentes, ausentes=ausentes,
        linhas=[l for l in linhas if l.id in usadas], categorias=CATEGORIAS_ATENDIMENTO,
    )


# ---------------------------------------------------------------------------
# Presença
# ---------------------------------------------------------------------------


@bp.route("/<int:id>/presenca", methods=["GET", "POST"])
def presenca(id):
    sessao = db.get_or_404(Sessao, id)
    atuais = {p.medium_id: p for p in sessao.presencas}
    # médiuns ativos + quem já tem registro nesta sessão (mesmo que inativo hoje)
    mediuns = Medium.query.filter(
        (Medium.ativo.is_(True)) | (Medium.id.in_(list(atuais) or [0]))
    ).order_by(Medium.nome).all()

    if request.method == "POST":
        for m in mediuns:
            status = request.form.get(f"status_{m.id}", "")
            justificativa = campo(f"just_{m.id}")
            registro = atuais.get(m.id)
            if status not in ("presente", "falta"):
                if registro:
                    db.session.delete(registro)
                continue
            if registro is None:
                registro = Presenca(sessao=sessao, medium=m)
                db.session.add(registro)
            registro.presente = status == "presente"
            registro.justificativa = justificativa if status == "falta" else None
        db.session.commit()
        flash("Presença salva.", "success")
        return redirect(url_for(".detalhe", id=id))

    por_grupo = {g: [m for m in mediuns if m.grupo == g] for g in GRUPOS_MEDIUM}
    return render_template("sessoes/presenca.html", sessao=sessao, por_grupo=por_grupo, atuais=atuais)


# ---------------------------------------------------------------------------
# Atendimentos e manifestações
# ---------------------------------------------------------------------------


def _contexto_atendimento(sessao, atendimento):
    linhas = Linha.query.order_by(Linha.ordem).all()
    presentes_ids = {p.medium_id for p in sessao.presencas if p.presente}
    mediuns = Medium.query.order_by(Medium.nome).all()
    # médiuns presentes primeiro na lista de "quem atendeu"
    mediuns_ordenados = sorted(mediuns, key=lambda m: (m.id not in presentes_ids, m.nome))
    por_linha = {m.linha_id: m for m in atendimento.manifestacoes}
    return dict(
        sessao=sessao, at=atendimento, linhas=linhas, por_linha=por_linha,
        mediuns=mediuns, mediuns_ordenados=mediuns_ordenados, presentes_ids=presentes_ids,
        consulentes=Consulente.query.order_by(Consulente.nome).all(),
        categorias=CATEGORIAS_ATENDIMENTO,
    )


def _pessoa_do_form(at):
    """Define o atendido a partir do formulário. Devolve mensagem de erro ou None."""
    categoria = campo("categoria")
    if categoria not in CATEGORIAS_ATENDIMENTO:
        return "Categoria inválida."
    at.categoria = categoria
    if categoria == "Consulente":
        texto = campo("consulente") or ""
        m = re.search(r"#(\d+)\)?\s*$", texto)
        consulente = db.session.get(Consulente, int(m.group(1))) if m else None
        if consulente is None and texto:
            nome = re.sub(r"\s*\(#\d+\)\s*$", "", texto)
            consulente = Consulente(nome=nome)
            db.session.add(consulente)
            flash(f"Consulente '{nome}' cadastrado. Complete o cadastro depois.", "info")
        if consulente is None:
            return "Informe o consulente."
        at.consulente, at.medium = consulente, None
    else:
        medium = db.session.get(Medium, campo_int("medium_id") or 0)
        if medium is None:
            return "Selecione o médium atendido."
        at.medium, at.consulente = medium, None
    return None


def _manifestacoes_do_form(at, linhas):
    at.manifestacoes.clear()
    for linha in linhas:
        escolha = request.form.get(f"ent_{linha.id}", "")
        medium_id = campo_int(f"med_{linha.id}")
        descricao = campo(f"desc_{linha.id}")
        if not (escolha or medium_id or descricao):
            continue
        man = Manifestacao(linha=linha, descricao=descricao)
        if escolha == "geral":
            man.geral = True
        elif escolha.isdigit():
            man.entidade_id = int(escolha)
        if medium_id:
            man.medium_responsavel_id = medium_id
        at.manifestacoes.append(man)


def _form_atendimento(sessao, at, titulo):
    ctx = _contexto_atendimento(sessao, at)
    if request.method == "POST":
        erro = _pessoa_do_form(at)
        if erro:
            flash(erro, "danger")
            db.session.rollback()
        else:
            at.parentesco = campo("parentesco")
            at.retorno = campo("retorno")
            at.observacoes = campo("observacoes")
            _manifestacoes_do_form(at, ctx["linhas"])
            if at.medium and not any(p.medium_id == at.medium.id for p in sessao.presencas):
                db.session.add(Presenca(sessao=sessao, medium=at.medium, presente=True))
            db.session.add(at)
            db.session.commit()
            flash("Atendimento salvo.", "success")
            if request.form.get("acao") == "salvar_novo":
                return redirect(url_for(".novo_atendimento", id=sessao.id, categoria=at.categoria))
            return redirect(url_for(".detalhe", id=sessao.id) + f"#at{at.id}")
    return render_template("sessoes/atendimento.html", titulo=titulo, **ctx)


@bp.route("/<int:id>/atendimentos/novo", methods=["GET", "POST"])
def novo_atendimento(id):
    sessao = db.get_or_404(Sessao, id)
    # sessao_id (e não sessao=) para o objeto não entrar na sessão do ORM antes de validado
    at = Atendimento(sessao_id=sessao.id, categoria=request.args.get("categoria", "Consulente"))
    return _form_atendimento(sessao, at, "Novo atendimento")


@bp.route("/<int:id>/atendimentos/<int:at_id>/editar", methods=["GET", "POST"])
def editar_atendimento(id, at_id):
    sessao = db.get_or_404(Sessao, id)
    at = db.get_or_404(Atendimento, at_id)
    if at.sessao_id != sessao.id:
        return redirect(url_for(".detalhe", id=id))
    return _form_atendimento(sessao, at, f"Atendimento de {at.pessoa_nome}")


@bp.route("/<int:id>/atendimentos/<int:at_id>/excluir", methods=["POST"])
def excluir_atendimento(id, at_id):
    at = db.get_or_404(Atendimento, at_id)
    if at.sessao_id == id:
        db.session.delete(at)
        db.session.commit()
        flash("Atendimento excluído.", "success")
    return redirect(url_for(".detalhe", id=id))
