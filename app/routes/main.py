from datetime import date

from flask import Blueprint, render_template
from sqlalchemy import func

from .. import gira as regras
from ..extensions import db
from ..models import CATEGORIAS, Entidade, Inscricao, Pessoa, Retorno

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    por_categoria = dict(
        db.session.query(Pessoa.categoria, func.count(Pessoa.id))
        .filter(Pessoa.ativo.is_(True)).group_by(Pessoa.categoria).all()
    )
    totais = [(c, por_categoria.get(c, 0)) for c in CATEGORIAS]
    proxima = regras.proxima_gira()
    info_proxima = None
    if proxima:
        info_proxima = {
            "inscritos": Inscricao.query.filter_by(gira_id=proxima.id).count(),
            "presentes": len(regras.presentes_ids(proxima)),
            "retornos": len(regras.retornos_previstos(proxima)),
        }
    return render_template(
        "index.html", totais=totais, proxima=proxima, info_proxima=info_proxima, hoje=date.today(),
        incorporam=Pessoa.query.filter_by(ativo=True, incorpora=True).count(),
        entidades=Entidade.query.filter_by(ativa=True).count(),
        retornos_pendentes=Retorno.query.filter_by(situacao="pendente").count(),
    )
