# create_admin.py
from app import create_app
from app.modelos import db, Usuario
from werkzeug.security import generate_password_hash
import getpass # Usaremos getpass para esconder a senha

def criar_admin():
    """
    Script para criar um novo usuário administrador.
    """
    # Cria uma instância do aplicativo para termos o contexto do banco de dados
    app = create_app()

    with app.app_context():
        print("\n--- Criação de Usuário Administrador ---")
        
        # Pede os dados do novo admin
        nome = input("Digite o nome do administrador: ")
        email = input("Digite o e-mail do administrador: ")
        # Usa getpass para que a senha não apareça na tela ao ser digitada
        senha = getpass.getpass("Digite a senha do administrador: ")

        # Verifica se o e-mail já existe
        if Usuario.query.filter_by(email=email).first():
            print(f"\n[ERRO] O e-mail '{email}' já existe no banco de dados.")
            return

        # Cria o hash da senha para segurança
        senha_hash = generate_password_hash(senha)

        # Cria o novo usuário com a flag de admin como True
        novo_admin = Usuario(
            nome=nome,
            email=email,
            senha=senha_hash,
            is_admin=True
        )

        # Adiciona ao banco de dados
        db.session.add(novo_admin)
        db.session.commit()

        print(f"\n[SUCESSO] Usuário administrador '{nome}' criado com sucesso!")

# Verifica se o script está sendo executado diretamente
if __name__ == '__main__':
    criar_admin()