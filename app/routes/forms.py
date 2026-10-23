"""Helpers simples de formulário (sem WTForms: o CSRF vem do Flask-WTF)."""

from datetime import datetime

from flask import request

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
