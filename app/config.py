import os
import secrets
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"


def _chave_secreta():
    """Usa SECRET_KEY do ambiente ou gera uma e guarda em instance/secret_key.

    Assim cada instalação tem sua própria chave sem configuração manual, e os
    logins continuam válidos quando o servidor reinicia.
    """
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    INSTANCE_DIR.mkdir(exist_ok=True)
    arquivo = INSTANCE_DIR / "secret_key"
    if not arquivo.exists():
        arquivo.write_text(secrets.token_hex(32))
    return arquivo.read_text().strip()


class Config:
    SECRET_KEY = _chave_secreta()
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{INSTANCE_DIR / 'tuc7fj.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    ITENS_POR_PAGINA = 50
    # login vale por 30 dias em cada aparelho
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # ligue (COOKIE_SEGURO=1) quando o sistema estiver atrás de HTTPS
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SEGURO") == "1"
    # o token CSRF acompanha a sessão (formulário aberto por horas no tablet não expira)
    WTF_CSRF_TIME_LIMIT = None


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
