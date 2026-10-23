from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Entidade, Linha, Pessoa
from ..utils import chave
from .forms import campo, campo_int, versao_confere

bp = Blueprint("entidades", __name__, url_prefix="/entidades")


@bp.route("/")
def lista():
    """Todas as entidades da casa, por linha, com o médium de cada uma."""
    busca = request.args.get("q", "").strip()
    linhas = Linha.query.order_by(Linha.ordem).all()
    consulta = Entidade.query.join(Pessoa).filter(Pessoa.ativo.is_(True))
    if busca:
        k = chave(busca)
        consulta = consulta.filter(Entidade.nome_chave.contains(k) | Pessoa.nome_chave.contains(k)
                                   | Pessoa.apelido.ilike(f"%{busca}%"))
    por_linha = {}
    for e in consulta.all():
        por_linha.setdefault(e.linha_id, []).append(e)
    for lista_linha in por_linha.values():
        lista_linha.sort(key=lambda e: (not e.ativa, e.nome is None, chave(e.rotulo)))
    return render_template("entidades/lista.html", linhas=linhas, por_linha=por_linha, busca=busca)


@bp.route("/<int:id>/editar", methods=["GET", "POST"])
def editar(id):
    ent = db.get_or_404(Entidade, id)
    if request.method == "POST" and versao_confere(ent):
        linha = db.session.get(Linha, campo_int("linha_id") or 0)
        if linha is None:
            flash("Escolha a linha.", "danger")
        else:
            ent.nome, ent.linha = campo("nome"), linha
            ent.ativa = request.form.get("ativa") == "on"
            ent.observacoes = campo("observacoes")
            try:
                db.session.commit()
                flash("Entidade atualizada.", "success")
                return redirect(url_for("pessoas.prontuario", id=ent.medium_id, aba="ficha"))
            except IntegrityError:
                db.session.rollback()
                flash("Esse médium já tem uma entidade com esse nome nessa linha.", "danger")
        ent = db.get_or_404(Entidade, id)
    return render_template("entidades/editar.html", ent=ent,
                           linhas=Linha.query.order_by(Linha.ordem).all())


@bp.route("/<int:id>/excluir", methods=["POST"])
def excluir(id):
    ent = db.get_or_404(Entidade, id)
    medium_id = ent.medium_id
    db.session.delete(ent)
    db.session.commit()
    flash("Entidade removida da ficha.", "success")
    return redirect(url_for("pessoas.prontuario", id=medium_id, aba="ficha"))
