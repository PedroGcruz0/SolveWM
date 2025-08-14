# config.py
import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'chave-secreta-para-desenvolvimento')
    
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'instance', 'app.db')
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Define a pasta de uploads na raiz do projeto
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')