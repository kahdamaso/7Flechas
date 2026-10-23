#!/bin/sh
# TUC7FJ - liga o sistema (Mac/Linux). Na primeira vez, instala o que for preciso.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Preparando o sistema pela primeira vez..."
  python3 -m venv .venv || { echo "Instale o Python 3: https://www.python.org/downloads/"; exit 1; }
fi
# instala/atualiza as dependências só quando a lista mudou
if ! cmp -s requirements.txt .venv/instalado.txt; then
  echo "Instalando componentes (precisa de internet só desta vez)..."
  .venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt \
    && cp requirements.txt .venv/instalado.txt \
    || { echo "Não foi possível instalar. Verifique a internet."; exit 1; }
fi
exec .venv/bin/python servidor.py
