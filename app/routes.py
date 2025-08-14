# app/routes.py
from flask import (
    render_template, flash, redirect, url_for, 
    request, current_app, Blueprint, send_from_directory, session, jsonify
)
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from . import services
from .models import db, Usuario
from .forms import LoginForm, RegistrationForm
from .analysis_tools import run_analysis
import os

main_bp = Blueprint('main', __name__)

# --- ROTAS DE NAVEGAÇÃO E AUTENTICAÇÃO ---

@main_bp.route('/')
def index():
    return render_template('home.html')

@main_bp.route('/tutor')
@login_required
def tutor():
    return render_template('tutor.html') 

@main_bp.route('/assistente')
@login_required
def assistente():
    return render_template('assistente.html') 

@main_bp.route('/sobre')
def sobre():
    return render_template('sobre.html')

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = Usuario.query.filter_by(email=form.email.data).first()
        if user is None or not check_password_hash(user.senha, form.password.data):
            flash('Email ou senha inválidos', 'warning')
            return redirect(url_for('main.login'))
        login_user(user, remember=form.remember_me.data)
        return redirect(url_for('main.index'))
    return render_template('login.html', title='Entrar', form=form)

@main_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data)
        services.criar_novo_usuario(form.nome.data, form.email.data, hashed_password)
        flash('Parabéns, você foi registrado com sucesso! Por favor, faça o login.', 'success')
        return redirect(url_for('main.login'))
    return render_template('register.html', title='Registrar', form=form)

@main_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))

# --- ROTAS DE ARQUIVOS E API ---

@main_bp.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

@main_bp.route('/process_image', methods=['POST'])
@login_required
def process_image():
    file = request.files.get('file')
    if not file or file.filename == '':
        return jsonify({'raw_latex': 'Erro: Nenhum arquivo enviado'}), 400
    if not services.allowed_file(file.filename):
        return jsonify({'raw_latex': 'Erro: Tipo de arquivo não permitido'}), 400
    try:
        raw_latex = services.processar_imagem_com_latex_ocr(file)
        return jsonify({'raw_latex': raw_latex})
    except Exception as e:
        return jsonify({'raw_latex': f'[ERRO OCR] {e}'}), 500

@main_bp.route('/calcular_latex', methods=['POST'])
@login_required
def calcular_latex():
    data = request.get_json() or {}
    expressao_usuario = data.get('funcao', '').strip()
    if not expressao_usuario:
        return jsonify({'tipo': 'Erro: Nenhuma expressão LaTeX fornecida.', 'metodos': []}), 400
    try:
        latex_processado = services.preprocessar_latex(expressao_usuario)
        limite_obj = services.converter_latex_para_sympy(latex_processado)
        resposta = services.gerar_resposta_completa(limite_obj)
        return jsonify(resposta)
    except Exception as e:
        return jsonify({'tipo': f"Erro ao processar a expressão LaTeX: {e}", 'metodos': []}), 500

@main_bp.route('/calcular_texto', methods=['POST'])
@login_required
def calcular_texto():
    data = request.get_json() or {}
    expressao_usuario = data.get('expressao', '').strip()
    if not expressao_usuario:
        return jsonify({'tipo': 'Erro: Nenhuma expressão fornecida.', 'metodos': []}), 400
    try:
        limite_obj = services.converter_texto_para_limite(expressao_usuario)
        resposta = services.gerar_resposta_completa(limite_obj)
        return jsonify(resposta)
    except Exception as e:
        return jsonify({'tipo': f"Erro ao processar a expressão: {e}", 'metodos': []}), 500

@main_bp.route('/get-problem', methods=['POST'])
@login_required
def get_problem():
    usuario_id = current_user.user_id
    limite = services.selecionar_proximo_limite(usuario_id)
    if not limite:
        return jsonify({'error': 'Parabéns, você completou todos os limites disponíveis!'}), 404
    
    nova_tentativa = services.iniciar_nova_tentativa(usuario_id, limite.id)
    
    perguntas_data = [{
        'id': p.id, 'texto': p.texto_pergunta,
        'alternativas': {'a': p.alternativa_a, 'b': p.alternativa_b, 'c': p.alternativa_c, 'd': p.alternativa_d}
    } for p in limite.perguntas]

    return jsonify({
        'tentativa_id': nova_tentativa.id,
        'limite_id': limite.id,
        'limite_latex': limite.latex_str,
        'perguntas': perguntas_data
    })

@main_bp.route('/submit-answer', methods=['POST'])
@login_required
def submit_answer():
    data = request.json
    resultado = services.registrar_interacao(
        tentativa_id=data.get('tentativa_id'),
        pergunta_id=data.get('pergunta_id'),
        alternativa_escolhida=data.get('alternativa_escolhida')
    )
    return jsonify(resultado)

# --- ROTAS PARA O PAINEL DE ADMIN ---

@main_bp.route('/admin/run-analysis')
@login_required
def run_analysis_route():
    if not current_user.is_admin:
        return redirect(url_for('main.index'))
    
    session.pop('report_files', None)
    try:
        file1, file2 = run_analysis(current_app.instance_path)
        if file1 and file2:
            session['report_files'] = [file1, file2]
            flash('Análise concluída! Relatórios gerados com sucesso.', 'success')
        else:
            flash('Análise executada, mas não há dados suficientes para gerar relatórios.', 'warning')
    except Exception as e:
        flash(f'Ocorreu um erro durante a análise: {e}', 'danger')
        
    return redirect(url_for('analysis.index'))


@main_bp.route('/reports/<path:filename>')
@login_required
def download_report(filename):
    if not current_user.is_admin:
        return redirect(url_for('main.index'))
    
    reports_dir = os.path.join(os.path.dirname(current_app.instance_path), 'reports')
    return send_from_directory(reports_dir, filename, as_attachment=True)