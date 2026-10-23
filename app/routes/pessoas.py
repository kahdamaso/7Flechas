import re
from datetime import date

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import (
    CATEGORIAS,
    FUNCOES,
    Entidade,
    Gira,
    HistoricoCategoria,
    Inscricao,
    Linha,
    Parentesco,
    Pessoa,
    PessoaFuncao,
    Retorno,
)
from ..utils import chave, nome_proprio, normalizar_cpf, normalizar_telefone, somente_digitos
from .forms import campo, campo_data, campo_int, responsavel, versao_confere

bp = Blueprint("pessoas", __name__, url_prefix="/pessoas")

TIPOS_PARENTESCO = ["Cônjuge/Namorado(a)", "Pai/Mãe", "Filho(a)", "Irmão(ã)", "Avô/Avó",
                    "Neto(a)", "Tio(a)", "Sobrinho(a)", "Primo(a)", "Parente"]


def _todas_pessoas():
    return Pessoa.query.order_by(Pessoa.nome).all()


def pessoa_do_texto(texto):
    """Interpreta o valor de um campo de busca 'Nome (#12)' e devolve a Pessoa."""
    m = re.search(r"#(\d+)\)?\s*$", texto or "")
    return db.session.get(Pessoa, int(m.group(1))) if m else None


@bp.route("/")
def lista():
    busca = request.args.get("q", "").strip()
    categoria = request.args.get("categoria", "")
    situacao = request.args.get("situacao", "ativos")
    consulta = Pessoa.query
    if busca:
        k = chave(busca)
        filtro = Pessoa.nome_chave.contains(k) | Pessoa.apelido.ilike(f"%{busca}%")
        digitos = somente_digitos(busca)
        if digitos and len(digitos) >= 3:
            filtro = filtro | Pessoa.cpf.contains(digitos) | Pessoa.telefone.contains(digitos)
        consulta = consulta.filter(filtro)
    if categoria in CATEGORIAS:
        consulta = consulta.filter_by(categoria=categoria)
    elif categoria == "mediuns":
        consulta = consulta.filter(Pessoa.categoria != "Consulente")
    if situacao == "ativos":
        consulta = consulta.filter_by(ativo=True)
    elif situacao == "inativos":
        consulta = consulta.filter_by(ativo=False)
    pagina = consulta.order_by(Pessoa.nome).paginate(
        per_page=current_app.config["ITENS_POR_PAGINA"], error_out=False
    )
    return render_template("pessoas/lista.html", pagina=pagina, busca=busca, categoria=categoria,
                           situacao=situacao, categorias=CATEGORIAS)


@bp.route("/<int:id>")
def prontuario(id):
    p = db.get_or_404(Pessoa, id)
    linhas = Linha.query.order_by(Linha.ordem).all()
    parentes = sorted(Parentesco.de(p), key=lambda laco: laco.outra(p).nome)
    retornos = Retorno.query.filter_by(pessoa_id=p.id).order_by(
        (Retorno.situacao != "pendente"), Retorno.data_prevista.desc()).all()
    inscricoes = (Inscricao.query.filter_by(pessoa_id=p.id).join(Gira)
                  .order_by(Gira.data.desc()).all())
    return render_template(
        "pessoas/prontuario.html", p=p, linhas=linhas, parentes=parentes,
        retornos=retornos, inscricoes=inscricoes,
        categorias=CATEGORIAS, tipos_parentesco=TIPOS_PARENTESCO,
        pessoas=_todas_pessoas(), aba=request.args.get("aba", "dados"),
        hoje=date.today().isoformat(),
    )


# ---------------------------------------------------------------------------
# Cadastro e edição
# ---------------------------------------------------------------------------


def _dados_do_form(p, novo):
    """Valida e aplica os campos de cadastro. Devolve lista de erros."""
    erros = []
    nome = nome_proprio(campo("nome"))
    if not nome:
        erros.append("Informe o nome.")
    cpf_digitado = campo("cpf")
    cpf = normalizar_cpf(cpf_digitado)
    if cpf_digitado and not cpf:
        erros.append("CPF inválido.")
    if cpf:
        dono = Pessoa.query.filter(Pessoa.cpf == cpf, Pessoa.id != p.id).first()
        if dono:
            erros.append(f"Este CPF já está cadastrado para {dono.nome}.")
    if nome and novo and not request.form.get("confirmar_homonimo"):
        homonimo = Pessoa.query.filter_by(nome_chave=chave(nome)).first()
        if homonimo:
            erros.append(f"Já existe '{homonimo.nome}' ({homonimo.categoria}). Se for outra "
                         "pessoa, marque 'é outra pessoa com o mesmo nome' e salve de novo.")
    if erros:
        return erros

    p.nome = nome
    p.cpf = cpf
    p.telefone = normalizar_telefone(campo("telefone"))
    p.cidade = nome_proprio(campo("cidade"))
    p.data_nascimento = campo_data("data_nascimento")
    p.outra_casa = campo("outra_casa")
    p.como_soube = campo("como_soube")
    p.observacoes = campo("observacoes")
    p.atualizado_por = responsavel()
    return []


@bp.route("/nova", methods=["GET", "POST"])
def nova():
    p = Pessoa(categoria=request.args.get("categoria", "Consulente"), ativo=True)
    if request.method == "POST":
        erros = _dados_do_form(p, novo=True)
        categoria = campo("categoria")
        if categoria not in CATEGORIAS:
            erros.append("Categoria inválida.")
        if not erros:
            p.categoria = categoria
            p.historico.append(HistoricoCategoria(de=None, para=categoria, observacao="Cadastro",
                                                  registrado_por=responsavel()))
            db.session.add(p)
            parente = pessoa_do_texto(campo("parente"))
            try:
                db.session.flush()
                if parente:
                    Parentesco.criar(p, parente, campo("tipo_parentesco") or "Parente",
                                     responsavel=responsavel())
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("Não foi possível salvar: CPF já cadastrado em outro aparelho agora há pouco.",
                      "danger")
                return render_template("pessoas/nova.html", p=p, form=request.form,
                                       categorias=CATEGORIAS, pessoas=_todas_pessoas(),
                                       tipos_parentesco=TIPOS_PARENTESCO)
            flash(f"{p.nome} cadastrado(a).", "success")
            if request.form.get("acao") == "outro":
                return redirect(url_for(".nova", categoria=p.categoria))
            return redirect(url_for(".prontuario", id=p.id))
        for e in erros:
            flash(e, "danger")
    return render_template("pessoas/nova.html", p=p, form=request.form, categorias=CATEGORIAS,
                           pessoas=_todas_pessoas(), tipos_parentesco=TIPOS_PARENTESCO)


@bp.route("/<int:id>/editar", methods=["GET", "POST"])
def editar(id):
    p = db.get_or_404(Pessoa, id)
    form = request.form
    if request.method == "POST":
        if not versao_confere(p):
            form = {}
        else:
            erros = _dados_do_form(p, novo=False)
            if not erros:
                p.apelido = campo("apelido")
                p.incorpora = form.get("incorpora") == "on"
                p.ativo = form.get("ativo") == "on"
                marcadas = set(form.getlist("funcoes")) & set(FUNCOES)
                for f in list(p.funcoes):
                    if f.funcao not in marcadas:
                        p.funcoes.remove(f)
                for nome_funcao in marcadas - set(p.nomes_funcoes):
                    p.funcoes.append(PessoaFuncao(funcao=nome_funcao, desde=campo_data("desde")))
                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    flash("Este CPF acabou de ser cadastrado para outra pessoa.", "danger")
                    p = db.get_or_404(Pessoa, id)
                    return render_template("pessoas/editar.html", p=p, form={}, funcoes=FUNCOES)
                flash("Cadastro atualizado.", "success")
                return redirect(url_for(".prontuario", id=p.id))
            db.session.rollback()
            for e in erros:
                flash(e, "danger")
            p = db.get_or_404(Pessoa, id)
    return render_template("pessoas/editar.html", p=p, form=form, funcoes=FUNCOES)


@bp.route("/<int:id>/categoria", methods=["POST"])
def mudar_categoria(id):
    p = db.get_or_404(Pessoa, id)
    nova_categoria = campo("categoria")
    if nova_categoria not in CATEGORIAS:
        flash("Categoria inválida.", "danger")
    elif versao_confere(p):
        anterior = p.categoria
        if p.mudar_categoria(nova_categoria, campo_data("data"), campo("observacao"), responsavel()):
            p.atualizado_por = responsavel()
            db.session.commit()
            flash(f"{p.nome}: {anterior} → {nova_categoria}.", "success")
    return redirect(url_for(".prontuario", id=id, aba="historico"))


@bp.route("/<int:id>/excluir", methods=["POST"])
def excluir(id):
    p = db.get_or_404(Pessoa, id)
    db.session.delete(p)
    db.session.commit()
    flash(f"{p.nome} excluído(a).", "success")
    return redirect(url_for(".lista"))


# ---------------------------------------------------------------------------
# Parentes
# ---------------------------------------------------------------------------


@bp.route("/<int:id>/parentes", methods=["POST"])
def adicionar_parente(id):
    p = db.get_or_404(Pessoa, id)
    parente = pessoa_do_texto(campo("parente"))
    if parente is None:
        flash("Escolha o parente na lista (digite o nome e selecione).", "danger")
    elif parente.id == p.id:
        flash("Escolha outra pessoa.", "danger")
    else:
        try:
            Parentesco.criar(p, parente, campo("tipo") or "Parente", campo("observacao"),
                             responsavel())
            db.session.commit()
            flash(f"Parentesco com {parente.nome} registrado.", "success")
        except IntegrityError:  # o mesmo laço criado em outro aparelho ao mesmo tempo
            db.session.rollback()
    return redirect(url_for(".prontuario", id=id, aba="parentes"))


@bp.route("/<int:id>/parentes/<int:laco_id>/excluir", methods=["POST"])
def remover_parente(id, laco_id):
    laco = db.get_or_404(Parentesco, laco_id)
    if id in (laco.pessoa_a_id, laco.pessoa_b_id):
        db.session.delete(laco)
        db.session.commit()
        flash("Parentesco removido.", "success")
    return redirect(url_for(".prontuario", id=id, aba="parentes"))


# ---------------------------------------------------------------------------
# Ficha espiritual
# ---------------------------------------------------------------------------


@bp.route("/<int:id>/entidades", methods=["POST"])
def adicionar_entidade(id):
    p = db.get_or_404(Pessoa, id)
    linha = db.session.get(Linha, campo_int("linha_id") or 0)
    if linha is None:
        flash("Escolha a linha.", "danger")
    else:
        try:
            p.entidades.append(Entidade(linha=linha, nome=campo("nome")))
            p.incorpora = True
            db.session.commit()
            flash("Entidade adicionada à ficha.", "success")
        except IntegrityError:
            db.session.rollback()
            flash("Essa entidade já está na ficha.", "warning")
    return redirect(url_for(".prontuario", id=id, aba="ficha"))
