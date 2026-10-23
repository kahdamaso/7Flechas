from flask import Flask, flash, redirect, request
from sqlalchemy.orm.exc import StaleDataError

from .config import INSTANCE_DIR, Config
from .extensions import csrf, db
from .utils import formatar_cpf, formatar_telefone


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    INSTANCE_DIR.mkdir(exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)

    from . import models
    from .routes import acesso, entidades, giras, main, pessoas, retornos

    for bp in (acesso.bp, main.bp, pessoas.bp, entidades.bp, giras.bp, retornos.bp):
        app.register_blueprint(bp)

    @app.errorhandler(StaleDataError)
    def _conflito(_erro):
        # dois aparelhos salvaram o mesmo registro quase no mesmo instante
        db.session.rollback()
        flash("Outro aparelho salvou este cadastro agora há pouco. Confira os dados "
              "atualizados e salve de novo se precisar.", "warning")
        return redirect(request.referrer or request.url)

    app.jinja_env.filters["cpf"] = formatar_cpf
    app.jinja_env.filters["telefone"] = formatar_telefone
    app.jinja_env.filters["data"] = lambda d: d.strftime("%d/%m/%Y") if d else ""
    app.jinja_env.filters["hora"] = lambda d: d.strftime("%H:%M") if d else ""
    app.jinja_env.filters["dia_semana"] = lambda d: [
        "segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"][d.weekday()]

    with app.app_context():
        db.create_all()
        models.garantir_linhas_padrao()

    from .cli import registrar_comandos

    registrar_comandos(app)
    return app
