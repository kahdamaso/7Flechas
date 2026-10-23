"""Atalho para importar as planilhas sem usar o comando `flask`.

Uso:
    python scripts/importar_csv.py data/            # todos os CSVs da pasta
    python scripts/importar_csv.py data/TUC7FJ_02_08_2026.csv --substituir
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.importacao import importar  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Importa as planilhas CSV do TUC7FJ.")
    parser.add_argument("caminhos", nargs="+", help="arquivos .csv ou pastas")
    parser.add_argument("--substituir", action="store_true",
                        help="reimporta sessões que já têm atendimentos")
    parser.add_argument("--ano", type=int, help="ano para datas sem ano (planilha de presença)")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        print(importar(args.caminhos, substituir=args.substituir, ano=args.ano).texto())


if __name__ == "__main__":
    main()
