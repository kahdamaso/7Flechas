from datetime import date

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func

from .. import gira as regras
from ..extensions import db
from ..models import (
    CATEGORIAS_MEDIUNS,
    PEDIDOS_SETE_FLECHAS,
    CamboneGira,
    TIPOS_GIRA,
    Conversa,
    Entidade,
    Gira,
    Inscricao,
    Linha,
    PedidoSeteFlechas,
    Pessoa,
    Presenca,
)
from ..utils import chave
from .forms import campo, campo_data, campo_int, responsavel, versao_confere
from .pessoas import pessoa_do_texto

bp = Blueprint("giras", __name__, url_prefix="/giras")


def _gira(id):
    return db.get_or_404(Gira, id)


def _quer_json():
    return request.headers.get("X-Requested-With") == "fetch"


# ---------------------------------------------------------------------------
# Lista, criação e edição
# ---------------------------------------------------------------------------


@bp.route("/")
def lista():
    giras = Gira.query.order_by(Gira.data.desc(), Gira.id.desc()).all()
    inscritos = dict(db.session.query(Inscricao.gira_id, func.count(Inscricao.id))
                     .group_by(Inscricao.gira_id).all())
    presentes = dict(db.session.query(Presenca.gira_id, func.count(Presenca.id))
                     .filter(Presenca.presente.is_(True)).group_by(Presenca.gira_id).all())
    return render_template("giras/lista.html", giras=giras, inscritos=inscritos,
                           presentes=presentes, hoje=date.today())


def _salvar_gira(g):
    if not versao_confere(g):
        return False
    data_gira = campo_data("data")
    tipo = campo("tipo")
    if not data_gira or tipo not in TIPOS_GIRA:
        flash("Informe a data e o tipo da gira.", "danger")
        return False
    g.data, g.tipo = data_gira, tipo
    g.descricao, g.observacoes = campo("descricao"), campo("observacoes")
    g.atualizado_por = responsavel()
    db.session.add(g)
    db.session.commit()
    return True


@bp.route("/nova", methods=["GET", "POST"])
def nova():
    dia = campo_data("data") if request.method == "POST" else date.today()
    g = Gira(data=dia or date.today(), tipo=regras.tipo_sugerido(dia or date.today()))
    if request.method == "POST":
        repetida = Gira.query.filter_by(data=campo_data("data")).first()
        if repetida and not request.form.get("confirmar"):
            flash(f"Já existe uma gira em {repetida.data:%d/%m/%Y}. Abra a existente ou "
                  "marque a confirmação para criar outra no mesmo dia.", "warning")
        elif _salvar_gira(g):
            flash("Gira criada. Comece pela chamada dos médiuns.", "success")
            return redirect(url_for(".chamada", id=g.id))
    return render_template("giras/form.html", g=g, tipos=TIPOS_GIRA, titulo="Nova gira",
                           confirmar=request.method == "POST")


@bp.route("/<int:id>/editar", methods=["GET", "POST"])
def editar(id):
    g = _gira(id)
    if request.method == "POST" and _salvar_gira(g):
        flash("Gira atualizada.", "success")
        return redirect(url_for(".painel", id=id))
    return render_template("giras/form.html", g=g, tipos=TIPOS_GIRA,
                           titulo=f"Editar gira de {g.data:%d/%m/%Y}")


@bp.route("/<int:id>/encerrar", methods=["POST"])
def encerrar_gira(id):
    g = _gira(id)
    abertas = Conversa.query.filter_by(gira_id=id, situacao="chamado").count()
    if not g.encerrada and abertas and not request.form.get("confirmar"):
        flash(f"Ainda há {abertas} conversa(s) em andamento. Encerre-as no Atendimento "
              "ou confirme para encerrar a gira assim mesmo.", "warning")
        return redirect(url_for(".painel", id=id))
    g.encerrada = not g.encerrada
    g.atualizado_por = responsavel()
    db.session.commit()
    flash("Gira encerrada." if g.encerrada else "Gira reaberta.", "success")
    return redirect(url_for(".painel", id=id))


@bp.route("/<int:id>/excluir", methods=["POST"])
def excluir(id):
    g = _gira(id)
    db.session.delete(g)
    db.session.commit()
    flash("Gira excluída.", "success")
    return redirect(url_for(".lista"))


@bp.route("/<int:id>")
def painel(id):
    g = _gira(id)
    em_terra = regras.entidades_em_terra(g)
    conversas = Conversa.query.filter_by(gira_id=id).all()
    resumo = {
        "presentes": Presenca.query.filter_by(gira_id=id, presente=True).count(),
        "ausentes": Presenca.query.filter_by(gira_id=id, presente=False).count(),
        "inscritos": len(g.inscricoes),
        "entidades": len(em_terra),
        "atendimentos": sum(1 for c in conversas if c.situacao == "atendido"),
        "em_andamento": sum(1 for c in conversas if c.situacao == "chamado"),
    }
    return render_template("giras/painel.html", g=g, resumo=resumo,
                           previstos=regras.retornos_previstos(g))


# ---------------------------------------------------------------------------
# Chamada
# ---------------------------------------------------------------------------


@bp.route("/<int:id>/chamada")
def chamada(id):
    g = _gira(id)
    registros = {p.pessoa_id: p for p in Presenca.query.filter_by(gira_id=id)}
    mediuns = Pessoa.query.filter(
        Pessoa.categoria.in_(CATEGORIAS_MEDIUNS),
        (Pessoa.ativo.is_(True)) | (Pessoa.id.in_(list(registros) or [0])),
    ).order_by(Pessoa.nome).all()
    grupos = [(c, [m for m in mediuns if m.categoria == c]) for c in ["Corrente", "Auxiliar", "Colaborador"]]
    marcados = sum(1 for r in registros.values() if r.presente)
    return render_template("giras/chamada.html", g=g, grupos=grupos, registros=registros,
                           marcados=marcados)


@bp.route("/<int:id>/chamada/<int:pessoa_id>", methods=["POST"])
def marcar(id, pessoa_id):
    g = _gira(id)
    pessoa = db.get_or_404(Pessoa, pessoa_id)
    valor = request.form.get("presente")
    presente = {"sim": True, "nao": False}.get(valor)
    regras.marcar_presenca(g, pessoa, presente, responsavel())
    if _quer_json():
        return jsonify(ok=True, presente=valor)
    return redirect(url_for(".chamada", id=id) + f"#p{pessoa_id}")


# ---------------------------------------------------------------------------
# Inscrição
# ---------------------------------------------------------------------------


@bp.route("/<int:id>/inscricao", methods=["GET", "POST"])
def inscricao(id):
    g = _gira(id)
    if request.method == "POST":
        pessoa = pessoa_do_texto(campo("pessoa"))
        if pessoa is None:
            flash("Escolha a pessoa na lista. Se ela não aparece, faça o cadastro rápido.", "warning")
        else:
            return redirect(url_for(".inscrever", id=id, pessoa_id=pessoa.id))
    inscritos = sorted(g.inscricoes, key=lambda i: i.chegada, reverse=True)
    ja_inscritos = {i.pessoa_id for i in g.inscricoes}
    pessoas = [p for p in Pessoa.query.filter_by(ativo=True).order_by(Pessoa.nome)
               if p.id not in ja_inscritos and (g.publica or p.categoria in ("Auxiliar", "Corrente"))]
    return render_template("giras/inscricao.html", g=g, inscritos=inscritos, pessoas=pessoas)


@bp.route("/<int:id>/inscricao/<int:pessoa_id>", methods=["GET", "POST"])
def inscrever(id, pessoa_id):
    g = _gira(id)
    pessoa = db.get_or_404(Pessoa, pessoa_id)
    insc = Inscricao.query.filter_by(gira_id=id, pessoa_id=pessoa_id).first()
    linhas = Linha.query.order_by(Linha.ordem).all()
    em_terra = regras.entidades_em_terra(g)
    if request.method == "POST":
        pedidos = [(t, None) for t in request.form.getlist("pedidos")
                   if t in PEDIDOS_SETE_FLECHAS and t != "Autorização para entidade"]
        for ent_id in request.form.getlist("autorizacoes"):
            if ent_id.isdigit() and db.session.get(Entidade, int(ent_id)):
                pedidos.append(("Autorização para entidade", int(ent_id)))
        linhas_ids = [int(x) for x in request.form.getlist("linhas") if x.isdigit()]
        try:
            insc, nova = regras.inscrever(g, pessoa, linhas_ids, pedidos, responsavel(),
                                          campo("observacao"), inscricao=insc)
            flash(f"{pessoa.nome} {'inscrito(a)' if nova else 'atualizado(a)'}.", "success")
            return redirect(url_for(".inscricao", id=id))
        except regras.ErroGira as erro:
            flash(str(erro), "danger")

    # alertas para a recepção
    retornos = regras.retornos_pendentes(pessoa.id)
    presentes = regras.presentes_ids(g)
    parentes = [db.session.get(Pessoa, pid) for pid in regras.parentes_ids(pessoa.id)]
    parentes_em_terra = {e.medium_id for e in em_terra} & {p.id for p in parentes}
    impedimento = regras.pode_inscrever(g, pessoa)
    entidades_casa = sorted(
        Entidade.query.join(Pessoa).filter(Entidade.ativa.is_(True), Pessoa.ativo.is_(True)).all(),
        key=lambda e: (e.linha.ordem, chave(e.rotulo)))
    return render_template(
        "giras/inscrever.html", g=g, p=pessoa, insc=insc, linhas=linhas,
        linhas_em_terra={e.linha_id for e in em_terra}, retornos=retornos, presentes=presentes,
        parentes=parentes, parentes_em_terra=parentes_em_terra, impedimento=impedimento,
        pedidos_tipos=[t for t in PEDIDOS_SETE_FLECHAS if t != "Autorização para entidade"],
        entidades_casa=entidades_casa,
    )


@bp.route("/<int:id>/inscricoes/<int:insc_id>/excluir", methods=["POST"])
def remover_inscricao(id, insc_id):
    insc = db.get_or_404(Inscricao, insc_id)
    if insc.gira_id == id:
        if any(c.situacao == "chamado" for c in insc.conversas):
            flash("Esta pessoa está em atendimento agora; encerre a conversa antes.", "warning")
        else:
            nome = insc.pessoa.nome
            db.session.delete(insc)
            db.session.commit()
            flash(f"Inscrição de {nome} removida.", "success")
    return redirect(url_for(".inscricao", id=id))


@bp.route("/<int:id>/inscricoes/<int:insc_id>/recusar", methods=["POST"])
def recusar_linha(id, insc_id):
    g = _gira(id)
    insc = db.get_or_404(Inscricao, insc_id)
    linha = db.session.get(Linha, campo_int("linha_id") or 0)
    if insc.gira_id == id and linha:
        regras.recusar_linha(g, insc, linha, responsavel())
        flash(f"{insc.pessoa.nome_curto} não vai passar em {linha.nome}.", "success")
    return redirect(request.referrer or url_for(".mapa", id=id))


# ---------------------------------------------------------------------------
# Atendimento: entidades em terra
# ---------------------------------------------------------------------------


@bp.route("/<int:id>/atendimento")
def atendimento(id):
    g = _gira(id)
    em_terra = regras.entidades_em_terra(g)
    abertas = {c.entidade_id: c for c in Conversa.query.filter_by(gira_id=id, situacao="chamado")}
    atendidos = dict(db.session.query(Conversa.entidade_id, func.count(Conversa.id))
                     .filter_by(gira_id=id, situacao="atendido").group_by(Conversa.entidade_id).all())
    cambones = {c.entidade_id: c.cambone for c in CamboneGira.query.filter_by(gira_id=id)}
    linhas_em_terra = []
    for e in em_terra:
        if e.linha not in linhas_em_terra:
            linhas_em_terra.append(e.linha)
    # filtro por linha (a escolha fica no endereço, para o recarregar automático manter)
    linha_id = request.args.get("linha", type=int)
    por_linha = {}
    for e in em_terra:
        if linha_id in (None, e.linha_id):
            por_linha.setdefault(e.linha, []).append(e)
    aguardando = sum(1 for i in g.inscricoes if not any(c.situacao == "chamado" for c in i.conversas))
    return render_template("giras/atendimento.html", g=g, por_linha=por_linha, abertas=abertas,
                           atendidos=atendidos, cambones=cambones, aguardando=aguardando,
                           linhas_em_terra=linhas_em_terra, linha_id=linha_id,
                           ocupadas=len(abertas))


@bp.route("/<int:id>/entidade/<int:ent_id>")
def entidade(id, ent_id):
    g = _gira(id)
    ent = db.get_or_404(Entidade, ent_id)
    aberta = regras.conversa_aberta_da_entidade(g, ent)
    sugestoes = regras.sugestoes(g, ent)
    cambones = Pessoa.query.filter(Pessoa.categoria.in_(CATEGORIAS_MEDIUNS), Pessoa.ativo.is_(True)) \
        .order_by(Pessoa.nome).all()
    cambones.sort(key=lambda p: (not p.tem_funcao("Cambone"), chave(p.nome)))
    atendidos = (Conversa.query.filter_by(gira_id=id, entidade_id=ent_id)
                 .filter(Conversa.situacao != "chamado").order_by(Conversa.encerrado_em.desc()).all())
    pedidos_autorizacao = []
    if aberta and regras.eh_sete_flechas(ent):
        pedidos_autorizacao = [p for p in aberta.inscricao.pedidos
                               if p.entidade_id and p.situacao == "pendente"]
    return render_template(
        "giras/entidade.html", g=g, ent=ent, aberta=aberta, s=sugestoes,
        cambone=regras.cambone_da_entidade(g, ent), cambones=cambones, atendidos=atendidos,
        presente=ent.medium_id in regras.presentes_ids(g),
        data_retorno=regras.data_retorno_padrao(g), pedidos_autorizacao=pedidos_autorizacao,
        sete_flechas=regras.eh_sete_flechas(ent),
        inscritos=[i for i in g.inscricoes if i.pessoa_id != ent.medium_id],
    )


@bp.route("/<int:id>/entidade/<int:ent_id>/cambone", methods=["POST"])
def definir_cambone(id, ent_id):
    g = _gira(id)
    ent = db.get_or_404(Entidade, ent_id)
    regras.definir_cambone(g, ent, db.session.get(Pessoa, campo_int("cambone_id") or 0))
    return redirect(url_for(".entidade", id=id, ent_id=ent_id))


@bp.route("/<int:id>/entidade/<int:ent_id>/chamar", methods=["POST"])
def chamar(id, ent_id):
    g = _gira(id)
    ent = db.get_or_404(Entidade, ent_id)
    insc = db.session.get(Inscricao, campo_int("inscricao_id") or 0)
    if insc is None:
        flash("Escolha quem vai ser chamado.", "warning")
        return redirect(url_for(".entidade", id=id, ent_id=ent_id))
    liberacao = campo("liberacao_parentesco") if request.form.get("liberar") else None
    try:
        regras.chamar(g, ent, insc, responsavel(), liberacao)
        flash(f"Chamar: {insc.pessoa.nome} → {ent.rotulo}.", "success")
    except regras.ErroGira as erro:
        flash(str(erro), "danger")
    return redirect(url_for(".entidade", id=id, ent_id=ent_id))


@bp.route("/<int:id>/conversas/<int:conversa_id>/encerrar", methods=["POST"])
def encerrar_conversa(id, conversa_id):
    conversa = db.get_or_404(Conversa, conversa_id)
    retorno_em = campo_data("retorno_em") if request.form.get("teve_retorno") else None
    if request.form.get("teve_retorno") and not retorno_em:
        flash("Informe a data do retorno.", "danger")
    else:
        try:
            regras.encerrar(conversa, campo("situacao") or "atendido", responsavel(),
                            retorno_em, campo("retorno_obs"))
            msg = f"{conversa.inscricao.pessoa.nome_curto}: {conversa.rotulo_situacao.lower()}"
            if retorno_em:
                msg += f", retorno em {retorno_em:%d/%m}"
            flash(msg + ".", "success")
        except regras.ErroGira as erro:
            flash(str(erro), "warning")
    destino = url_for(".entidade", id=id, ent_id=conversa.entidade_id) if conversa.entidade_id \
        else url_for(".atendimento", id=id)
    return redirect(destino)


@bp.route("/<int:id>/pedidos/<int:pedido_id>", methods=["POST"])
def decidir_pedido(id, pedido_id):
    pedido = db.get_or_404(PedidoSeteFlechas, pedido_id)
    regras.decidir_autorizacao(pedido, request.form.get("decisao") == "autorizar", responsavel())
    flash(f"{pedido.entidade.rotulo if pedido.entidade else 'Pedido'}: {pedido.situacao}.", "success")
    return redirect(request.referrer or url_for(".atendimento", id=id))


# ---------------------------------------------------------------------------
# Mapa da gira (visão parecida com a planilha)
# ---------------------------------------------------------------------------


@bp.route("/<int:id>/mapa")
def mapa(id):
    g = _gira(id)
    linhas = Linha.query.order_by(Linha.ordem).all()
    em_terra = {e.linha_id for e in regras.entidades_em_terra(g)}
    usadas = {c.linha_id for c in g.conversas} | em_terra
    linhas = [l for l in linhas if l.id in usadas]
    celulas = {}
    for c in g.conversas:
        celulas.setdefault((c.inscricao_id, c.linha_id), []).append(c)
    grupos = []
    for categoria in ["Corrente", "Auxiliar", "Colaborador", "Consulente"]:
        itens = [i for i in g.inscricoes if i.categoria == categoria]
        if itens:
            grupos.append((categoria, itens))
    return render_template("giras/mapa.html", g=g, linhas=linhas, celulas=celulas, grupos=grupos)
