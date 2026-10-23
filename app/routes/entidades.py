from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Entidade, Linha, Manifestacao
from .forms import campo, campo_int, versao_confere

bp = Blueprint("entidades", __name__, url_prefix="/entidades")


@bp.route("/")
def lista():
    linhas = Linha.query.filter_by(servico=False).order_by(Linha.ordem).all()
    usos = dict(
        db.session.query(Manifestacao.entidade_id, func.count(Manifestacao.id))
        .group_by(Manifestacao.entidade_id).all()
    )
    return render_template("entidades/lista.html", linhas=linhas, usos=usos)


def _salvar(ent):
    if not versao_confere(ent):
        return False
    nome, linha_id = campo("nome"), campo_int("linha_id")
    if not nome or not db.session.get(Linha, linha_id or 0):
        flash("Informe o nome e a linha.", "danger")
        return False
    ent.nome, ent.linha_id, ent.observacoes = nome, linha_id, campo("observacoes")
    try:
        db.session.add(ent)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Já existe uma entidade com esse nome nessa linha.", "danger")
        return False
    return True


def _form(ent, titulo):
    linhas = Linha.query.filter_by(servico=False).order_by(Linha.ordem).all()
    return render_template("entidades/form.html", ent=ent, linhas=linhas, titulo=titulo)


@bp.route("/nova", methods=["GET", "POST"])
def nova():
    ent = Entidade(linha_id=request.args.get("linha", type=int))
    if request.method == "POST" and _salvar(ent):
        flash("Entidade cadastrada.", "success")
        return redirect(url_for(".lista") + f"#linha{ent.linha_id}")
    return _form(ent, "Nova entidade")


@bp.route("/<int:id>/editar", methods=["GET", "POST"])
def editar(id):
    ent = db.get_or_404(Entidade, id)
    if request.method == "POST" and _salvar(ent):
        flash("Entidade atualizada.", "success")
        return redirect(url_for(".lista") + f"#linha{ent.linha_id}")
    return _form(db.get_or_404(Entidade, id), f"Editar {ent.nome}")


@bp.route("/<int:id>/excluir", methods=["POST"])
def excluir(id):
    ent = db.get_or_404(Entidade, id)
    db.session.delete(ent)
    db.session.commit()
    flash(f"Entidade {ent.nome} excluída. Os atendimentos mantêm o texto original.", "success")
    return redirect(url_for(".lista"))
