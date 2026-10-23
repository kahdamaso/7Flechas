from datetime import date, datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..models import Retorno
from .forms import responsavel

bp = Blueprint("retornos", __name__, url_prefix="/retornos")

FILTROS = {
    "pendentes": "Pendentes",
    "atrasados": "Atrasados",
    "concluidos": "Concluídos",
    "cancelados": "Cancelados",
}


@bp.route("/")
def lista():
    filtro = request.args.get("filtro", "pendentes")
    consulta = Retorno.query
    if filtro == "atrasados":
        consulta = consulta.filter(Retorno.situacao == "pendente", Retorno.data_prevista < date.today())
    elif filtro == "concluidos":
        consulta = consulta.filter_by(situacao="concluido")
    elif filtro == "cancelados":
        consulta = consulta.filter_by(situacao="cancelado")
    else:
        filtro = "pendentes"
        consulta = consulta.filter_by(situacao="pendente")
    ordem = Retorno.data_prevista if filtro in ("pendentes", "atrasados") else Retorno.data_prevista.desc()
    return render_template("retornos/lista.html", retornos=consulta.order_by(ordem).limit(500).all(),
                           filtro=filtro, filtros=FILTROS)


@bp.route("/<int:id>/situacao", methods=["POST"])
def mudar_situacao(id):
    """Concluir sem conversa registrada, cancelar ou reabrir um retorno."""
    r = db.get_or_404(Retorno, id)
    nova = request.form.get("situacao")
    if nova in ("pendente", "concluido", "cancelado"):
        r.situacao = nova
        r.concluido_em = datetime.now() if nova == "concluido" else None
        r.registrado_por = responsavel()
        db.session.commit()
        flash(f"Retorno de {r.pessoa.nome_curto}: {nova}.", "success")
    return redirect(request.referrer or url_for(".lista"))
