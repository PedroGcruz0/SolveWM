from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError

from .modelos import Usuario, Turma


class FormEntrar(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    senha = PasswordField("Senha", validators=[DataRequired(), Length(min=3, max=64)])
    lembrar = BooleanField("Lembrar de mim")
    enviar = SubmitField("Entrar")


class FormCadastro(FlaskForm):
    nome = StringField("Nome", validators=[DataRequired(), Length(min=2, max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    codigo_turma = StringField("Código da turma", validators=[DataRequired(), Length(min=2, max=32)])

    senha = PasswordField("Senha", validators=[DataRequired(), Length(min=3, max=64)])
    senha2 = PasswordField("Confirmar senha", validators=[DataRequired(), EqualTo("senha")])

    enviar = SubmitField("Cadastrar")

    def validate_email(self, field):
        if Usuario.query.filter_by(email=field.data.strip().lower()).first():
            raise ValidationError("Email já cadastrado.")

    def validate_codigo_turma(self, field):
        codigo = field.data.strip()
        if not Turma.query.filter_by(codigo=codigo).first():
            raise ValidationError("Código de turma inválido. Peça ao professor.")
