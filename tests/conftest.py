import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.config import TestConfig  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import definir_senha_casa  # noqa: E402

SENHA = "senha-teste"


@pytest.fixture
def app():
    from app.routes import acesso

    acesso._tentativas.clear()  # o bloqueio por senha errada não passa de um teste para outro
    app = create_app(TestConfig)
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def anonimo(app):
    """Aparelho que ainda não entrou no sistema."""
    return app.test_client()


@pytest.fixture
def client(app):
    """Aparelho já com a senha da casa e o responsável do dia informados."""
    definir_senha_casa(SENHA)
    db.session.commit()
    c = app.test_client()
    c.post("/entrar", data={"senha": SENHA})
    c.post("/responsavel", data={"responsavel": "Secretaria"})
    return c


def recarregar(modelo, id_):
    db.session.expire_all()
    return db.session.get(modelo, id_)
