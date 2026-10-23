from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..models import Atendimento, Consulente, Sessao
from ..utils import chave, normalizar_cpf, normalizar_telefone, somente_digitos
from .forms import campo, campo_data, versao_confere

bp = Blueprint("consulentes", __name__, url_prefix="/consulentes")


@bp.route("/")
def lista():
    busca = request.args.get("q", "").strip()
    cidade = request.args.get("cidade", "").strip()
    consulta = Consulente.query
    if busca:
        digitos = somente_digitos(busca)
        filtro = Consulente.nome_chave.contains(chave(busca))
        if digitos and len(digitos) >= 3:
            filtro = filtro | Consulente.cpf.contains(digitos) | Consulente.telefone.contains(digitos)
        consulta = consulta.filter(filtro)
    if cidade:
        consulta = consulta.filter(Consulente.cidade == cidade)
    pagina = consulta.order_by(Consulente.nome).paginate(
        per_page=current_app.config["ITENS_POR_PAGINA"], error_out=False
    )
    cidades = [
        c for (c,) in db.session.query(Consulente.cidade).filter(Consulente.cidade.isnot(None))
        .distinct().order_by(Consulente.cidade)
    ]
    return render_template(
        "consulentes/lista.html", pagina=pagina, busca=busca, cidade=cidade, cidades=cidades
    )


@bp.route("/<int:id>")
def detalhe(id):
    consulente = db.get_or_404(Consulente, id)
    atendimentos = (
        Atendimento.query.filter_by(consulente_id=id).join(Sessao).order_by(Sessao.data.desc()).all()
    )
    return render_template("consulentes/detalhe.html", c=consulente, atendimentos=atendimentos)


def _salvar(c):
    erros = []
    nome = campo("nome")
    if not nome:
        erros.append("Informe o nome.")
    cpf_digitado = campo("cpf")
    cpf = normalizar_cpf(cpf_digitado)
    if cpf_digitado and not cpf:
        erros.append("CPF inválido.")
    if cpf:
        dono = Consulente.query.filter(Consulente.cpf == cpf, Consulente.id != c.id).first()
        if dono:
            erros.append(f"CPF já cadastrado para {dono.nome}.")
    if erros:
        for e in erros:
            flash(e, "danger")
        return False

    c.nome = nome
    c.cpf = cpf
    c.data_nascimento = campo_data("data_nascimento")
    c.telefone = normalizar_telefone(campo("telefone"))
    c.email = (campo("email") or "").lower() or None
    c.endereco = campo("endereco")
    c.bairro = campo("bairro")
    c.cidade = campo("cidade")
    c.uf = (campo("uf") or "").upper()[:2] or None
    c.observacoes = campo("observacoes")
    db.session.add(c)
    db.session.commit()
    return True


@bp.route("/novo", methods=["GET", "POST"])
def novo():
    c = Consulente()
    if request.method == "POST":
        if _salvar(c):
            flash("Consulente cadastrado.", "success")
            return redirect(url_for(".detalhe", id=c.id))
    return render_template("consulentes/form.html", c=c, titulo="Novo consulente", form=request.form)


@bp.route("/<int:id>/editar", methods=["GET", "POST"])
def editar(id):
    c = db.get_or_404(Consulente, id)
    if request.method == "POST":
        if not versao_confere(c):
            return render_template("consulentes/form.html", c=c, titulo=f"Editar {c.nome}", form={})
        if _salvar(c):
            flash("Consulente atualizado.", "success")
            return redirect(url_for(".detalhe", id=c.id))
    return render_template("consulentes/form.html", c=c, titulo=f"Editar {c.nome}", form=request.form)


@bp.route("/<int:id>/excluir", methods=["POST"])
def excluir(id):
    c = db.get_or_404(Consulente, id)
    db.session.delete(c)
    db.session.commit()
    flash(f"{c.nome} excluído(a).", "success")
    return redirect(url_for(".lista"))
