# app/admin_views.py
from __future__ import annotations

from collections import defaultdict
from typing import Optional, Dict, List, Tuple

import random

from flask import redirect, url_for, request
from flask_admin import BaseView, expose
from flask_login import current_user
from sqlalchemy import func, case

from .modelos import db, Usuario, Turma, Matricula, Topico, TentativaDesafio, Interacao


# =========================
# Acesso Admin 
# =========================
class AdminAccessMixin:
    def is_accessible(self):
        return current_user.is_authenticated and getattr(current_user, "is_admin", False)

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("site.index"))


# =========================
# K-means simples 
# =========================
def _kmeans_simple(X: List[List[float]], k: int, iters: int = 60, seed: int = 42) -> List[int]:
    n = len(X)
    if n == 0:
        return []
    d = len(X[0]) if X[0] else 0
    if d == 0:
        return [0] * n

    k = max(1, min(int(k), n))

    rnd = random.Random(seed)
    centroids = [X[i][:] for i in rnd.sample(range(n), k)]

    def dist2(a, b):
        return sum((a[j] - b[j]) ** 2 for j in range(d))

    labels = [0] * n

    for _ in range(iters):
        changed = False

        # assign
        for i in range(n):
            best = 0
            bestd = dist2(X[i], centroids[0])
            for c in range(1, k):
                dd = dist2(X[i], centroids[c])
                if dd < bestd:
                    bestd = dd
                    best = c
            if labels[i] != best:
                labels[i] = best
                changed = True

        # recompute
        sums = [[0.0] * d for _ in range(k)]
        counts = [0] * k

        for i in range(n):
            c = labels[i]
            counts[c] += 1
            xi = X[i]
            for j in range(d):
                sums[c][j] += xi[j]

        for c in range(k):
            if counts[c] == 0:
                centroids[c] = X[rnd.randrange(n)][:]  # reinit cluster vazio
            else:
                centroids[c] = [sums[c][j] / counts[c] for j in range(d)]

        if not changed:
            break

    return labels


# =========================
# Queries e construção do dashboard
# =========================
def _alunos_da_turma(turma_id: int) -> list[Usuario]:
    return (
        db.session.query(Usuario)
        .join(Matricula, Matricula.usuario_id == Usuario.id)
        .filter(Matricula.turma_id == turma_id, Matricula.papel == "aluno")
        .order_by(Usuario.nome.asc())
        .all()
    )


def _dados_por_topico(turma_id: int, aluno_id: Optional[int]) -> list[dict]:
    q = (
        db.session.query(
            Interacao.topico_id.label("topico_id"),
            Topico.nome.label("topico_nome"),
            func.count(Interacao.id).label("total"),
            func.coalesce(
                func.sum(case((Interacao.foi_correta.is_(False), 1), else_=0)),
                0
            ).label("erros"),
        )
        .join(TentativaDesafio, TentativaDesafio.id == Interacao.tentativa_id)
        .join(Topico, Topico.id == Interacao.topico_id)
        .filter(TentativaDesafio.turma_id == turma_id)
    )

    if aluno_id:
        q = q.filter(TentativaDesafio.usuario_id == aluno_id)

    rows = q.group_by(Interacao.topico_id, Topico.nome).all()

    out = []
    for r in rows:
        total = int(r.total or 0)
        erros = int(r.erros or 0)
        taxa = (erros / total) if total else 0.0
        out.append(
            {
                "topico_id": int(r.topico_id),
                "topico_nome": str(r.topico_nome),
                "total": total,
                "erros": erros,
                "taxa_erro": float(taxa),
            }
        )

    # ordena por pior taxa (desc) pra tabela
    out.sort(key=lambda x: x["taxa_erro"], reverse=True)
    return out


def _build_kmeans_por_turma(turma_id: int, k: int) -> dict:
    """
    Retorna:
      - chart_data: média da taxa de erro (%) por GRUPO em cada tópico
      - clusters: aluno_id -> grupo (1..k) | None (sem dados)
      - cluster_cards: lista com alunos por grupo
      - k_eff: k efetivo
      - stats: contagens úteis
    """
    alunos_all = _alunos_da_turma(turma_id)
    aluno_ids_all = [int(a.id) for a in alunos_all]

    # interações por aluno x tópico
    rows = (
        db.session.query(
            TentativaDesafio.usuario_id.label("usuario_id"),
            Interacao.topico_id.label("topico_id"),
            func.count(Interacao.id).label("total"),
            func.coalesce(func.sum(case((Interacao.foi_correta.is_(False), 1), else_=0)), 0).label("erros"),
        )
        .join(Interacao, Interacao.tentativa_id == TentativaDesafio.id)
        .filter(TentativaDesafio.turma_id == turma_id)
        .group_by(TentativaDesafio.usuario_id, Interacao.topico_id)
        .all()
    )

    total_interacoes = int(sum(int(r.total or 0) for r in rows))

    # tópicos presentes nas interações
    topic_ids = sorted({int(r.topico_id) for r in rows if r.topico_id is not None})
    if not topic_ids:
        return {
            "chart_data": {"labels": [], "datasets": []},
            "clusters": {aid: None for aid in aluno_ids_all},
            "cluster_cards": [],
            "k_eff": 0,
            "stats": {
                "n_alunos": len(aluno_ids_all),
                "n_topicos": 0,
                "total_interacoes": total_interacoes,
                "n_alunos_com_dados": 0,
            },
        }

    topics = Topico.query.filter(Topico.id.in_(topic_ids)).all()
    topic_name_by_id = {t.id: t.nome for t in topics}
    # ordem do gráfico por nome
    topic_ids_ord = sorted(topic_ids, key=lambda tid: (topic_name_by_id.get(tid, f"Tópico {tid}")).lower())
    topic_labels = [topic_name_by_id.get(tid, f"Tópico {tid}") for tid in topic_ids_ord]

    # alunos com dados (aparecem em rows)
    aluno_ids_active = sorted({int(r.usuario_id) for r in rows if r.usuario_id is not None})
    aluno_ids_active = [aid for aid in aluno_ids_active if aid in aluno_ids_all]

    # se ninguém interagiu, não clusteriza
    if not aluno_ids_active:
        return {
            "chart_data": {"labels": [], "datasets": []},
            "clusters": {aid: None for aid in aluno_ids_all},
            "cluster_cards": [],
            "k_eff": 0,
            "stats": {
                "n_alunos": len(aluno_ids_all),
                "n_topicos": len(topic_ids_ord),
                "total_interacoes": total_interacoes,
                "n_alunos_com_dados": 0,
            },
        }

    # taxa_map[(aluno, topico)] = taxa erro
    taxa_map: Dict[Tuple[int, int], float] = {}
    # médias globais por tópico (para imputar missing)
    sum_t: Dict[int, float] = defaultdict(float)
    cnt_t: Dict[int, int] = defaultdict(int)

    for r in rows:
        uid = int(r.usuario_id)
        tid = int(r.topico_id)
        total = int(r.total or 0)
        erros = int(r.erros or 0)
        taxa = (erros / total) if total else 0.0
        taxa_map[(uid, tid)] = float(taxa)
        sum_t[tid] += float(taxa)
        cnt_t[tid] += 1

    mean_by_topico = {tid: (sum_t[tid] / cnt_t[tid] if cnt_t[tid] else 0.0) for tid in topic_ids_ord}

    # matriz X (só alunos com dados)
    X: List[List[float]] = []
    for uid in aluno_ids_active:
        row = []
        for tid in topic_ids_ord:
            row.append(taxa_map.get((uid, tid), mean_by_topico.get(tid, 0.0)))
        X.append(row)

    k_eff = max(1, min(int(k), len(aluno_ids_active)))
    labels0 = _kmeans_simple(X, k_eff, iters=60, seed=42)  # 0..k-1

    # clusters para todos alunos (sem dados => None)
    clusters: Dict[int, Optional[int]] = {aid: None for aid in aluno_ids_all}
    for i, uid in enumerate(aluno_ids_active):
        clusters[uid] = int(labels0[i] + 1)  # 1..k

    # médias por grupo x tópico
    sums = [[0.0 for _ in topic_ids_ord] for _ in range(k_eff)]
    counts = [0 for _ in range(k_eff)]
    for i, uid in enumerate(aluno_ids_active):
        g = labels0[i]
        counts[g] += 1
        for j in range(len(topic_ids_ord)):
            sums[g][j] += X[i][j]

    group_means = []
    for g in range(k_eff):
        if counts[g] == 0:
            group_means.append([0.0] * len(topic_ids_ord))
        else:
            group_means.append([sums[g][j] / counts[g] for j in range(len(topic_ids_ord))])

    chart_data = {
        "labels": topic_labels,
        "datasets": [
            {"label": f"Grupo {g+1} (n={counts[g]})", "data": [round(v * 100, 2) for v in group_means[g]]}
            for g in range(k_eff)
        ],
    }

    # cards por grupo
    aluno_nome = {int(a.id): a.nome for a in alunos_all}
    cluster_cards = []
    for g in range(1, k_eff + 1):
        ids_g = [uid for uid in aluno_ids_active if clusters.get(uid) == g]
        cluster_cards.append(
            {
                "grupo": g,
                "n": len(ids_g),
                "alunos": [{"id": uid, "nome": aluno_nome.get(uid, str(uid))} for uid in ids_g],
            }
        )

    # alunos sem dados
    sem_dados = [aid for aid in aluno_ids_all if clusters.get(aid) is None]

    return {
        "chart_data": chart_data,
        "clusters": clusters,
        "cluster_cards": cluster_cards,
        "k_eff": k_eff,
        "stats": {
            "n_alunos": len(aluno_ids_all),
            "n_topicos": len(topic_ids_ord),
            "total_interacoes": total_interacoes,
            "n_alunos_com_dados": len(aluno_ids_active),
            "n_alunos_sem_dados": len(sem_dados),
        },
    }


# =========================
# View
# =========================
class AnaliseView(AdminAccessMixin, BaseView):
    @expose("/", methods=("GET",))
    def index(self):
        turmas = Turma.query.order_by(Turma.nome.asc()).all()

        turma_id_raw = (request.args.get("turma_id") or "").strip()
        aluno_id_raw = (request.args.get("aluno_id") or "").strip()
        k_raw = (request.args.get("k") or "3").strip()

        turma_id: Optional[int] = int(turma_id_raw) if turma_id_raw.isdigit() else None
        aluno_id: Optional[int] = int(aluno_id_raw) if aluno_id_raw.isdigit() else None

        k = int(k_raw) if k_raw.isdigit() else 3
        k = max(1, min(k, 10))

        alunos = _alunos_da_turma(turma_id) if turma_id else []

        # defaults (não quebra template)
        ctx = {
            "turmas": turmas,
            "alunos": alunos,
            "turma_id": turma_id,
            "aluno_id": aluno_id,
            "k": k,
            "dados": [],
            "chart_data": {"labels": [], "datasets": []},
            "clusters": {},
            "cluster_cards": [],
            "k_eff": 0,
            "stats": {"n_alunos": 0, "n_topicos": 0, "total_interacoes": 0, "n_alunos_com_dados": 0, "n_alunos_sem_dados": 0},
            "aluno_grupo": None,
        }

        if turma_id:
            # tabela por tópico (pode filtrar por aluno)
            ctx["dados"] = _dados_por_topico(turma_id, aluno_id)

            # kmeans + gráfico (sempre por turma, não por aluno)
            km = _build_kmeans_por_turma(turma_id, k)
            ctx.update(km)

            if aluno_id:
                grp = (ctx.get("clusters") or {}).get(int(aluno_id))
                ctx["aluno_grupo"] = grp

        return self.render("admin/analise.html", **ctx)
