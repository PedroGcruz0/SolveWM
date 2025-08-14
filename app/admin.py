# app/admin.py
from flask_admin import Admin, AdminIndexView, BaseView, expose
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user
from flask import redirect, url_for, request, current_app
from wtforms.fields import TextAreaField, PasswordField
from werkzeug.security import generate_password_hash
from .models import db, Usuario, Limite, PerguntasEstrategicas, TiposIndeterminacao, Estrategia
import pandas as pd
import os

# --- View Customizada para a PÁGINA INICIAL do Admin (DASHBOARD) ---
class MyAdminIndexView(AdminIndexView):
    @expose('/')
    def index(self):
        if not current_user.is_authenticated or not current_user.is_admin:
            return redirect(url_for('main.login', next=request.url))
        
        limite_count = Limite.query.count()
        perguntas_count = PerguntasEstrategicas.query.count()
        user_count = Usuario.query.count()
        
        return self.render('admin/index.html', 
                           limite_count=limite_count, 
                           perguntas_count=perguntas_count, 
                           user_count=user_count)

# --- View de Segurança e Padrão para os Modelos ---
class SolveWMBaseView(ModelView):
    can_sort = False
    can_view_details = True
    can_edit = True
    can_delete = True
    column_display_actions = True
    can_search = False
    can_filters = False
    action_disallowed_list = ['delete']
    
    list_template = 'admin/custom_list.html'
    instructional_text = None

    def list_view(self):
        view_args = self._list_view_args()
        view_args['instructional_text'] = self.instructional_text
        return self.render(self.list_template, **view_args)

    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin
        
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('main.login', next=request.url))

# --- View Customizada para a Análise (COM A LÓGICA RESTAURADA) ---
class AnalysisView(BaseView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('main.login', next=request.url))

    @expose('/')
    def index(self):
        reports_dir = os.path.join(os.path.dirname(current_app.instance_path), 'reports')
        profiles_df_display = None
        analysis_df_display = None
        chart_data = None
        try:
            profile_path = os.path.join(reports_dir, 'resultado_clusters_usuarios.csv')
            analysis_path = os.path.join(reports_dir, 'analise_dos_clusters.csv')
            
            if os.path.exists(profile_path) and os.path.exists(analysis_path):
                profiles_df = pd.read_csv(profile_path)
                analysis_df = pd.read_csv(analysis_path)
                
                # Prepara dados para o gráfico
                chart_labels = analysis_df.columns[1:].tolist()
                datasets = []
                colors = ['rgba(54, 162, 235, 0.6)', 'rgba(255, 99, 132, 0.6)', 'rgba(75, 192, 192, 0.6)']
                for index, row in analysis_df.iterrows():
                    datasets.append({
                        'label': row[0],
                        'data': [round(val * 100) for val in row[1:].tolist()],
                        'backgroundColor': colors[index % len(colors)]
                    })
                chart_data = {'labels': chart_labels, 'datasets': datasets}
                
                # Formata o DataFrame de ANÁLISE para EXIBIÇÃO
                analysis_df_display = analysis_df.copy()
                analysis_df_display.rename(columns={analysis_df.columns[0]: 'Perfil de Grupo (Taxa de Erro Média)'}, inplace=True)
                for col in analysis_df_display.columns[1:]:
                    analysis_df_display[col] = analysis_df_display[col].apply(lambda x: f"{x:.1%}")
                
                # Formata o DataFrame de PERFIS para EXIBIÇÃO
                profiles_df_display = profiles_df.copy()
                strategy_cols = [col for col in profiles_df_display.columns if col not in ['ID do Usuário', 'Nome do Aluno', 'Perfil de Aluno']]
                for col in profiles_df_display.columns:
                    if col in strategy_cols:
                        profiles_df_display[col] = profiles_df_display[col].apply(lambda x: f"{x:.1%}")

        except Exception as e:
            print(f"Erro ao ler ou processar arquivos de relatório: {e}")

        return self.render('admin/analysis.html', 
                           profiles_df_display=profiles_df_display, 
                           analysis_df_display=analysis_df_display,
                           chart_data=chart_data)

# --- Views Específicas que Herdam a Base ---
class UsuarioView(SolveWMBaseView):
    instructional_text = "Esta página exibe todos os usuários cadastrados."
    can_search = True
    column_searchable_list = ('nome', 'email')
    column_list = ('nome', 'email', 'is_admin')
    form_create_rules = ('nome', 'email', 'senha', 'is_admin')
    form_edit_rules = ('nome', 'email', 'is_admin')
    form_overrides = {'senha': PasswordField}
    def on_model_change(self, form, model, is_created):
        if is_created and form.senha.data:
            model.senha = generate_password_hash(form.senha.data)

class LimiteView(SolveWMBaseView):
    instructional_text = "Esta é a página para gerenciar os desafios de limite."
    column_labels = {'latex_str': 'Código LaTeX', 'estrategia': 'Estratégia', 'tipo': 'Tipo de Indeterminação'}
    column_list = ('id', 'tipo', 'estrategia', 'latex_str')
    form_overrides = {'latex_str': TextAreaField}
    form_ajax_refs = {
        'tipo': {'fields': ('nome',)},
        'estrategia': {'fields': ('nome',)}
    }
    form_columns = ('tipo', 'estrategia', 'latex_str', 'resposta_final')

class PerguntasView(SolveWMBaseView):
    instructional_text = "Aqui você gerencia as perguntas de múltipla escolha."
    column_list = ('texto_pergunta', 'limite', 'resposta_correta')
    column_labels = {'texto_pergunta': 'Texto da Pergunta', 'limite': 'Limite Associado', 'resposta_correta': 'Resposta Correta'}
    form_ajax_refs = {'limite': {'fields': ('latex_str',)}}
    form_columns = [
        'limite', 'texto_pergunta', 'ordem',
        'alternativa_a', 'alternativa_b', 'alternativa_c', 'alternativa_d',
        'resposta_correta'
    ]

class EstrategiaView(SolveWMBaseView):
    instructional_text = "As estratégias são os métodos de resolução."
    column_list = ('nome', 'descricao')
    column_labels = {'nome': 'Nome da Estratégia', 'descricao': 'Descrição'}

class TiposIndeterminacaoView(SolveWMBaseView):
    instructional_text = "Aqui você cadastra os tipos de indeterminação."
    column_list = ('nome', 'descricao')
    column_labels = {'nome': 'Nome da Indeterminação', 'descricao': 'Descrição'}

# --- Setup Final do Admin ---
def setup_admin(app):
    admin = Admin(
        app, 
        name='Painel de Controle Solve WM', 
        template_mode='bootstrap4',
        index_view=MyAdminIndexView(name="Início", url='/admin'),
        base_template='admin/my_master.html'
    )
    
    admin.add_view(EstrategiaView(Estrategia, db.session, name='Estratégias', category='Gerenciar Conteúdo'))
    admin.add_view(TiposIndeterminacaoView(TiposIndeterminacao, db.session, name='Tipos de Indeterminação', category='Gerenciar Conteúdo'))
    admin.add_view(LimiteView(Limite, db.session, name='Limites', category='Gerenciar Conteúdo'))
    admin.add_view(PerguntasView(PerguntasEstrategicas, db.session, name='Perguntas', category='Gerenciar Conteúdo'))
    admin.add_view(UsuarioView(Usuario, db.session, name='Usuários', category='Gerenciar Acessos'))
    admin.add_view(AnalysisView(name='Análise de Alunos', endpoint='analysis', category='Pesquisa'))