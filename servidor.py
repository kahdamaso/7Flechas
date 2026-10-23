"""Servidor para uso no dia a dia (vários celulares, tablets e computadores).

    python servidor.py              # porta 8000
    PORTA=8080 python servidor.py

Os aparelhos na mesma rede Wi-Fi acessam pelo endereço mostrado ao iniciar.
Uma cópia de segurança do banco é feita ao iniciar e a cada 6 horas
(instance/backups/, guardando as 30 mais recentes).
"""

import os
import socket
import threading

from waitress import serve

from app import create_app
from app.backup import fazer_backup

HORAS_ENTRE_BACKUPS = 6


def ip_da_rede():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # não envia nada; só descobre a interface de saída
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def backups_periodicos(uri):
    parar = threading.Event()

    def ciclo():
        while not parar.wait(HORAS_ENTRE_BACKUPS * 3600):
            fazer_backup(uri)

    threading.Thread(target=ciclo, daemon=True).start()


if __name__ == "__main__":
    app = create_app()
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    copia = fazer_backup(uri)
    if copia:
        print(f"Cópia de segurança: {copia}")
    backups_periodicos(uri)
    porta = int(os.environ.get("PORTA", "8000"))
    print(f"TUC7FJ no ar. Nos aparelhos da mesma rede, abra: http://{ip_da_rede()}:{porta}")
    print("Para parar: Ctrl+C")
    serve(app, host="0.0.0.0", port=porta, threads=16)
