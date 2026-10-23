from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import GRUPOS_MEDIUM, Entidade, Linha, Medium, MediumEntidade, Presenca, Sessao
from ..utils import chave, normalizar_telefone
from .forms import campo, versao_confere

bp = Blueprint("mediuns", __name__, url_prefix="/mediuns")


@bp.route("/")
def lista():
    busca = request.args.get("q", "").strip()
    grupo = request.args.get("grupo", "")
    situacao = request.args.get("situacao", "ativos")
    consulta = Medium.query
    if busca:
        consulta = consulta.filter(
            (Medium.nome_chave.contains(chave(busca))) | (Medium.apelido.ilike(f"%{busca}%"))
        )
    if grupo:
        consulta = consulta.filter_by(grupo=grupo)
    if situacao == "ativos":
        consulta = consulta.filter_by(ativo=True)
    elif situacao == "inativos":
        consulta = consulta.filter_by(ativo=False)
    mediuns = consulta.order_by(Medium.nome).all()
    return render_template(
        "mediuns/lista.html", mediuns=mediuns, busca=busca, grupo=grupo,
        situacao=situacao, grupos=GRUPOS_MEDIUM,
    )


@bp.route("/<int:id>")
def detalhe(id):
    medium = db.get_or_404(Medium, id)
    presencas = (
        Presenca.query.filter_by(medium_id=id).join(Sessao).order_by(Sessao.data.desc()).all()
    )
    total = len(presencas)
    presentes = sum(1 for p in presencas if p.presente)
    return render_template(
        "mediuns/detalhe.html", medium=medium, presencas=presencas,
        frequencia=(presentes / total * 100) if total else None,
    )


def _salvar(medium):
    if not versao_confere(medium):
        return False
    nome = campo("nome")
    if not nome:
        flash("Informe o nome.", "danger")
        return False
    medium.nome = nome
    medium.apelido = campo("apelido")
    medium.grupo = campo("grupo") if campo("grupo") in GRUPOS_MEDIUM else "Corrente"
    medium.telefone = normalizar_telefone(campo("telefone"))
    medium.ativo = request.form.get("ativo") == "on"
    medium.observacoes = campo("observacoes")

    selecionadas = {int(i) for i in request.form.getlist("entidades") if i.isdigit()}
    atuais = {v.entidade_id: v for v in medium.entidades}
    for ent_id, vinculo in atuais.items():
        if ent_id not in selecionadas:
            medium.entidades.remove(vinculo)
    for ent_id in selecionadas - set(atuais):
        if db.session.get(Entidade, ent_id):
            medium.entidades.append(MediumEntidade(entidade_id=ent_id))
    try:
        db.session.add(medium)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Já existe um médium com esse nome.", "danger")
        return False
    return True


def _form(medium, titulo):
    linhas = Linha.query.filter_by(servico=False).order_by(Linha.ordem).all()
    marcadas = {v.entidade_id for v in medium.entidades}
    return render_template(
        "mediuns/form.html", medium=medium, titulo=titulo, grupos=GRUPOS_MEDIUM,
        linhas=linhas, marcadas=marcadas,
    )


@bp.route("/novo", methods=["GET", "POST"])
def novo():
    medium = Medium(ativo=True, grupo="Corrente")
    if request.method == "POST":
        if _salvar(medium):
            flash("Médium cadastrado.", "success")
            return redirect(url_for(".detalhe", id=medium.id))
    return _form(medium, "Novo médium")


@bp.route("/<int:id>/editar", methods=["GET", "POST"])
def editar(id):
    medium = db.get_or_404(Medium, id)
    if request.method == "POST":
        if _salvar(medium):
            flash("Médium atualizado.", "success")
            return redirect(url_for(".detalhe", id=medium.id))
        medium = db.get_or_404(Medium, id)
    return _form(medium, f"Editar {medium.nome}")


@bp.route("/<int:id>/excluir", methods=["POST"])
def excluir(id):
    medium = db.get_or_404(Medium, id)
    db.session.delete(medium)
    db.session.commit()
    flash(f"{medium.nome} excluído(a).", "success")
    return redirect(url_for(".lista"))
