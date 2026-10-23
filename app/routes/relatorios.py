from datetime import datetime

from flask import Blueprint, Response, render_template, request

from .. import relatorios as rel
from ..models import CATEGORIAS_MEDIUNS

bp = Blueprint("relatorios", __name__, url_prefix="/relatorios")


def _data(nome):
    try:
        return datetime.strptime(request.args.get(nome, ""), "%Y-%m-%d").date()
    except ValueError:
        return None


def _periodo():
    return rel.periodo(_data("de"), _data("ate"))


def _csv(nome, cabecalho, linhas, de, ate):
    conteudo = rel.para_csv(cabecalho, linhas)
    arquivo = f"tuc7fj-{nome}-{de:%Y%m%d}-{ate:%Y%m%d}.csv"
    return Response(conteudo, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{arquivo}"'})


def _quer_csv():
    return request.args.get("formato") == "csv"


@bp.route("/")
def index():
    de, ate = _periodo()
    return render_template("relatorios/index.html", de=de, ate=ate)


@bp.route("/frequencia")
def frequencia():
    de, ate = _periodo()
    categoria = request.args.get("categoria", "")
    dados = rel.frequencia(de, ate, categoria or None)
    if _quer_csv():
        return _csv("frequencia", ["Nome", "Categoria", "Giras", "Presenças", "Faltas", "Sem registro",
                                   "Frequência %", "Atendimentos das entidades", "Vezes como cambone"],
                    [[l.pessoa.nome, l.pessoa.categoria, l.giras, l.presentes, l.faltas, l.sem_registro,
                      "" if l.percentual is None else l.percentual, l.atendimentos, l.cambonou]
                     for l in dados["linhas"]], de, ate)
    return render_template("relatorios/frequencia.html", de=de, ate=ate, dados=dados,
                           categoria=categoria, categorias=CATEGORIAS_MEDIUNS)


@bp.route("/retornos")
def retornos():
    de, ate = _periodo()
    dados = rel.retornos(de, ate)
    if _quer_csv():
        return _csv("retornos", ["Entidade", "Linha", "Médium", "Criados", "Concluídos", "Pendentes",
                                 "Cancelados"],
                    [[i["entidade"].rotulo if i["entidade"] else "(removida)",
                      i["entidade"].linha.nome if i["entidade"] else "",
                      i["entidade"].medium.nome if i["entidade"] else "",
                      i["criados"], i["concluido"], i["pendente"], i["cancelado"]]
                     for i in dados["por_entidade"]], de, ate)
    return render_template("relatorios/retornos.html", de=de, ate=ate, dados=dados)


@bp.route("/giras")
def giras():
    de, ate = _periodo()
    dados = rel.giras_e_atendimentos(de, ate)
    if _quer_csv():
        return _csv("giras", ["Data", "Tipo", "Médiuns presentes", "Inscritos", "Consulentes",
                              "Conversas atendidas", "Recusas de linha", "Retornos gerados"],
                    [[i["gira"].data.strftime("%d/%m/%Y"), i["gira"].tipo, i["presentes"], i["inscritos"],
                      i["consulentes"], i["atendidos"], i["recusas"], i["retornos"]]
                     for i in dados["por_gira"]], de, ate)
    return render_template("relatorios/giras.html", de=de, ate=ate, dados=dados)
