"""Servidor para uso no dia a dia (vários celulares, tablets e computadores).

    python servidor.py              # porta 8000
    PORTA=8080 python servidor.py

Os aparelhos na mesma rede Wi-Fi acessam pelo endereço mostrado ao iniciar.
"""

import os
import socket

from waitress import serve

from app import create_app


def ip_da_rede():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # não envia nada; só descobre a interface de saída
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


if __name__ == "__main__":
    porta = int(os.environ.get("PORTA", "8000"))
    print(f"TUC7FJ no ar. Nos aparelhos da mesma rede, abra: http://{ip_da_rede()}:{porta}")
    print("Para parar: Ctrl+C")
    serve(create_app(), host="0.0.0.0", port=porta, threads=16)
