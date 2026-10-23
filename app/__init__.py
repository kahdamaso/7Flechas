from flask import Flask

from .config import BASE_DIR, Config
from .extensions import csrf, db
from .utils import formatar_cpf, formatar_telefone


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    (BASE_DIR / "instance").mkdir(exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)

    from . import models  # noqa: F401  (registra as tabelas)
    from .routes import consulentes, entidades, main, mediuns, sessoes

    for bp in (main.bp, mediuns.bp, consulentes.bp, entidades.bp, sessoes.bp):
        app.register_blueprint(bp)

    app.jinja_env.filters["cpf"] = formatar_cpf
    app.jinja_env.filters["telefone"] = formatar_telefone
    app.jinja_env.filters["data"] = lambda d: d.strftime("%d/%m/%Y") if d else ""

    with app.app_context():
        db.create_all()
        models.garantir_linhas_padrao()

    from .cli import registrar_comandos

    registrar_comandos(app)
    return app
