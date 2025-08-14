# app/models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import UserMixin

db = SQLAlchemy()

class Usuario(db.Model, UserMixin):
    __tablename__ = 'usuarios'
    user_id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    senha = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_id(self):
        return self.user_id
    
    def __str__(self):
        return self.nome

class TiposIndeterminacao(db.Model):
    __tablename__ = 'tipos_indeterminacao'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)
    descricao = db.Column(db.Text)
    limites = db.relationship('Limite', back_populates='tipo', lazy=True)

    def __str__(self):
        return self.nome

class Estrategia(db.Model):
    __tablename__ = 'estrategias'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)
    descricao = db.Column(db.Text)
    limites = db.relationship('Limite', back_populates='estrategia', lazy=True)

    def __str__(self):
        return self.nome

class Limite(db.Model):
    __tablename__ = 'limites'
    id = db.Column(db.Integer, primary_key=True)
    tipo_id = db.Column(db.Integer, db.ForeignKey('tipos_indeterminacao.id'), nullable=False)
    estrategia_id = db.Column(db.Integer, db.ForeignKey('estrategias.id'), nullable=False)
    latex_str = db.Column(db.Text, nullable=False)
    resposta_final = db.Column(db.String(100), nullable=False)
    
    tipo = db.relationship('TiposIndeterminacao', back_populates='limites')
    estrategia = db.relationship('Estrategia', back_populates='limites')
    perguntas = db.relationship('PerguntasEstrategicas', back_populates='limite', lazy=True, cascade="all, delete-orphan")
    
    def __str__(self):
        return f"ID {self.id}: {self.latex_str[:30]}..."

class PerguntasEstrategicas(db.Model):
    __tablename__ = 'perguntas_estrategicas'
    id = db.Column(db.Integer, primary_key=True)
    limite_id = db.Column(db.Integer, db.ForeignKey('limites.id'), nullable=False)
    texto_pergunta = db.Column(db.Text, nullable=False)
    ordem = db.Column(db.Integer)
    alternativa_a = db.Column(db.Text)
    alternativa_b = db.Column(db.Text)
    alternativa_c = db.Column(db.Text)
    alternativa_d = db.Column(db.Text)
    resposta_correta = db.Column(db.String(1), nullable=False)
    limite = db.relationship('Limite', back_populates='perguntas')

class TentativasLimites(db.Model):
    __tablename__ = 'tentativas_limites'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.user_id'), nullable=False)
    limite_id = db.Column(db.Integer, db.ForeignKey('limites.id'), nullable=False)
    timestamp_inicio = db.Column(db.DateTime, default=datetime.utcnow)
    finalizada = db.Column(db.Boolean, default=False)
    taxa_acerto_final = db.Column(db.Float)
    dominou_limite = db.Column(db.Boolean)
    
    limite = db.relationship('Limite')
    interacoes = db.relationship('InteracoesUsuarios', backref='tentativa', lazy=True, cascade="all, delete-orphan")

class InteracoesUsuarios(db.Model):
    __tablename__ = 'interacoes_usuarios'
    id = db.Column(db.Integer, primary_key=True)
    tentativa_id = db.Column(db.Integer, db.ForeignKey('tentativas_limites.id'), nullable=False)
    pergunta_id = db.Column(db.Integer, db.ForeignKey('perguntas_estrategicas.id'), nullable=False)
    limite_id = db.Column(db.Integer, db.ForeignKey('limites.id'), nullable=False)
    alternativa_escolhida = db.Column(db.String(1), nullable=False)
    foi_correta = db.Column(db.Boolean, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)