import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-chave-local")

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or (
        "sqlite:///" + os.path.join(BASE_DIR, "instance", "app.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Flask-Admin / Babel
    BABEL_DEFAULT_LOCALE = "pt_BR"
    BABEL_DEFAULT_TIMEZONE = "America/Sao_Paulo"

    # uploads ficam em /static/uploads (servidos pelo Flask)
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "app", "static", "uploads")
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
