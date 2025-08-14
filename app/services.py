# app/services.py
import os
import os.path as osp
import uuid
import re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import current_app
from PIL import Image
from werkzeug.utils import secure_filename
from sqlalchemy import func
from .models import db, Limite, PerguntasEstrategicas, TentativasLimites, InteracoesUsuarios, Usuario, TiposIndeterminacao, Estrategia
from sympy import sympify, limit, oo, S, Add, Mul, Symbol, Limit, log, Pow, sqrt
from sympy.parsing.latex import parse_latex

# -- FUNÇÕES AUXILIARES --
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# -- SERVIÇOS PRINCIPAIS --
def render_latex_matplotlib(latex_str, app):
    try:
        filename = f"latex_{uuid.uuid4().hex}.png"
        upload_folder = app.config['UPLOAD_FOLDER']
        output_path = osp.join(upload_folder, filename)
        
        formatted_latex = f"${latex_str}$"
        fig = plt.figure()
        text = fig.text(0.5, 0.5, formatted_latex, ha='center', va='center', fontsize=20)
        
        fig.canvas.draw()
        bbox = text.get_window_extent(fig.canvas.get_renderer()).transformed(fig.dpi_scale_trans.inverted())
        fig.set_size_inches(bbox.width + 0.2, bbox.height + 0.2)
        
        plt.axis('off')
        plt.savefig(output_path, format='png', bbox_inches='tight', pad_inches=0.1, transparent=True)
        plt.close(fig)
        
        return f"/uploads/{filename}"
    except Exception as e:
        print(f"Erro ao renderizar LaTeX: {e}")
        return None

def processar_imagem_com_latex_ocr(file_storage):
    filename = secure_filename(file_storage.filename)
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    file_storage.save(filepath)
    raw_latex = current_app.latex_ocr_model(Image.open(filepath))
    print(f"LaTeX-OCR extraiu: {raw_latex}")
    return raw_latex

def criar_novo_usuario(nome, email, senha_hash):
    novo_usuario = Usuario(nome=nome, email=email, senha=senha_hash)
    db.session.add(novo_usuario)
    db.session.commit()
    return novo_usuario

def iniciar_nova_tentativa(usuario_id, limite_id):
    nova_tentativa = TentativasLimites(usuario_id=usuario_id, limite_id=limite_id)
    db.session.add(nova_tentativa)
    db.session.commit()
    return nova_tentativa

def registrar_interacao(tentativa_id, pergunta_id, alternativa_escolhida):
    pergunta = db.session.get(PerguntasEstrategicas, pergunta_id)
    if not pergunta:
        return {'error': 'Pergunta não encontrada'}

    foi_correta = (alternativa_escolhida.lower() == pergunta.resposta_correta.lower())
    
    nova_interacao = InteracoesUsuarios(
        tentativa_id=tentativa_id,
        pergunta_id=pergunta_id,
        limite_id=pergunta.limite_id,
        alternativa_escolhida=alternativa_escolhida,
        foi_correta=foi_correta
    )
    db.session.add(nova_interacao)
    db.session.commit()

    tentativa_atual = db.session.get(TentativasLimites, tentativa_id)
    total_perguntas_limite = db.session.query(PerguntasEstrategicas).filter_by(limite_id=tentativa_atual.limite_id).count()
    total_respostas_dadas = db.session.query(InteracoesUsuarios).filter_by(tentativa_id=tentativa_id).count()
    
    fim_da_tentativa = (total_respostas_dadas >= total_perguntas_limite)
    
    if fim_da_tentativa:
        acertos = db.session.query(InteracoesUsuarios).filter_by(tentativa_id=tentativa_id, foi_correta=True).count()
        if total_perguntas_limite > 0:
            taxa_acerto = acertos / total_perguntas_limite
            tentativa_atual.finalizada = True
            tentativa_atual.taxa_acerto_final = taxa_acerto
            tentativa_atual.dominou_limite = (taxa_acerto >= 0.70)
            db.session.commit()

    return {
        'foi_correta': foi_correta,
        'resposta_correta': pergunta.resposta_correta,
        'fim_da_tentativa': fim_da_tentativa
    }

def selecionar_proximo_limite(usuario_id):
    """Seleciona um limite aleatório que o usuário AINDA NÃO TENTOU."""
    limites_com_perguntas_ids = [res[0] for res in db.session.query(PerguntasEstrategicas.limite_id).distinct().all()]
    if not limites_com_perguntas_ids:
        return None
        
    limites_ja_tentados_ids = [
        t.limite_id for t in TentativasLimites.query.filter_by(usuario_id=usuario_id).all()
    ]
    
    proximo_limite = Limite.query.filter(
        ~Limite.id.in_(limites_ja_tentados_ids),
        Limite.id.in_(limites_com_perguntas_ids)
    ).order_by(func.random()).first()
        
    return proximo_limite

def preprocessar_latex(expressao_latex):
    expressao_processada = expressao_latex.strip().lower()
    substituicoes = {"\\operatorname*{lim}": "\\lim", "\\operatorname{lim}": "\\lim", "\\rightarrow": "\\to", "\\left(": "(", "\\right)": ")"}
    for antigo, novo in substituicoes.items():
        expressao_processada = expressao_processada.replace(antigo, novo)
    expressao_processada = re.sub(r'\\to\s*x', r'\\to \\infty', expressao_processada)
    return expressao_processada

def converter_latex_para_sympy(expressao_latex):
    return parse_latex(expressao_latex)

def converter_texto_para_limite(expressao_str: str):
    """
    Converte uma string no formato 'funcao var->ponto' para um objeto de Limite do Sympy.
    """
    if '->' not in expressao_str:
        raise ValueError("Formato de texto inválido. Use o formato: expressao x->ponto")

    partes = expressao_str.split('->')
    if len(partes) != 2:
        raise ValueError("Formato de texto inválido. Separe a função e o ponto com '->'.")
        
    ponto_str = partes[1].strip().lower()
    
    func_e_var_str = partes[0].strip()
    try:
        # Encontra o último espaço para separar a variável da função
        idx_ultimo_espaco = func_e_var_str.rindex(' ')
        func_str = func_e_var_str[:idx_ultimo_espaco].strip()
        var_str = func_e_var_str[idx_ultimo_espaco:].strip()
    except ValueError:
        # Se não houver espaço, pode ser um erro de digitação
        raise ValueError("Formato inválido. Lembre-se de separar a variável com um espaço. Ex: x**2 x->2")

    var_obj = Symbol(var_str)
    
    # Adiciona as funções permitidas ao dicionário de locais para o sympify
    func_obj = sympify(func_str, locals={var_str: var_obj, 'log': log, 'sqrt': sqrt})
    
    ponto_obj = oo if 'oo' in ponto_str else sympify(ponto_str)
    
    return Limit(func_obj, var_obj, ponto_obj)

def gerar_resposta_completa(limite_obj):
    if not isinstance(limite_obj, Limit):
        return {'tipo': 'A expressão fornecida não é um limite calculável.', 'metodos': []}
    try:
        resultado_final = limite_obj.doit()
        func, var, ponto = limite_obj.args[:3]
        indeterminacao_tipo = None
        
        numerador, denominador = func.as_numer_denom()
        lim_numerador = limit(numerador, var, ponto)
        lim_denominador = limit(denominador, var, ponto)

        if lim_numerador == 0 and lim_denominador == 0:
            indeterminacao_tipo = "Indeterminação do tipo 0/0"
        elif hasattr(lim_numerador, 'is_infinite') and lim_numerador.is_infinite and \
             hasattr(lim_denominador, 'is_infinite') and lim_denominador.is_infinite:
            indeterminacao_tipo = "Indeterminação do tipo ∞/∞"
        elif isinstance(func, Add):
            termos = func.as_ordered_terms()
            limites_termos = [limit(t, var, ponto) for t in termos]
            if oo in limites_termos and -oo in limites_termos:
                indeterminacao_tipo = "Indeterminação do tipo ∞ - ∞"
        elif isinstance(func, Mul):
            fatores = func.as_ordered_factors()
            limites_fatores = [limit(f, var, ponto) for f in fatores]
            tem_zero = any(l == 0 for l in limites_fatores)
            tem_infinito = any(hasattr(l, 'is_infinite') and l.is_infinite for l in limites_fatores)
            if tem_zero and tem_infinito:
                indeterminacao_tipo = "Indeterminação do tipo 0 * ∞"
        
        resultado_str = str(resultado_final)
        if indeterminacao_tipo:
            texto_analise = f"Detectada uma <strong>{indeterminacao_tipo}</strong>. Após os cálculos, o resultado do limite é <strong>{resultado_str}</strong>."
        else:
            texto_analise = f"O limite é <strong>{resultado_str}</strong>. Não foi detectada uma indeterminação comum."
            
        metodos_sugeridos = sugerir_metodos(texto_analise, func)
        return {'tipo': texto_analise, 'metodos': metodos_sugeridos}
    except Exception as e:
        return {'tipo': f"Erro ao calcular o limite: {e}", 'metodos': []}

def sugerir_metodos(texto_resultado, func_obj):
    if "0/0" in texto_resultado or "∞/∞" in texto_resultado:
        metodos = ["<strong>Regra de L'Hôpital</strong>"]
        if "sqrt" in str(func_obj):
            metodos.append("<strong>Racionalização (Multiplicar pelo Conjugado)</strong>")
        else:
            metodos.append("<strong>Fatoração e Simplificação</strong>")
        return metodos
    elif "∞ - ∞" in texto_resultado:
        return ["<strong>Racionalização (Multiplicar pelo Conjugado)</strong>", "<strong>Colocar o Termo de Maior Grau em Evidência</strong>"]
    elif "0 * ∞" in texto_resultado:
        return ["<strong>Rearranjar a expressão</strong> para a forma 0/0 ou ∞/∞ (ex: `f*g = f/(1/g)`) e então aplicar L'Hôpital."]
    return []