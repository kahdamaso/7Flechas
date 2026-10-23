from datetime import date

from app.extensions import db
from app.models import Entidade, Linha, Parentesco, Pessoa
from app.utils import chave

from .conftest import SENHA, recarregar


def _cadastrar(client, nome, categoria="Consulente", **extra):
    dados = {"nome": nome, "categoria": categoria, **extra}
    resp = client.post("/pessoas/nova", data=dados)
    return resp, Pessoa.query.filter_by(nome_chave=chave(nome)).order_by(Pessoa.id.desc()).first()


# --- acesso -----------------------------------------------------------------


def test_primeiro_uso_define_senha_e_pede_responsavel(anonimo):
    assert anonimo.get("/").headers["Location"].endswith("/configurar")
    resp = anonimo.post("/configurar", data={"senha": "abc", "senha2": "abc"})
    assert "pelo menos 6" in resp.get_data(as_text=True)
    resp = anonimo.post("/configurar", data={"senha": "segredo1", "senha2": "segredo1"})
    assert "/responsavel" in resp.headers["Location"]
    assert "/responsavel" in anonimo.get("/").headers["Location"]
    anonimo.post("/responsavel", data={"responsavel": "Ana"})
    pagina = anonimo.get("/").get_data(as_text=True)
    assert "Responsável: <strong>Ana</strong>" in pagina


def test_senha_errada_e_bloqueio(client, app):
    outro = app.test_client()
    assert "/entrar" in outro.get("/pessoas/").headers["Location"]
    for _ in range(5):
        assert "Senha incorreta" in outro.post("/entrar", data={"senha": "x"}).get_data(as_text=True)
    resp = outro.post("/entrar", data={"senha": SENHA})
    assert "Muitas tentativas" in resp.get_data(as_text=True)


def test_redirecionamento_externo_bloqueado(app, client):
    resp = client.post("/responsavel?proximo=//evil.com", data={"responsavel": "X"})
    assert resp.headers["Location"] == "/"


def test_responsavel_vale_so_no_dia(client):
    with client.session_transaction() as s:
        s["responsavel_dia"] = "2000-01-01"
    assert "/responsavel" in client.get("/").headers["Location"]


# --- telas ------------------------------------------------------------------


def test_telas_abrem(client):
    _, p = _cadastrar(client, "Fulano de Tal", "Corrente")
    ent = Entidade(medium=p, linha=Linha.query.first(), nome="Juruá")
    db.session.add(ent)
    db.session.commit()
    for url in ["/", "/pessoas/", "/pessoas/?q=fulano&categoria=mediuns&situacao=todos",
                "/pessoas/nova", f"/pessoas/{p.id}", f"/pessoas/{p.id}?aba=ficha",
                f"/pessoas/{p.id}/editar", "/entidades/", "/entidades/?q=jur",
                f"/entidades/{ent.id}/editar", "/senha", "/responsavel"]:
        assert client.get(url).status_code == 200, url


# --- pessoas ----------------------------------------------------------------


def test_cadastro_rapido(client):
    resp, p = _cadastrar(client, "MARIA DE TESTE", cpf="529.982.247-25", telefone="(37) 99999-1111",
                         cidade="bom despacho", outra_casa="Oásis")
    assert resp.status_code == 302
    assert p.nome == "Maria de Teste" and p.cpf == "52998224725" and p.telefone == "37999991111"
    assert p.outra_casa == "Oásis" and p.atualizado_por == "Secretaria"
    assert [(h.de, h.para) for h in p.historico] == [(None, "Consulente")]

    # CPF repetido é recusado
    resp, _ = _cadastrar(client, "Outra Pessoa", cpf="52998224725")
    assert "já está cadastrado para Maria de Teste" in resp.get_data(as_text=True)
    # nome repetido pede confirmação
    resp, _ = _cadastrar(client, "Maria de Teste")
    assert "Já existe" in resp.get_data(as_text=True)
    assert Pessoa.query.filter_by(nome="Maria de Teste").count() == 1
    _cadastrar(client, "Maria de Teste", confirmar_homonimo="on")
    assert Pessoa.query.filter_by(nome="Maria de Teste").count() == 2


def test_cadastro_com_parente(client):
    _, medium = _cadastrar(client, "Jurema Medium", "Corrente")
    _, p = _cadastrar(client, "Namorado Teste", parente=f"Jurema Medium (#{medium.id})",
                      tipo_parentesco="Cônjuge/Namorado(a)")
    laco = Parentesco.entre(p.id, medium.id)
    assert laco.tipo == "Cônjuge/Namorado(a)" and laco.registrado_por == "Secretaria"
    pagina = client.get(f"/pessoas/{p.id}").get_data(as_text=True)
    assert "Parentes na casa" in pagina and "Jurema" in pagina


def test_editar_funcoes_e_conflito_de_versao(client):
    _, p = _cadastrar(client, "Cambone Teste", "Auxiliar")
    versao = p.versao
    client.post(f"/pessoas/{p.id}/editar", data={
        "versao": versao, "nome": "Cambone Teste", "apelido": "Cambi", "funcoes": ["Cambone", "Ogã"],
        "ativo": "on"})
    p = recarregar(Pessoa, p.id)
    assert p.apelido == "Cambi" and p.nomes_funcoes == ["Cambone", "Ogã"] and not p.incorpora

    # outro aparelho envia o formulário aberto antes da alteração acima
    resp = client.post(f"/pessoas/{p.id}/editar", data={
        "versao": versao, "nome": "Nome Antigo", "ativo": "on"})
    assert "alterado em outro aparelho" in resp.get_data(as_text=True)
    assert recarregar(Pessoa, p.id).nome == "Cambone Teste"


def test_mudar_categoria_registra_historico(client):
    _, p = _cadastrar(client, "Em Evolucao")
    hoje = date.today().isoformat()
    client.post(f"/pessoas/{p.id}/categoria", data={
        "categoria": "Colaborador", "data": hoje, "observacao": "Convite do Sete Flechas"})
    client.post(f"/pessoas/{p.id}/categoria", data={"categoria": "Auxiliar"})
    p = recarregar(Pessoa, p.id)
    assert p.categoria == "Auxiliar"
    assert [(h.de, h.para) for h in p.historico] == [
        ("Colaborador", "Auxiliar"), ("Consulente", "Colaborador"), (None, "Consulente")]
    assert p.historico[1].data == date.today()
    assert p.historico[1].observacao == "Convite do Sete Flechas"


def test_parentes_e_ficha(client):
    _, a = _cadastrar(client, "Pessoa A", "Corrente")
    _, b = _cadastrar(client, "Pessoa B")
    client.post(f"/pessoas/{b.id}/parentes", data={"parente": f"Pessoa A (#{a.id})", "tipo": "Irmão(ã)"})
    client.post(f"/pessoas/{a.id}/parentes", data={"parente": f"Pessoa B (#{b.id})"})  # repetido
    assert Parentesco.query.count() == 1
    laco = Parentesco.entre(a.id, b.id)
    client.post(f"/pessoas/{a.id}/parentes/{laco.id}/excluir")
    assert Parentesco.query.count() == 0

    exu = Linha.query.filter_by(nome="Exu").one()
    client.post(f"/pessoas/{a.id}/entidades", data={"linha_id": exu.id, "nome": ""})
    client.post(f"/pessoas/{a.id}/entidades", data={"linha_id": exu.id, "nome": "Tranca Rua"})
    a = recarregar(Pessoa, a.id)
    assert a.incorpora
    assert sorted(e.rotulo for e in a.entidades) == ["Exu de Pessoa", "Tranca Rua"]
    sem_nome = next(e for e in a.entidades if not e.nome)
    client.post(f"/entidades/{sem_nome.id}/editar", data={
        "versao": sem_nome.versao, "linha_id": exu.id, "nome": "Marabô", "ativa": "on"})
    assert recarregar(Entidade, sem_nome.id).rotulo == "Marabô"
    client.post(f"/entidades/{sem_nome.id}/excluir")
    assert Entidade.query.count() == 1


def test_busca(client):
    _cadastrar(client, "José da Silva", cpf="529.982.247-25", telefone="37988776655")
    for termo in ["jose", "JOSÉ", "529982", "88776"]:
        assert "José da Silva" in client.get(f"/pessoas/?q={termo}").get_data(as_text=True), termo


def test_ip_real_atras_de_proxy(anonimo, app):
    """Com ATRAS_DE_PROXY, o bloqueio por senha errada vale por aparelho, não para todos."""
    from werkzeug.middleware.proxy_fix import ProxyFix

    from app.models import definir_senha_casa

    definir_senha_casa(SENHA)
    db.session.commit()
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
    for _ in range(5):
        anonimo.post("/entrar", data={"senha": "x"}, headers={"X-Forwarded-For": "10.0.0.1"})
    bloqueado = anonimo.post("/entrar", data={"senha": SENHA}, headers={"X-Forwarded-For": "10.0.0.1"})
    assert "Muitas tentativas" in bloqueado.get_data(as_text=True)
    outro = anonimo.post("/entrar", data={"senha": SENHA}, headers={"X-Forwarded-For": "10.0.0.2"})
    assert "/responsavel" in outro.headers["Location"]
