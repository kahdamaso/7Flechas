"""Modelo relacional do TUC7FJ.

Visão geral
-----------
- ``Medium``         membros da casa (Corrente, Auxiliares, Colaboradores).
- ``Consulente``     visitantes atendidos nas giras.
- ``Linha``          linhas de trabalho (Caboclo, Exu, Preto Velho...). Também
                     inclui os "serviços" das planilhas (7 Flechas, Maca).
- ``Entidade``       guias espirituais, sempre pertencentes a uma linha.
- ``MediumEntidade`` quais entidades cada médium trabalha (RETORNO_MEDIUNS).
- ``Sessao``         uma gira/sessão em uma data.
- ``Presenca``       presença de cada médium em uma sessão.
- ``Atendimento``    uma pessoa (consulente ou médium) atendida numa sessão,
                     com parentesco/retorno — equivale a uma linha da planilha.
- ``Manifestacao``   cada célula preenchida das colunas de linha: qual entidade
                     (e/ou médium de qual entidade) atendeu naquela linha.
- ``Usuario``        quem pode entrar no sistema.

Uso simultâneo: os registros editáveis têm a coluna ``versao`` (controle
otimista do SQLAlchemy). Se dois aparelhos abrem o mesmo cadastro e ambos
salvam, o segundo é avisado em vez de apagar sem perceber o que o primeiro fez.
"""

from datetime import datetime

from sqlalchemy.orm import declared_attr
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db
from .utils import chave

GRUPOS_MEDIUM = ["Corrente", "Auxiliar", "Colaborador"]


class TimestampMixin:
    criado_em = db.Column(db.DateTime, default=datetime.now, nullable=False)
    atualizado_em = db.Column(
        db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )


class VersaoMixin:
    """Incrementa ``versao`` a cada UPDATE; o UPDATE falha (StaleDataError) se
    outro aparelho tiver salvo uma versão mais nova nesse meio-tempo."""

    versao = db.Column(db.Integer, nullable=False, default=1)

    @declared_attr.directive
    def __mapper_args__(cls):
        return {"version_id_col": cls.versao}


class Medium(VersaoMixin, TimestampMixin, db.Model):
    __tablename__ = "mediuns"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    nome_chave = db.Column(db.String(150), nullable=False, unique=True, index=True)
    apelido = db.Column(db.String(60))  # ex.: "Thiago DV", como aparece nas planilhas
    grupo = db.Column(db.String(20), nullable=False, default="Corrente")
    telefone = db.Column(db.String(20))
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    observacoes = db.Column(db.Text)

    entidades = db.relationship(
        "MediumEntidade", back_populates="medium", cascade="all, delete-orphan"
    )
    presencas = db.relationship(
        "Presenca", back_populates="medium", cascade="all, delete-orphan"
    )
    atendimentos = db.relationship(
        "Atendimento", back_populates="medium", foreign_keys="Atendimento.medium_id",
        cascade="all, delete-orphan", passive_deletes=True,
    )

    @db.validates("nome")
    def _set_chave(self, _key, nome):
        self.nome_chave = chave(nome)
        return nome

    def __repr__(self):
        return f"<Medium {self.nome}>"


class Consulente(VersaoMixin, TimestampMixin, db.Model):
    __tablename__ = "consulentes"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    nome_chave = db.Column(db.String(150), nullable=False, index=True)
    cpf = db.Column(db.String(11), unique=True)  # só dígitos
    data_nascimento = db.Column(db.Date)
    telefone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    endereco = db.Column(db.String(200))
    bairro = db.Column(db.String(80))
    cidade = db.Column(db.String(80))
    uf = db.Column(db.String(2))
    observacoes = db.Column(db.Text)

    atendimentos = db.relationship(
        "Atendimento", back_populates="consulente", cascade="all, delete-orphan", passive_deletes=True
    )

    @db.validates("nome")
    def _set_chave(self, _key, nome):
        self.nome_chave = chave(nome)
        return nome

    def __repr__(self):
        return f"<Consulente {self.nome}>"


class Linha(db.Model):
    __tablename__ = "linhas"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(60), nullable=False, unique=True)
    ordem = db.Column(db.Integer, nullable=False, default=0)
    # "servico" = colunas como 7 Flechas/Maca, cujo conteúdo é o tipo de trabalho
    # (Orientação Espiritual, Consagrar Pano...) e não o nome de uma entidade.
    servico = db.Column(db.Boolean, nullable=False, default=False)

    entidades = db.relationship("Entidade", back_populates="linha", order_by="Entidade.nome")

    def __repr__(self):
        return f"<Linha {self.nome}>"


class Entidade(VersaoMixin, db.Model):
    __tablename__ = "entidades"
    __table_args__ = (db.UniqueConstraint("linha_id", "nome_chave"),)

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    nome_chave = db.Column(db.String(100), nullable=False, index=True)
    linha_id = db.Column(db.Integer, db.ForeignKey("linhas.id"), nullable=False)
    observacoes = db.Column(db.Text)

    linha = db.relationship("Linha", back_populates="entidades")
    mediuns = db.relationship(
        "MediumEntidade", back_populates="entidade", cascade="all, delete-orphan"
    )

    @db.validates("nome")
    def _set_chave(self, _key, nome):
        self.nome_chave = chave(nome)
        return nome

    def __repr__(self):
        return f"<Entidade {self.nome} ({self.linha_id})>"


class MediumEntidade(db.Model):
    __tablename__ = "medium_entidades"
    __table_args__ = (db.UniqueConstraint("medium_id", "entidade_id"),)

    id = db.Column(db.Integer, primary_key=True)
    medium_id = db.Column(
        db.Integer, db.ForeignKey("mediuns.id", ondelete="CASCADE"), nullable=False
    )
    entidade_id = db.Column(
        db.Integer, db.ForeignKey("entidades.id", ondelete="CASCADE"), nullable=False
    )

    medium = db.relationship("Medium", back_populates="entidades")
    entidade = db.relationship("Entidade", back_populates="mediuns")


class Sessao(VersaoMixin, TimestampMixin, db.Model):
    __tablename__ = "sessoes"

    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, index=True)
    tipo = db.Column(db.String(60), nullable=False, default="Gira")
    descricao = db.Column(db.String(200))
    observacoes = db.Column(db.Text)

    presencas = db.relationship(
        "Presenca", back_populates="sessao", cascade="all, delete-orphan"
    )
    atendimentos = db.relationship(
        "Atendimento",
        back_populates="sessao",
        cascade="all, delete-orphan",
        order_by="Atendimento.id",
    )

    def __repr__(self):
        return f"<Sessao {self.data} {self.tipo}>"


class Presenca(db.Model):
    __tablename__ = "presencas"
    __table_args__ = (db.UniqueConstraint("sessao_id", "medium_id"),)

    id = db.Column(db.Integer, primary_key=True)
    sessao_id = db.Column(
        db.Integer, db.ForeignKey("sessoes.id", ondelete="CASCADE"), nullable=False
    )
    medium_id = db.Column(
        db.Integer, db.ForeignKey("mediuns.id", ondelete="CASCADE"), nullable=False
    )
    presente = db.Column(db.Boolean, nullable=False, default=True)
    justificativa = db.Column(db.String(200))

    sessao = db.relationship("Sessao", back_populates="presencas")
    medium = db.relationship("Medium", back_populates="presencas")


# Categoria do atendido, igual aos blocos da planilha de sessão.
CATEGORIAS_ATENDIMENTO = ["Corrente", "Auxiliar", "Colaborador", "Consulente"]


class Atendimento(VersaoMixin, TimestampMixin, db.Model):
    __tablename__ = "atendimentos"
    __table_args__ = (
        db.CheckConstraint(
            "(consulente_id IS NULL) <> (medium_id IS NULL)",
            name="ck_atendimento_uma_pessoa",
        ),
        # uma pessoa tem no máximo um atendimento por sessão: evita que dois
        # aparelhos registrem o mesmo consulente ao mesmo tempo
        db.Index("ux_atendimento_consulente", "sessao_id", "consulente_id", unique=True,
                 sqlite_where=db.text("consulente_id IS NOT NULL")),
        db.Index("ux_atendimento_medium", "sessao_id", "medium_id", unique=True,
                 sqlite_where=db.text("medium_id IS NOT NULL")),
    )

    id = db.Column(db.Integer, primary_key=True)
    sessao_id = db.Column(
        db.Integer, db.ForeignKey("sessoes.id", ondelete="CASCADE"), nullable=False
    )
    categoria = db.Column(db.String(20), nullable=False, default="Consulente")
    # exatamente um dos dois: quem foi atendido
    consulente_id = db.Column(db.Integer, db.ForeignKey("consulentes.id", ondelete="CASCADE"))
    medium_id = db.Column(db.Integer, db.ForeignKey("mediuns.id", ondelete="CASCADE"))
    parentesco = db.Column(db.String(150))
    retorno = db.Column(db.String(150))
    observacoes = db.Column(db.Text)
    atualizado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"))

    sessao = db.relationship("Sessao", back_populates="atendimentos")
    atualizado_por = db.relationship("Usuario")
    consulente = db.relationship("Consulente", back_populates="atendimentos")
    medium = db.relationship("Medium", foreign_keys=[medium_id], back_populates="atendimentos")
    manifestacoes = db.relationship(
        "Manifestacao", back_populates="atendimento", cascade="all, delete-orphan"
    )

    @property
    def pessoa_nome(self):
        pessoa = self.consulente or self.medium
        return pessoa.nome if pessoa else "?"


class Manifestacao(db.Model):
    """Uma célula preenchida das colunas de linha na planilha da sessão.

    ``descricao`` guarda sempre o texto original; ``entidade`` e
    ``medium_responsavel`` são preenchidos quando é possível identificar quem
    atendeu (pelo nome da entidade ou pelo nome do médium). ``geral`` marca o
    valor "GERAL" (qualquer entidade daquela linha).
    """

    __tablename__ = "manifestacoes"

    id = db.Column(db.Integer, primary_key=True)
    atendimento_id = db.Column(
        db.Integer, db.ForeignKey("atendimentos.id", ondelete="CASCADE"), nullable=False
    )
    linha_id = db.Column(db.Integer, db.ForeignKey("linhas.id"), nullable=False)
    entidade_id = db.Column(db.Integer, db.ForeignKey("entidades.id", ondelete="SET NULL"))
    medium_responsavel_id = db.Column(
        db.Integer, db.ForeignKey("mediuns.id", ondelete="SET NULL")
    )
    geral = db.Column(db.Boolean, nullable=False, default=False)
    descricao = db.Column(db.String(150))

    atendimento = db.relationship("Atendimento", back_populates="manifestacoes")
    linha = db.relationship("Linha")
    entidade = db.relationship("Entidade")
    medium_responsavel = db.relationship("Medium")

    @property
    def rotulo(self):
        partes = []
        if self.geral:
            partes.append("Geral")
        if self.entidade:
            partes.append(self.entidade.nome)
        if self.medium_responsavel:
            partes.append(f"({self.medium_responsavel.apelido or self.medium_responsavel.nome})")
        if not partes:
            partes.append(self.descricao or "")
        return " ".join(partes)


class Usuario(db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    login = db.Column(db.String(60), nullable=False, unique=True)
    senha_hash = db.Column(db.String(255), nullable=False)
    admin = db.Column(db.Boolean, nullable=False, default=False)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.now, nullable=False)

    @db.validates("login")
    def _normalizar_login(self, _key, login):
        return login.strip().lower()

    def definir_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def confere_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)


# Linhas padrão, na ordem das colunas das planilhas.
LINHAS_PADRAO = [
    ("7 Flechas", True),
    ("Maca", True),
    ("Caboclo", False),
    ("Boiadeiro", False),
    ("Baiano", False),
    ("Povo d'Água", False),
    ("Preto Velho", False),
    ("Erê", False),
    ("Cigano", False),
    ("Exu", False),
    ("Pombo Gira", False),
    ("Malandragem", False),
    ("Mestres", False),
]


def garantir_linhas_padrao():
    existentes = {chave(l.nome) for l in Linha.query.all()}
    for ordem, (nome, servico) in enumerate(LINHAS_PADRAO):
        if chave(nome) not in existentes:
            db.session.add(Linha(nome=nome, ordem=ordem, servico=servico))
    db.session.commit()
