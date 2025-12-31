import os
from flask import Flask
from flask_login import LoginManager
from flask_babel import Babel

from config import Config
from .modelos import db, Usuario
from .rotas import site_bp
from .painel_admin import configurar_admin


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    Babel(app)

    db.init_app(app)

    login = LoginManager()
    login.login_view = "site.entrar"
    login.init_app(app)

    @login.user_loader
    def load_user(user_id):
        return db.session.get(Usuario, int(user_id))

    with app.app_context():
        db.create_all()

    app.register_blueprint(site_bp)
    configurar_admin(app)
    return app
