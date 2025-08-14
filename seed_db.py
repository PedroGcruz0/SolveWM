# seed_db.py
from app import create_app
from app.models import db, TiposIndeterminacao, Limite, PerguntasEstrategicas, Estrategia, TentativasLimites, Usuario

app = create_app()

with app.app_context():
    print("Iniciando a população do banco de dados...")

    # Limpa dados de progresso e perguntas de exemplo para segurança
    db.session.query(PerguntasEstrategicas).delete()
    db.session.query(TentativasLimites).delete()
    db.session.commit()

    # --- 1. CRIAÇÃO DE ESTRATÉGIAS ---
    print("Verificando e populando estratégias...")
    estrategias = {
        'Fatoração': 'Técnica algébrica para simplificar expressões polinomiais.',
        'Racionalização': 'Técnica para eliminar radicais do numerador ou denominador.',
        'L\'Hôpital': 'Método de cálculo para indeterminações do tipo 0/0 ou ∞/∞ usando derivadas.',
        'Divisão pela Maior Potência': 'Técnica para resolver limites no infinito de funções racionais.',
        'Limite Trigonométrico Fundamental': 'Uso do limite fundamental de sin(x)/x.',
        'Análise de Grau': 'Comparação entre os graus dos polinômios do numerador e denominador.',
        'Substituição Direta': 'Avaliação do limite substituindo o valor diretamente na função.'
    }
    for nome, desc in estrategias.items():
        if not Estrategia.query.filter_by(nome=nome).first():
            db.session.add(Estrategia(nome=nome, descricao=desc))
    db.session.commit()

    # --- 2. CRIAÇÃO DE TIPOS DE INDETERMINAÇÃO ---
    print("Verificando e populando tipos de indeterminação...")
    tipos = {
        '0/0': 'Numerador e denominador tendem a zero.',
        'Infinito sobre Infinito': 'Numerador e denominador tendem ao infinito.',
        'Infinito menos Infinito': 'Subtração de duas funções que tendem ao infinito.',
        'Sem Indeterminação': 'Limites resolvidos por substituição direta.'
    }
    for nome, desc in tipos.items():
        if not TiposIndeterminacao.query.filter_by(nome=nome).first():
            db.session.add(TiposIndeterminacao(nome=nome, descricao=desc))
    db.session.commit()

    # --- 3. CRIAÇÃO DE LIMITES DE EXEMPLO ---
    print("Verificando e populando limites de exemplo...")
    map_estrategia = {e.nome: e for e in Estrategia.query.all()}
    map_tipo = {t.nome: t for t in TiposIndeterminacao.query.all()}

    limites_exemplo = [
        {'id': 1, 'tipo': '0/0', 'estrategia': 'Fatoração', 'latex_str': '\\lim_{x \\to 2} \\frac{x^2 - 4}{x - 2}', 'resposta_final': '4'},
        {'id': 2, 'tipo': 'Infinito sobre Infinito', 'estrategia': 'Divisão pela Maior Potência', 'latex_str': '\\lim_{x \\to \\infty} \\frac{3x^2 + 5x}{2x^2 - 1}', 'resposta_final': '3/2'},
        {'id': 3, 'tipo': 'Infinito menos Infinito', 'estrategia': 'Racionalização', 'latex_str': '\\lim_{x \\to \\infty} (\\sqrt{x^2 + x} - x)', 'resposta_final': '1/2'},
        {'id': 4, 'tipo': 'Sem Indeterminação', 'estrategia': 'Substituição Direta', 'latex_str': '\\lim_{x \\to 3} (x^2 + 2x - 5)', 'resposta_final': '26'},
        {'id': 5, 'tipo': '0/0', 'estrategia': 'Limite Trigonométrico Fundamental', 'latex_str': '\\lim_{x \\to 0} \\frac{\\sin(x)}{x}', 'resposta_final': '1'}
    ]
    
    for l_data in limites_exemplo:
        if not db.session.get(Limite, l_data['id']):
            novo_limite = Limite(
                id=l_data['id'], 
                tipo_id=map_tipo[l_data['tipo']].id,
                estrategia_id=map_estrategia[l_data['estrategia']].id,
                latex_str=l_data['latex_str'], 
                resposta_final=l_data['resposta_final']
            )
            db.session.add(novo_limite)
    db.session.commit()

    # --- 4. CRIAÇÃO DE PERGUNTAS DE EXEMPLO ---
    print("Populando com perguntas de exemplo...")
    perguntas_exemplo = [
        {'limite_id': 1, 'ordem': 1, 'texto': "Qual o primeiro passo ideal?", 'a': "Substituir x=2", 'b': "L'Hôpital", 'correta': 'a'},
        {'limite_id': 1, 'ordem': 2, 'texto': "Qual a indeterminação?", 'a': "∞/∞", 'b': "0/0", 'correta': 'b'},
        {'limite_id': 2, 'ordem': 1, 'texto': "Qual a maior potência no denominador?", 'a': "x", 'b': "x²", 'correta': 'b'},
        {'limite_id': 3, 'ordem': 1, 'texto': "Qual o conjugado da expressão?", 'a': "\\sqrt{x^2+x}+x", 'b': "\\sqrt{x^2+x}-x", 'correta': 'a'}
    ]

    for p_data in perguntas_exemplo:
        if not PerguntasEstrategicas.query.filter_by(limite_id=p_data['limite_id'], ordem=p_data['ordem']).first():
            nova_pergunta = PerguntasEstrategicas(
                limite_id=p_data['limite_id'], ordem=p_data['ordem'], texto_pergunta=p_data['texto'],
                alternativa_a=p_data.get('a'), alternativa_b=p_data.get('b'),
                resposta_correta=p_data['correta']
            )
            db.session.add(nova_pergunta)
    
    db.session.commit()
    print("Banco de dados populado com sucesso!")