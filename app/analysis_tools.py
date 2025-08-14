# app/analysis_tools.py
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sqlalchemy import create_engine
import os
import os.path as osp

def run_analysis(app_instance_path):
    """
    Executa a análise de K-Means e salva os relatórios com nomes.
    """

    db_path = osp.join(app_instance_path, 'app.db')
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Arquivo de banco de dados não encontrado: {db_path}")

    engine = create_engine(f'sqlite:///{db_path}')
    
    query = """
        SELECT 
            t.usuario_id,
            u.nome,
            e.nome AS estrategia_principal,
            1.0 - AVG(CASE WHEN i.foi_correta THEN 1.0 ELSE 0.0 END) as taxa_erro
        FROM 
            interacoes_usuarios AS i
        JOIN 
            tentativas_limites AS t ON i.tentativa_id = t.id
        JOIN 
            limites AS l ON i.limite_id = l.id
        JOIN 
            estrategias AS e ON l.estrategia_id = e.id
        JOIN
            usuarios AS u ON t.usuario_id = u.user_id
        GROUP BY 
            t.usuario_id, u.nome, e.nome;
    """
    
    df_interacoes = pd.read_sql(query, engine)

    if df_interacoes.empty or len(df_interacoes['usuario_id'].unique()) < 2:
        print("[AVISO] Não há dados de pelo menos 2 usuários diferentes para a análise.")
        return None, None

    df_perfis = df_interacoes.pivot_table(
        index=['usuario_id', 'nome'],
        columns='estrategia_principal', 
        values='taxa_erro'
    ).fillna(0)

    if len(df_perfis.index) < 2:
        return None, None

    dados_numericos = df_perfis.values
    scaler = StandardScaler()
    dados_normalizados = scaler.fit_transform(dados_numericos)
    
    n_clusters = min(3, len(df_perfis.index))
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init='auto')
    clusters = kmeans.fit_predict(dados_normalizados)
    
    df_perfis.reset_index(inplace=True)
    df_perfis['perfil_cluster'] = clusters

    # Mapeia os números dos clusters
    df_perfis['perfil_cluster'] = df_perfis['perfil_cluster'].apply(lambda x: f"Grupo {chr(65 + x)}")

    # Renomeia as colunas para o CSV
    df_perfis.rename(columns={
        'usuario_id': 'ID do Usuário',
        'nome': 'Nome do Aluno',
        'perfil_cluster': 'Perfil de Aluno'
    }, inplace=True)
    
    colunas_estrategias = [col for col in df_perfis.columns if col not in ['ID do Usuário', 'Nome do Aluno', 'Perfil de Aluno']]
    relatorio_perfis_final = df_perfis[['ID do Usuário', 'Nome do Aluno', 'Perfil de Aluno'] + colunas_estrategias]

    cluster_analysis = df_perfis.groupby('Perfil de Aluno')[colunas_estrategias].mean()
    cluster_analysis.rename_axis('Perfil de Grupo', inplace=True) # Renomeia o índice
    
    reports_dir = osp.join(osp.dirname(app_instance_path), 'reports')
    os.makedirs(reports_dir, exist_ok=True)
    
    output_file_profiles = 'resultado_clusters_usuarios.csv'
    output_file_analysis = 'analise_dos_clusters.csv'
    
    relatorio_perfis_final.to_csv(osp.join(reports_dir, output_file_profiles), index=False)
    cluster_analysis.to_csv(osp.join(reports_dir, output_file_analysis))
    
    return output_file_profiles, output_file_analysis