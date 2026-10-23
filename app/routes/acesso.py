"""Acesso ao sistema: uma senha única da casa + nome do responsável do dia.

Fluxo em cada aparelho:
1. Se a casa ainda não tem senha -> tela para definir (primeiro uso).
2. Sem login no aparelho -> pede a senha da casa (o login vale 30 dias).
3. Sem responsável informado HOJE -> pergunta quem está operando o sistema.
   Esse nome é gravado em todos os lançamentos feitos naquele dia.
"""

import time
from datetime import date
from urllib.parse import urlsplit

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from ..extensions import db
from ..models import confere_senha_casa, definir_senha_casa, senha_configurada
from .forms import campo

bp = Blueprint("acesso", __name__)

LIVRES = {"acesso.entrar", "acesso.configurar", "static"}
SO_LOGIN = {"acesso.responsavel", "acesso.sair"}

# proteção simples contra tentativa de adivinhar a senha (por IP, em memória)
MAX_TENTATIVAS = 5
BLOQUEIO_SEGUNDOS = 300
_tentativas = {}


@bp.before_app_request
def exigir_acesso():
    g.responsavel = None
    if request.endpoint in LIVRES or request.endpoint is None:
        return None
    if not senha_configurada():
        return redirect(url_for("acesso.configurar"))
    if not session.get("autenticado"):
        return redirect(url_for("acesso.entrar", proximo=_caminho_atual()))
    if session.get("responsavel_dia") == date.today().isoformat():
        g.responsavel = session.get("responsavel")
    if g.responsavel or request.endpoint in SO_LOGIN:
        return None
    return redirect(url_for("acesso.responsavel", proximo=_caminho_atual()))


def _caminho_atual():
    return request.full_path if request.query_string else request.path


def _destino_seguro(url):
    # só caminhos internos, para o "próximo" não virar redirecionamento externo
    if url and url.startswith("/") and not url.startswith("//") and not urlsplit(url).netloc:
        return url
    return url_for("main.index")


def _bloqueado(ip):
    falhas, ate = _tentativas.get(ip, (0, 0))
    return falhas >= MAX_TENTATIVAS and time.time() < ate


def _registrar_falha(ip):
    falhas, _ = _tentativas.get(ip, (0, 0))
    _tentativas[ip] = (falhas + 1, time.time() + BLOQUEIO_SEGUNDOS)


@bp.route("/configurar", methods=["GET", "POST"])
def configurar():
    """Primeiro uso: define a senha da casa."""
    if senha_configurada():
        return redirect(url_for("acesso.entrar"))
    if request.method == "POST":
        if _senha_valida():
            definir_senha_casa(request.form["senha"])
            db.session.commit()
            session.clear()
            session.permanent = True
            session["autenticado"] = True
            flash("Senha da casa definida. Guarde-a com cuidado.", "success")
            return redirect(url_for("acesso.responsavel"))
    return render_template("acesso/configurar.html")


def _senha_valida():
    senha = request.form.get("senha", "")
    if len(senha) < 6:
        flash("A senha precisa ter pelo menos 6 caracteres.", "danger")
        return False
    if senha != request.form.get("senha2", ""):
        flash("As senhas digitadas não são iguais.", "danger")
        return False
    return True


@bp.route("/entrar", methods=["GET", "POST"])
def entrar():
    if not senha_configurada():
        return redirect(url_for("acesso.configurar"))
    if request.method == "POST":
        ip = request.remote_addr or "?"
        if _bloqueado(ip):
            flash("Muitas tentativas erradas. Aguarde 5 minutos.", "danger")
        elif confere_senha_casa(request.form.get("senha", "")):
            _tentativas.pop(ip, None)
            ultimo = session.get("ultimo_responsavel")
            session.clear()
            session.permanent = True
            session["autenticado"] = True
            if ultimo:
                session["ultimo_responsavel"] = ultimo
            return redirect(url_for("acesso.responsavel", proximo=request.args.get("proximo")))
        else:
            _registrar_falha(ip)
            flash("Senha incorreta.", "danger")
    return render_template("acesso/entrar.html")


@bp.route("/responsavel", methods=["GET", "POST"])
def responsavel():
    if request.method == "POST":
        nome = campo("responsavel")
        if not nome:
            flash("Informe o seu nome.", "danger")
        else:
            session["responsavel"] = nome[:100]
            session["ultimo_responsavel"] = nome[:100]
            session["responsavel_dia"] = date.today().isoformat()
            return redirect(_destino_seguro(request.args.get("proximo")))
    return render_template("acesso/responsavel.html",
                           sugestao=session.get("responsavel") or session.get("ultimo_responsavel", ""))


@bp.route("/sair", methods=["POST"])
def sair():
    session.clear()
    return redirect(url_for("acesso.entrar"))


@bp.route("/senha", methods=["GET", "POST"])
def trocar_senha():
    if request.method == "POST":
        if not confere_senha_casa(request.form.get("atual", "")):
            flash("Senha atual incorreta.", "danger")
        elif _senha_valida():
            definir_senha_casa(request.form["senha"])
            db.session.commit()
            flash("Senha da casa alterada. Os outros aparelhos continuam conectados "
                  "até saírem; nos novos acessos vale a senha nova.", "success")
            return redirect(url_for("main.index"))
    return render_template("acesso/senha.html")
