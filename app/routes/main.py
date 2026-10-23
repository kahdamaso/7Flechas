from flask import Blueprint, render_template
from sqlalchemy import func

from ..extensions import db
from ..models import Atendimento, Consulente, Entidade, Medium, Sessao

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    totais = {
        "Médiuns ativos": Medium.query.filter_by(ativo=True).count(),
        "Consulentes": Consulente.query.count(),
        "Entidades": Entidade.query.count(),
        "Sessões": Sessao.query.count(),
        "Atendimentos": Atendimento.query.count(),
    }
    ultimas = (
        db.session.query(Sessao, func.count(Atendimento.id))
        .outerjoin(Atendimento)
        .group_by(Sessao.id)
        .order_by(Sessao.data.desc())
        .limit(5)
        .all()
    )
    return render_template("index.html", totais=totais, ultimas=ultimas)
