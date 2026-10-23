#!/bin/sh
# TUC7FJ - importa os cadastros da planilha baixada do Google Drive (.xlsx).
# Uso: ./importar.sh caminho/da/planilha.xlsx
cd "$(dirname "$0")" || exit 1
[ -n "$1" ] || { echo "Uso: ./importar.sh caminho/da/planilha.xlsx"; exit 1; }
[ -x .venv/bin/python ] || { echo "Rode primeiro ./iniciar.sh uma vez."; exit 1; }
.venv/bin/python -m flask --app run importar "$1" | tee importacao-relatorio.txt
