#!/bin/bash
# Instala ou atualiza o TUC7FJ no PythonAnywhere.
# Rode num console "Bash" do PythonAnywhere:
#     bash ~/tuc7fj/deploy/pythonanywhere.sh
set -e

PASTA="$HOME/tuc7fj"
REPO="https://github.com/kahdamaso/7Flechas.git"
RAMO="claude/confident-sagan-zykmvc"
DOMINIO="${USER}.pythonanywhere.com"
WSGI_DIR="${WSGI_DIR:-/var/www}"
WSGI="$WSGI_DIR/${USER}_pythonanywhere_com_wsgi.py"

echo "== 1/4 Código"
if [ -d "$PASTA/.git" ]; then
  git -C "$PASTA" pull --ff-only
else
  git clone -b "$RAMO" "$REPO" "$PASTA"
fi
cd "$PASTA"

echo "== 2/4 Python e componentes"
if [ ! -x .venv/bin/python ]; then
  PY=""
  for v in 3.13 3.12 3.11 3.10; do
    if command -v "python$v" >/dev/null 2>&1; then PY="python$v"; break; fi
  done
  [ -n "$PY" ] || { echo "Nenhum Python 3.10+ encontrado."; exit 1; }
  "$PY" -m venv .venv
fi
.venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt
VERSAO=$(.venv/bin/python -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
mkdir -p instance data

# o disco do PythonAnywhere é de rede: SQLite sem WAL também nos comandos do console
grep -q "SQLITE_WAL=0" "$HOME/.bashrc" 2>/dev/null || echo "export SQLITE_WAL=0" >> "$HOME/.bashrc"
export SQLITE_WAL=0
.venv/bin/python -m flask --app run init-db >/dev/null

echo "== 3/4 Arquivo WSGI"
CONTEUDO="# TUC7FJ — gerado por deploy/pythonanywhere.sh
import os
import sys

PASTA = '$PASTA'
sys.path.insert(0, PASTA)
os.chdir(PASTA)
os.environ.setdefault('COOKIE_SEGURO', '1')    # só HTTPS
os.environ.setdefault('SQLITE_WAL', '0')       # disco de rede
os.environ.setdefault('ATRAS_DE_PROXY', '1')   # IP real de cada aparelho

from wsgi import application  # noqa: E402,F401
"
if [ -f "$WSGI" ]; then
  [ -f "$WSGI.original" ] || cp "$WSGI" "$WSGI.original"
  printf '%s' "$CONTEUDO" > "$WSGI"
  echo "Arquivo WSGI configurado: $WSGI"
  WSGI_OK=1
else
  echo "Ainda não existe o web app. Crie-o na aba Web (passo abaixo) e rode este script de novo."
  WSGI_OK=0
fi

echo
echo "== 4/4 Falta pouco — na aba Web do PythonAnywhere:"
if [ "$WSGI_OK" = 0 ]; then
  echo "  a) 'Add a new web app' -> Next -> 'Manual configuration' -> Python $VERSAO -> Next"
  echo "  b) Rode de novo:  bash ~/tuc7fj/deploy/pythonanywhere.sh"
else
  echo "  a) Em 'Virtualenv', informe:  $PASTA/.venv"
  echo "     (o web app precisa ser Python $VERSAO)"
  echo "  b) Em 'Security', ligue 'Force HTTPS'"
  echo "  c) Clique no botão verde 'Reload'"
  echo "  d) Abra https://$DOMINIO e defina a senha da casa"
fi
echo
echo "Importar a planilha: envie o .xlsx pela aba Files para $PASTA/data/ e rode:"
echo "  cd ~/tuc7fj && .venv/bin/python -m flask --app run importar data/TUC7FJ.xlsx"
