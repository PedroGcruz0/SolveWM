import os
import os.path as osp

import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sqlalchemy import create_engine


def rodar_analise(instance_path: str, turma_id: int | None = None):
    db_path = osp.join(instance_path, "app.db")
    if not os.path.exists(db_path):
        return None, None

    engine = create_engine(f"sqlite:///{db_path}")

    where = ""
    params = {}
    if turma_id:
        where = "WHERE t.turma_id = :turma_id"
        params["turma_id"] = turma_id

    query = f"""
        SELECT
            t.usuario_id,
            u.nome AS aluno,
            tp.nome AS topico,
            1.0 - AVG(CASE WHEN i.foi_correta THEN 1.0 ELSE 0.0 END) AS taxa_erro
        FROM interacoes i
        JOIN tentativas_desafio t ON i.tentativa_id = t.id
        JOIN usuarios u ON t.usuario_id = u.id
        JOIN topicos tp ON i.topico_id = tp.id
        {where}
        GROUP BY t.usuario_id, u.nome, tp.nome;
    """

    df = pd.read_sql(query, engine, params=params)
    if df.empty:
        return None, None

    matriz = df.pivot_table(index=["usuario_id", "aluno"], columns="topico", values="taxa_erro").fillna(0)
    if matriz.empty:
        return None, None

    n = len(matriz.index)
    if n == 1:
        clusters = [0]
    else:
        X = StandardScaler().fit_transform(matriz.values)
        k = min(3, n)
        kmeans = KMeans(n_clusters=k, random_state=42, n_init="auto")
        clusters = kmeans.fit_predict(X)

    matriz.reset_index(inplace=True)
    matriz["cluster"] = [f"Grupo {chr(65 + int(c))}" for c in clusters]

    cols = [c for c in matriz.columns if c not in ["usuario_id", "aluno", "cluster"]]
    rel_alunos = matriz[["usuario_id", "aluno", "cluster"] + cols]
    rel_grupos = matriz.groupby("cluster")[cols].mean().reset_index()

    reports_dir = osp.join(osp.dirname(instance_path), "reports")
    os.makedirs(reports_dir, exist_ok=True)

    sufixo = f"_turma_{turma_id}" if turma_id else ""
    f1 = f"relatorio_alunos{sufixo}.csv"
    f2 = f"relatorio_grupos{sufixo}.csv"

    rel_alunos.to_csv(osp.join(reports_dir, f1), index=False)
    rel_grupos.to_csv(osp.join(reports_dir, f2), index=False)

    return f1, f2
