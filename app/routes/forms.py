"""Helpers simples de formulário (sem WTForms: o CSRF vem do Flask-WTF)."""

from datetime import datetime

from flask import flash, g, request

from ..utils import limpar


def campo(nome):
    return limpar(request.form.get(nome))


def campo_data(nome):
    texto = campo(nome)
    if not texto:
        return None
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        return None


def campo_int(nome):
    texto = campo(nome)
    try:
        return int(texto) if texto else None
    except ValueError:
        return None


def responsavel():
    """Nome de quem está operando o sistema hoje (gravado nos lançamentos)."""
    return g.get("responsavel")


def versao_confere(obj):
    """Compara a versão enviada pelo formulário com a do banco.

    Se outro aparelho salvou o registro depois que este formulário foi aberto,
    devolve False e avisa; a tela é exibida de novo com os dados atuais.
    """
    enviada = campo_int("versao")
    if obj.id is None or enviada is None or enviada == obj.versao:
        return True
    flash("Este cadastro foi alterado em outro aparelho enquanto você editava. "
          "Os dados abaixo já são os mais recentes: confira e salve de novo.", "warning")
    return False
