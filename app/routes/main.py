from flask import Blueprint, render_template
from sqlalchemy import func

from ..extensions import db
from ..models import CATEGORIAS, Entidade, Pessoa

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    por_categoria = dict(
        db.session.query(Pessoa.categoria, func.count(Pessoa.id))
        .filter(Pessoa.ativo.is_(True)).group_by(Pessoa.categoria).all()
    )
    totais = [(c, por_categoria.get(c, 0)) for c in CATEGORIAS]
    incorporam = Pessoa.query.filter_by(ativo=True, incorpora=True).count()
    entidades = Entidade.query.filter_by(ativa=True).count()
    recentes = Pessoa.query.order_by(Pessoa.criado_em.desc()).limit(5).all()
    return render_template("index.html", totais=totais, incorporam=incorporam,
                           entidades=entidades, recentes=recentes)
