# app/__init__.py
from flask import Flask
from config import Config
from .models import db, Usuario
from .routes import main_bp
from .admin import setup_admin
from flask_login import LoginManager
from pix2tex.cli import LatexOCR
from flask_babel import Babel  # 1. Importa a biblioteca Babel
import os

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    # Garante que as pastas necessárias existam
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # --- CONFIGURAÇÃO DE IDIOMA ---
    app.config['BABEL_DEFAULT_LOCALE'] = 'pt_BR'  # 2. Define o idioma padrão
    babel = Babel(app)                             # 3. Inicializa o Babel com o app
    # --- FIM DA CONFIGURAÇÃO DE IDIOMA ---

    # Inicializa as outras extensões
    db.init_app(app)
    setup_admin(app)

    login_manager = LoginManager()
    login_manager.login_view = 'main.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return Usuario.query.get(int(user_id))

    # Carrega o modelo de IA
    print("Carregando modelo LaTeX-OCR...")
    app.latex_ocr_model = LatexOCR()
    print("Modelo LaTeX-OCR carregado com sucesso.")

    # Cria as tabelas do banco de dados
    with app.app_context():
        db.create_all()

    # Registra as rotas
    app.register_blueprint(main_bp)

    return app