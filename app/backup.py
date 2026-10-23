"""Cópias de segurança do banco SQLite.

O banco é um único arquivo (instance/tuc7fj.db). A cópia usa a API de backup
do SQLite, que é segura mesmo com o sistema em uso. Ficam guardadas as 30
cópias mais recentes em instance/backups/.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

from .config import INSTANCE_DIR

PASTA = INSTANCE_DIR / "backups"
MANTER = 30


def caminho_do_banco(uri):
    if not uri.startswith("sqlite:///") or uri.endswith(":memory:"):
        return None
    return Path(uri.removeprefix("sqlite:///"))


def fazer_backup(uri, pasta=PASTA, manter=MANTER):
    """Copia o banco para ``pasta`` e apaga as cópias mais antigas. Devolve o arquivo criado."""
    origem = caminho_do_banco(uri)
    if origem is None or not origem.exists():
        return None
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"tuc7fj-{datetime.now():%Y%m%d-%H%M%S-%f}.db"
    fonte, copia = sqlite3.connect(origem), sqlite3.connect(destino)
    try:
        fonte.backup(copia)
    finally:
        copia.close()
        fonte.close()
    for antigo in sorted(pasta.glob("tuc7fj-*.db"))[:-manter]:
        antigo.unlink()
    return destino
