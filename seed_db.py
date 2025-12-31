from werkzeug.security import generate_password_hash

from app import create_app
from app.modelos import (
    db,
    Usuario,
    Turma,
    Matricula,
    Disciplina,
    Topico,
    Desafio,
    Pergunta,
)

app = create_app()

with app.app_context():
    # Limpa tudo (ordem importa por FK)
    Pergunta.query.delete()
    Desafio.query.delete()
    Topico.query.delete()
    Disciplina.query.delete()
    Matricula.query.delete()
    Turma.query.delete()
    Usuario.query.delete()
    db.session.commit()

    # --- DISCIPLINAS ---
    calc1 = Disciplina(nome="Cálculo I", descricao="Limites, derivadas e integrais.")
    db.session.add(calc1)
    db.session.commit()

    # --- TÓPICOS ---
    t1 = Topico(disciplina_id=calc1.id, nome="Limite por fatoração", descricao="Fatorar e simplificar antes de avaliar.")
    t2 = Topico(disciplina_id=calc1.id, nome="Regra da cadeia", descricao="Derivada de função composta.")
    t3 = Topico(disciplina_id=calc1.id, nome="Substituição (u-sub)", descricao="Integração por substituição.")
    db.session.add_all([t1, t2, t3])
    db.session.commit()

    # --- TURMA ---
    turma101 = Turma(nome="Turma 101", codigo="101", descricao="Turma de demonstração")
    turma101.disciplinas.append(calc1)  # conteúdo habilitado pra turma
    db.session.add(turma101)
    db.session.commit()

    # --- ADMIN ---
    admin = Usuario(
        nome="Professor Admin",
        email="admin@admin.com",
        senha_hash=generate_password_hash("123"),
        is_admin=True,
    )
    db.session.add(admin)
    db.session.commit()

    db.session.add(Matricula(turma_id=turma101.id, usuario_id=admin.id, papel="professor"))
    db.session.commit()

    # --- DESAFIO EXEMPLO (LaTeX) ---
    d = Desafio(
        topico_id=t1.id,
        titulo="Fatoração (exemplo)",
        tipo_enunciado="latex",
        enunciado_latex=r"\lim_{x\to 1}\frac{x^2-1}{x-1}",
    )
    db.session.add(d)
    db.session.commit()

    # --- PERGUNTAS (passos) com alternativas LaTeX ---
    p1 = Pergunta(
        desafio_id=d.id,
        ordem=1,
        enunciado=r"Qual fatoração é correta para \(x^2-1\)?",
        alt_a=r"(x-1)(x+1)",
        alt_b=r"(x-1)^2",
        alt_c=r"x(x-1)",
        alt_d=r"(x+1)^2",
        correta="a",
    )
    p2 = Pergunta(
        desafio_id=d.id,
        ordem=2,
        enunciado=r"Após simplificar, qual expressão resta?",
        alt_a=r"\frac{x^2-1}{x-1}",
        alt_b=r"x+1",
        alt_c=r"x-1",
        alt_d=r"\frac{1}{x-1}",
        correta="b",
    )
    p3 = Pergunta(
        desafio_id=d.id,
        ordem=3,
        enunciado=r"Qual é o valor do limite?",
        alt_a=r"0",
        alt_b=r"1",
        alt_c=r"2",
        alt_d=r"\infty",
        correta="c",
    )
    db.session.add_all([p1, p2, p3])
    db.session.commit()

    print("OK!")
    print("Admin: admin@admin.com | senha: 123")
    print("Turma (cadastro aluno): código 101")
