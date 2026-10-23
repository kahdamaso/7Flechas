from urllib.parse import urlsplit

from flask import (Blueprint, abort, flash, g, redirect, render_template, request, session,
                   url_for)
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Usuario
from .forms import campo

bp = Blueprint("auth", __name__)

ABERTAS = {"auth.login", "auth.primeiro_acesso", "static"}


@bp.before_app_request
def exigir_login():
    g.usuario = None
    uid = session.get("usuario_id")
    if uid:
        usuario = db.session.get(Usuario, uid)
        if usuario and usuario.ativo:
            g.usuario = usuario
        else:
            session.clear()
    if g.usuario or request.endpoint in ABERTAS or request.endpoint is None:
        return None
    if Usuario.query.first() is None:
        return redirect(url_for("auth.primeiro_acesso"))
    if request.accept_mimetypes.best == "application/json":
        abort(401)
    return redirect(url_for("auth.login", proximo=request.full_path))


def _destino_seguro(url):
    # só aceita caminhos internos, para o "próximo" não virar redirecionamento externo
    if url and url.startswith("/") and not url.startswith("//") and not urlsplit(url).netloc:
        return url
    return url_for("main.index")


def _entrar(usuario):
    session.clear()
    session.permanent = True
    session["usuario_id"] = usuario.id


@bp.route("/entrar", methods=["GET", "POST"])
def login():
    if Usuario.query.first() is None:
        return redirect(url_for("auth.primeiro_acesso"))
    if request.method == "POST":
        usuario = Usuario.query.filter_by(login=(campo("login") or "").lower()).first()
        if usuario and usuario.ativo and usuario.confere_senha(request.form.get("senha", "")):
            _entrar(usuario)
            return redirect(_destino_seguro(request.args.get("proximo")))
        flash("Usuário ou senha incorretos.", "danger")
    return render_template("auth/login.html")


@bp.route("/sair", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/primeiro-acesso", methods=["GET", "POST"])
def primeiro_acesso():
    """Cria o primeiro administrador quando o banco ainda não tem usuários."""
    if Usuario.query.first() is not None:
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        usuario = _usuario_do_form(Usuario(admin=True), senha_obrigatoria=True)
        if usuario:
            usuario.admin = True
            db.session.add(usuario)
            db.session.commit()
            _entrar(usuario)
            flash("Administrador criado. Bem-vindo(a)!", "success")
            return redirect(url_for("main.index"))
    return render_template("auth/primeiro_acesso.html")


def _usuario_do_form(usuario, senha_obrigatoria):
    nome, login, senha = campo("nome"), campo("login"), request.form.get("senha", "")
    if not nome or not login:
        flash("Informe nome e usuário.", "danger")
        return None
    if senha or senha_obrigatoria:
        if len(senha) < 6:
            flash("A senha precisa ter pelo menos 6 caracteres.", "danger")
            return None
        if senha != request.form.get("senha2", ""):
            flash("As senhas não conferem.", "danger")
            return None
        usuario.definir_senha(senha)
    usuario.nome, usuario.login = nome, login
    return usuario


@bp.route("/minha-senha", methods=["GET", "POST"])
def minha_senha():
    if request.method == "POST":
        if not g.usuario.confere_senha(request.form.get("atual", "")):
            flash("Senha atual incorreta.", "danger")
        else:
            senha = request.form.get("senha", "")
            if len(senha) < 6 or senha != request.form.get("senha2", ""):
                flash("A nova senha precisa ter 6+ caracteres e ser igual nos dois campos.", "danger")
            else:
                g.usuario.definir_senha(senha)
                db.session.commit()
                flash("Senha alterada.", "success")
                return redirect(url_for("main.index"))
    return render_template("auth/minha_senha.html")


# --- administração de usuários ---------------------------------------------


def _so_admin():
    if not g.usuario.admin:
        abort(403)


@bp.route("/usuarios/")
def usuarios():
    _so_admin()
    return render_template("auth/usuarios.html", usuarios=Usuario.query.order_by(Usuario.nome).all())


@bp.route("/usuarios/novo", methods=["GET", "POST"])
@bp.route("/usuarios/<int:id>/editar", methods=["GET", "POST"])
def editar_usuario(id=None):
    _so_admin()
    usuario = db.get_or_404(Usuario, id) if id else Usuario(ativo=True)
    if request.method == "POST":
        if _usuario_do_form(usuario, senha_obrigatoria=id is None):
            eu = usuario.id == g.usuario.id
            # o administrador não pode tirar o próprio acesso
            usuario.admin = True if eu else request.form.get("admin") == "on"
            usuario.ativo = True if eu else request.form.get("ativo") == "on"
            try:
                db.session.add(usuario)
                db.session.commit()
                flash("Usuário salvo.", "success")
                return redirect(url_for(".usuarios"))
            except IntegrityError:
                db.session.rollback()
                flash("Esse nome de usuário já existe.", "danger")
    return render_template("auth/usuario_form.html", u=usuario)
