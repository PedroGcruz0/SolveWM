from datetime import datetime
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


turmas_disciplinas = db.Table(
    "turmas_disciplinas",
    db.Column("turma_id", db.Integer, db.ForeignKey("turmas.id"), primary_key=True),
    db.Column("disciplina_id", db.Integer, db.ForeignKey("disciplinas.id"), primary_key=True),
)


class Usuario(db.Model, UserMixin):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    def get_id(self):
        return str(self.id)

    def __str__(self):
        return self.nome


class Turma(db.Model):
    __tablename__ = "turmas"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    codigo = db.Column(db.String(32), unique=True, nullable=False)
    descricao = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    disciplinas = db.relationship(
        "Disciplina",
        secondary=turmas_disciplinas,
        back_populates="turmas",
        lazy="subquery",
    )

    def __str__(self):
        return f"{self.nome} ({self.codigo})"


class Matricula(db.Model):
    __tablename__ = "matriculas"

    id = db.Column(db.Integer, primary_key=True)
    turma_id = db.Column(db.Integer, db.ForeignKey("turmas.id"), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    papel = db.Column(db.String(20), nullable=False, default="aluno")
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    turma = db.relationship("Turma", backref=db.backref("matriculas", cascade="all, delete-orphan"))
    usuario = db.relationship("Usuario", backref=db.backref("matriculas", cascade="all, delete-orphan"))

    __table_args__ = (
        db.UniqueConstraint("turma_id", "usuario_id", name="uq_matricula_turma_usuario"),
    )


class Disciplina(db.Model):
    __tablename__ = "disciplinas"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(140), unique=True, nullable=False)
    descricao = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    topicos = db.relationship(
        "Topico",
        backref="disciplina",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="Topico.nome.asc()",
    )

    turmas = db.relationship(
        "Turma",
        secondary=turmas_disciplinas,
        back_populates="disciplinas",
    )

    def __str__(self):
        return self.nome


class Topico(db.Model):
    __tablename__ = "topicos"

    id = db.Column(db.Integer, primary_key=True)
    disciplina_id = db.Column(db.Integer, db.ForeignKey("disciplinas.id"), nullable=False)
    nome = db.Column(db.String(160), nullable=False)
    descricao = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("disciplina_id", "nome", name="uq_topico_disciplina_nome"),
    )

    desafios = db.relationship(
        "Desafio",
        backref="topico",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="Desafio.criado_em.desc()",
    )

    def __str__(self):
        return f"{self.disciplina.nome} — {self.nome}"


class Desafio(db.Model):
    __tablename__ = "desafios"

    id = db.Column(db.Integer, primary_key=True)
    topico_id = db.Column(db.Integer, db.ForeignKey("topicos.id"), nullable=False)

    titulo = db.Column(db.String(160), nullable=False)

    # texto | latex | imagem
    tipo_enunciado = db.Column(db.String(10), nullable=False, default="texto")
    enunciado_texto = db.Column(db.Text)
    enunciado_latex = db.Column(db.Text)
    enunciado_imagem = db.Column(db.String(255))  # só o nome do arquivo

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    perguntas = db.relationship(
        "Pergunta",
        backref="desafio",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="Pergunta.ordem.asc()",
    )

    def __str__(self):
        return f"{self.topico} — {self.titulo}"


class Pergunta(db.Model):
    __tablename__ = "perguntas"

    id = db.Column(db.Integer, primary_key=True)
    desafio_id = db.Column(db.Integer, db.ForeignKey("desafios.id"), nullable=False)

    ordem = db.Column(db.Integer, default=1, nullable=False)
    enunciado = db.Column(db.Text, nullable=False)  # pode ser texto ou latex

    alt_a = db.Column(db.Text, nullable=False)
    alt_b = db.Column(db.Text, nullable=False)
    alt_c = db.Column(db.Text)
    alt_d = db.Column(db.Text)

    correta = db.Column(db.String(1), nullable=False)  # a|b|c|d


class TentativaDesafio(db.Model):
    __tablename__ = "tentativas_desafio"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    turma_id = db.Column(db.Integer, db.ForeignKey("turmas.id"), nullable=False)

    desafio_id = db.Column(db.Integer, db.ForeignKey("desafios.id"), nullable=False)
    topico_id = db.Column(db.Integer, db.ForeignKey("topicos.id"), nullable=False)

    iniciado_em = db.Column(db.DateTime, default=datetime.utcnow)
    finalizada = db.Column(db.Boolean, default=False)

    taxa_acerto_final = db.Column(db.Float)
    dominou = db.Column(db.Boolean)

    usuario = db.relationship("Usuario")
    turma = db.relationship("Turma")
    desafio = db.relationship("Desafio")
    topico = db.relationship("Topico")

    interacoes = db.relationship(
        "Interacao",
        backref="tentativa",
        lazy=True,
        cascade="all, delete-orphan",
    )


class Interacao(db.Model):
    __tablename__ = "interacoes"

    id = db.Column(db.Integer, primary_key=True)
    tentativa_id = db.Column(db.Integer, db.ForeignKey("tentativas_desafio.id"), nullable=False)
    pergunta_id = db.Column(db.Integer, db.ForeignKey("perguntas.id"), nullable=False)
    topico_id = db.Column(db.Integer, db.ForeignKey("topicos.id"), nullable=False)

    alternativa = db.Column(db.String(1), nullable=False)
    foi_correta = db.Column(db.Boolean, nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    pergunta = db.relationship("Pergunta")
    topico = db.relationship("Topico")
