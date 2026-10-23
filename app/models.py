"""Modelo de dados do TUC7FJ — Fase 1 (cadastros e ficha espiritual).

Visão geral
-----------
- ``Pessoa``              qualquer pessoa da casa ou do público. A mesma pessoa
                          evolui: Consulente -> Colaborador -> Auxiliar -> Corrente.
- ``PessoaFuncao``        funções exercidas (Cambone, Ogã).
- ``HistoricoCategoria``  cada mudança de categoria, com data.
- ``Parentesco``          laço entre duas pessoas. Quem é parente de um médium
                          não pode conversar com as entidades dele.
- ``Linha``               linhas de trabalho (Caboclo, Preto Velho, Exu...).
- ``Entidade``            guia que um médium incorpora numa linha. Sem nome
                          ainda? Fica identificada pelo médium ("Exu da Jessica").
- ``Configuracao``        parâmetros da casa (senha de acesso).

Uso simultâneo: os registros editáveis têm a coluna ``versao`` (controle
otimista do SQLAlchemy). Se dois aparelhos abrem o mesmo cadastro e ambos
salvam, o segundo é avisado em vez de apagar sem perceber o que o primeiro fez.
"""

from datetime import date, datetime

from sqlalchemy.orm import declared_attr
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db
from .utils import chave

CATEGORIAS = ["Consulente", "Colaborador", "Auxiliar", "Corrente"]
# categorias que formam o corpo mediúnico da casa (fazem chamada na gira)
CATEGORIAS_MEDIUNS = ["Colaborador", "Auxiliar", "Corrente"]
FUNCOES = ["Cambone", "Ogã"]


class TimestampMixin:
    criado_em = db.Column(db.DateTime, default=datetime.now, nullable=False)
    atualizado_em = db.Column(
        db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )
    # nome do responsável do dia que fez o último lançamento
    atualizado_por = db.Column(db.String(100))


class VersaoMixin:
    """Incrementa ``versao`` a cada UPDATE; o UPDATE falha (StaleDataError) se
    outro aparelho tiver salvo uma versão mais nova nesse meio-tempo."""

    versao = db.Column(db.Integer, nullable=False, default=1)

    @declared_attr.directive
    def __mapper_args__(cls):
        return {"version_id_col": cls.versao}


class Pessoa(VersaoMixin, TimestampMixin, db.Model):
    __tablename__ = "pessoas"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    nome_chave = db.Column(db.String(150), nullable=False, index=True)
    # como a pessoa é chamada na casa ("Pai Igor", "Thiago DV")
    apelido = db.Column(db.String(60))
    cpf = db.Column(db.String(11), unique=True)  # só dígitos
    data_nascimento = db.Column(db.Date)
    telefone = db.Column(db.String(20))
    cidade = db.Column(db.String(80))
    outra_casa = db.Column(db.String(150))  # vínculo com outra casa/religião
    como_soube = db.Column(db.String(150))
    # texto do parentesco como veio da planilha, para conferência
    parentesco_informado = db.Column(db.String(150))
    categoria = db.Column(db.String(20), nullable=False, default="Consulente")
    incorpora = db.Column(db.Boolean, nullable=False, default=False)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    observacoes = db.Column(db.Text)

    funcoes = db.relationship(
        "PessoaFuncao", back_populates="pessoa", cascade="all, delete-orphan"
    )
    historico = db.relationship(
        "HistoricoCategoria", back_populates="pessoa", cascade="all, delete-orphan",
        order_by="(HistoricoCategoria.data.desc(), HistoricoCategoria.id.desc())",
    )
    entidades = db.relationship(
        "Entidade", back_populates="medium", cascade="all, delete-orphan",
    )

    @db.validates("nome")
    def _set_chave(self, _key, nome):
        self.nome_chave = chave(nome)
        return nome

    @property
    def eh_medium(self):
        return self.categoria in CATEGORIAS_MEDIUNS

    @property
    def nome_curto(self):
        return self.apelido or self.nome.split(" ")[0]

    @property
    def nomes_funcoes(self):
        return sorted(f.funcao for f in self.funcoes)

    def tem_funcao(self, funcao):
        return any(f.funcao == funcao for f in self.funcoes)

    def mudar_categoria(self, nova, quando=None, observacao=None, responsavel=None):
        """Troca a categoria guardando o histórico. Devolve False se não mudou."""
        if nova == self.categoria:
            return False
        self.historico.append(HistoricoCategoria(
            de=self.categoria, para=nova, data=quando or date.today(),
            observacao=observacao, registrado_por=responsavel,
        ))
        self.categoria = nova
        return True

    def __repr__(self):
        return f"<Pessoa {self.nome} ({self.categoria})>"


class PessoaFuncao(db.Model):
    __tablename__ = "pessoa_funcoes"
    __table_args__ = (db.UniqueConstraint("pessoa_id", "funcao"),)

    id = db.Column(db.Integer, primary_key=True)
    pessoa_id = db.Column(
        db.Integer, db.ForeignKey("pessoas.id", ondelete="CASCADE"), nullable=False
    )
    funcao = db.Column(db.String(30), nullable=False)
    desde = db.Column(db.Date)

    pessoa = db.relationship("Pessoa", back_populates="funcoes")


class HistoricoCategoria(db.Model):
    __tablename__ = "historico_categorias"

    id = db.Column(db.Integer, primary_key=True)
    pessoa_id = db.Column(
        db.Integer, db.ForeignKey("pessoas.id", ondelete="CASCADE"), nullable=False
    )
    de = db.Column(db.String(20))
    para = db.Column(db.String(20), nullable=False)
    data = db.Column(db.Date, nullable=False, default=date.today)
    observacao = db.Column(db.String(200))
    registrado_por = db.Column(db.String(100))
    registrado_em = db.Column(db.DateTime, default=datetime.now, nullable=False)

    pessoa = db.relationship("Pessoa", back_populates="historico")


class Parentesco(db.Model):
    """Laço entre duas pessoas, guardado uma única vez (pessoa_a_id < pessoa_b_id)."""

    __tablename__ = "parentescos"
    __table_args__ = (
        db.UniqueConstraint("pessoa_a_id", "pessoa_b_id"),
        db.CheckConstraint("pessoa_a_id < pessoa_b_id", name="ck_parentesco_ordem"),
    )

    id = db.Column(db.Integer, primary_key=True)
    pessoa_a_id = db.Column(
        db.Integer, db.ForeignKey("pessoas.id", ondelete="CASCADE"), nullable=False
    )
    pessoa_b_id = db.Column(
        db.Integer, db.ForeignKey("pessoas.id", ondelete="CASCADE"), nullable=False
    )
    tipo = db.Column(db.String(60), nullable=False, default="Parente")
    observacao = db.Column(db.String(200))
    registrado_por = db.Column(db.String(100))
    registrado_em = db.Column(db.DateTime, default=datetime.now, nullable=False)

    pessoa_a = db.relationship("Pessoa", foreign_keys=[pessoa_a_id])
    pessoa_b = db.relationship("Pessoa", foreign_keys=[pessoa_b_id])

    def outra(self, pessoa):
        return self.pessoa_b if self.pessoa_a_id == pessoa.id else self.pessoa_a

    @staticmethod
    def entre(pessoa1_id, pessoa2_id):
        a, b = sorted((pessoa1_id, pessoa2_id))
        return Parentesco.query.filter_by(pessoa_a_id=a, pessoa_b_id=b).first()

    @staticmethod
    def de(pessoa):
        return Parentesco.query.filter(
            (Parentesco.pessoa_a_id == pessoa.id) | (Parentesco.pessoa_b_id == pessoa.id)
        ).all()

    @staticmethod
    def criar(pessoa1, pessoa2, tipo="Parente", observacao=None, responsavel=None):
        """Cria o laço se ainda não existir; devolve o registro (novo ou existente)."""
        existente = Parentesco.entre(pessoa1.id, pessoa2.id)
        if existente:
            return existente
        a, b = sorted((pessoa1, pessoa2), key=lambda p: p.id)
        laco = Parentesco(pessoa_a=a, pessoa_b=b, tipo=tipo, observacao=observacao,
                          registrado_por=responsavel)
        db.session.add(laco)
        return laco


class Linha(db.Model):
    __tablename__ = "linhas"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(60), nullable=False, unique=True)
    ordem = db.Column(db.Integer, nullable=False, default=0)

    entidades = db.relationship("Entidade", back_populates="linha")

    def __repr__(self):
        return f"<Linha {self.nome}>"


class Entidade(VersaoMixin, db.Model):
    """Guia que um médium incorpora numa linha."""

    __tablename__ = "entidades"
    __table_args__ = (db.UniqueConstraint("medium_id", "linha_id", "nome_chave"),)

    id = db.Column(db.Integer, primary_key=True)
    medium_id = db.Column(
        db.Integer, db.ForeignKey("pessoas.id", ondelete="CASCADE"), nullable=False
    )
    linha_id = db.Column(db.Integer, db.ForeignKey("linhas.id"), nullable=False)
    # vazio enquanto a entidade não deu o nome
    nome = db.Column(db.String(100))
    nome_chave = db.Column(db.String(100), nullable=False, default="")
    ativa = db.Column(db.Boolean, nullable=False, default=True)
    observacoes = db.Column(db.Text)

    medium = db.relationship("Pessoa", back_populates="entidades")
    linha = db.relationship("Linha", back_populates="entidades")

    @db.validates("nome")
    def _set_chave(self, _key, nome):
        self.nome_chave = chave(nome)
        return nome

    @property
    def rotulo(self):
        """Nome para exibir: 'Juruá' ou, sem nome, 'Exu da Jessica'."""
        if self.nome:
            return self.nome
        return f"{self.linha.nome} de {self.medium.nome_curto}"

    def __repr__(self):
        return f"<Entidade {self.rotulo}>"


class Configuracao(db.Model):
    __tablename__ = "configuracoes"

    chave = db.Column(db.String(60), primary_key=True)
    valor = db.Column(db.Text)

    @staticmethod
    def obter(chave_cfg, padrao=None):
        item = db.session.get(Configuracao, chave_cfg)
        return item.valor if item else padrao

    @staticmethod
    def definir(chave_cfg, valor):
        item = db.session.get(Configuracao, chave_cfg) or Configuracao(chave=chave_cfg)
        item.valor = valor
        db.session.add(item)


def senha_configurada():
    return Configuracao.obter("senha_casa") is not None


def definir_senha_casa(senha):
    Configuracao.definir("senha_casa", generate_password_hash(senha))


def confere_senha_casa(senha):
    hash_salvo = Configuracao.obter("senha_casa")
    return bool(hash_salvo) and check_password_hash(hash_salvo, senha)


# Linhas de trabalho, na ordem das planilhas.
LINHAS_PADRAO = [
    "Caboclo", "Preto Velho", "Baiano", "Boiadeiro", "Povo d'Água", "Cigano", "Erê",
    "Exu", "Exu Mirim", "Pomba Gira", "Pomba Gira Mirim", "Malandragem", "Mestres",
    "Princesas", "Cangaço",
]


def garantir_linhas_padrao():
    existentes = {chave(l.nome) for l in Linha.query.all()}
    for ordem, nome in enumerate(LINHAS_PADRAO):
        if chave(nome) not in existentes:
            db.session.add(Linha(nome=nome, ordem=ordem))
    db.session.commit()
