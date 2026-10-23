"""Ponto de entrada para hospedagens WSGI (PythonAnywhere, gunicorn, etc.).

As variáveis de ambiente (COOKIE_SEGURO, SQLITE_WAL, ATRAS_DE_PROXY,
SECRET_KEY) são definidas pela hospedagem antes de importar este arquivo.
"""

from app import create_app

application = create_app()
