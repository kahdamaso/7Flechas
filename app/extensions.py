import os

from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
csrf = CSRFProtect()


@event.listens_for(Engine, "connect")
def _configurar_sqlite(dbapi_connection, _record):
    """Ajustes do SQLite para uso por vários aparelhos ao mesmo tempo.

    - foreign_keys: respeitar ON DELETE CASCADE;
    - WAL: leituras não bloqueiam a escrita (celulares consultando enquanto
      outro aparelho salva);
    - busy_timeout: em vez de falhar com "database is locked", espera até 5 s
      a escrita concorrente terminar.

    Em hospedagens com disco de rede (ex.: PythonAnywhere) o WAL não é
    confiável: defina SQLITE_WAL=0 para usar o modo tradicional.
    """
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        if os.environ.get("SQLITE_WAL", "1") != "0":
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        else:
            cursor.execute("PRAGMA journal_mode=DELETE")
        cursor.close()
