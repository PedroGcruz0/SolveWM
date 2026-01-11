# app/painel_admin.py
from __future__ import annotations

import random
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
from flask import flash, redirect, request, url_for,current_app
from flask_admin import Admin, AdminIndexView, BaseView, expose
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user
from sqlalchemy import case, func
from sqlalchemy.orm import subqueryload
from werkzeug.security import generate_password_hash
import uuid
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import current_app
from .modelos import (
    db,
    Usuario,
    Turma,
    Matricula,
    Disciplina,
    Topico,
    Desafio,
    Pergunta,
    TentativaDesafio,
    Interacao,
)


import os
import uuid
from datetime import datetime




ALLOWED_IMG_EXT = {"png", "jpg", "jpeg", "webp", "gif"}

# ============================================================
# Acesso Admin (Mixin)
# ============================================================


class AdminAccessMixin:
    def is_accessible(self):
        return current_user.is_authenticated and getattr(current_user, "is_admin", False)

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("site.index"))


class SecureModelView(AdminAccessMixin, ModelView):
    can_view_details = True
    page_size = 25


class SecureIndexView(AdminAccessMixin, AdminIndexView):
    @expose("/")
    def index(self):
        kpi_turmas = Turma.query.count()
        kpi_alunos = (
            db.session.query(Matricula.usuario_id)
            .filter(Matricula.papel == "aluno")
            .distinct()
            .count()
        )
        kpi_desafios = Desafio.query.count()

        return self.render(
            "admin/index.html",
            kpi_turmas=kpi_turmas,
            kpi_alunos=kpi_alunos,
            kpi_desafios=kpi_desafios,
        )


# ============================================================
# Helpers (parsing)
# ============================================================


def _parse_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    s = str(value).strip()
    return int(s) if s.isdigit() else None


# ============================================================
# Helpers (K-means simples)
# ============================================================


def _kmeans_simple(X: List[List[float]], k: int, iters: int = 60, seed: int = 42) -> List[int]:
    """
    K-means simples (sem sklearn), retorna labels 0..k-1.
    """
    n = len(X)
    if n == 0:
        return []
    d = len(X[0]) if X[0] else 0
    if d == 0:
        return [0] * n

    k = max(1, min(k, n))
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


# ============================================================
# Helpers (Consultas)
# ============================================================


def _alunos_da_turma(turma_id: int) -> List[Usuario]:
    return (
        db.session.query(Usuario)
        .join(Matricula, Matricula.usuario_id == Usuario.id)
        .filter(Matricula.turma_id == turma_id, Matricula.papel == "aluno")
        .order_by(Usuario.nome.asc())
        .all()
    )


def _dados_por_topico(turma_id: int, aluno_id: Optional[int]) -> List[Dict]:
    """
    Retorna lista por tópico com total/erros/taxa_erro, filtrando por turma e opcionalmente aluno.
    """
    q = (
        db.session.query(
            Interacao.topico_id.label("topico_id"),
            Topico.nome.label("topico_nome"),
            func.count(Interacao.id).label("total"),
            func.coalesce(
                func.sum(case((Interacao.foi_correta.is_(False), 1), else_=0)),
                0,
            ).label("erros"),
        )
        .join(Topico, Topico.id == Interacao.topico_id)
        .join(TentativaDesafio, TentativaDesafio.id == Interacao.tentativa_id)
        .filter(TentativaDesafio.turma_id == turma_id)
    )

    if aluno_id is not None:
        q = q.filter(TentativaDesafio.usuario_id == aluno_id)

    rows = q.group_by(Interacao.topico_id, Topico.nome).all()

    dados = []
    for r in rows:
        total = int(r.total or 0)
        erros = int(r.erros or 0)
        taxa = (erros / total) if total else 0.0
        dados.append(
            {
                "topico_id": int(r.topico_id),
                "topico_nome": str(r.topico_nome),
                "total": total,
                "erros": erros,
                "taxa_erro": float(taxa),
            }
        )

    # ordena por nome (fica estável no gráfico/tabelas)
    dados.sort(key=lambda x: x["topico_nome"].lower())
    return dados


def _donut_data(turma_id: int, aluno_id: Optional[int]) -> Dict:
    """
    Retorna {"acertos": x, "erros": y, "total": z} para turma e opcionalmente aluno.
    """
    q = (
        db.session.query(
            func.count(Interacao.id).label("total"),
            func.coalesce(
                func.sum(case((Interacao.foi_correta.is_(False), 1), else_=0)),
                0,
            ).label("erros"),
        )
        .join(TentativaDesafio, TentativaDesafio.id == Interacao.tentativa_id)
        .filter(TentativaDesafio.turma_id == turma_id)
    )

    if aluno_id is not None:
        q = q.filter(TentativaDesafio.usuario_id == aluno_id)

    row = q.one()
    total = int(row.total or 0)
    erros = int(row.erros or 0)
    acertos = max(0, total - erros)
    return {"acertos": acertos, "erros": erros, "total": total}


def _kmeans_por_turma(turma_id: int, k: int) -> Tuple[Dict[int, int], Dict]:
    """
    Retorna:
      clusters: {aluno_id: grupo (1..k_eff)}
      chart_data: {labels: [...tópicos...], datasets: [{label, data:[%...]}, ...]}
    """
    alunos = _alunos_da_turma(turma_id)
    aluno_ids = [int(a.id) for a in alunos]
    if not aluno_ids:
        return {}, {"labels": [], "datasets": []}

    rows = (
        db.session.query(
            TentativaDesafio.usuario_id.label("usuario_id"),
            Interacao.topico_id.label("topico_id"),
            func.count(Interacao.id).label("total"),
            func.coalesce(func.sum(case((Interacao.foi_correta.is_(False), 1), else_=0)), 0).label("erros"),
        )
        .join(Interacao, Interacao.tentativa_id == TentativaDesafio.id)
        .filter(TentativaDesafio.turma_id == turma_id, TentativaDesafio.usuario_id.in_(aluno_ids))
        .group_by(TentativaDesafio.usuario_id, Interacao.topico_id)
        .all()
    )

    if not rows:
        return {}, {"labels": [], "datasets": []}

    # tópicos presentes
    topico_ids = sorted({int(r.topico_id) for r in rows if r.topico_id is not None})
    topicos_db = Topico.query.filter(Topico.id.in_(topico_ids)).all()
    nome_topico = {t.id: t.nome for t in topicos_db}

    # ordem fixa (por nome)
    topicos_ord = sorted(
        [{"id": int(tid), "nome": nome_topico.get(int(tid), f"Tópico {tid}")} for tid in topico_ids],
        key=lambda x: x["nome"].lower(),
    )
    feat_ids = [t["id"] for t in topicos_ord]

    # taxa (aluno, topico)
    taxa_map: Dict[Tuple[int, int], float] = {}
    for r in rows:
        total = int(r.total or 0)
        erros = int(r.erros or 0)
        taxa = (erros / total) if total else 0.0
        taxa_map[(int(r.usuario_id), int(r.topico_id))] = float(taxa)

    # médias globais por tópico (imputação)
    mean_by_topico = {}
    dados_turma = _dados_por_topico(turma_id, None)
    for dct in dados_turma:
        mean_by_topico[int(dct["topico_id"])] = float(dct["taxa_erro"])

    X: List[List[float]] = []
    for uid in aluno_ids:
        row = []
        for tid in feat_ids:
            row.append(taxa_map.get((uid, tid), mean_by_topico.get(tid, 0.0)))
        X.append(row)

    k_eff = max(1, min(int(k), len(aluno_ids)))
    labels0 = _kmeans_simple(X, k_eff, iters=80, seed=42)  # 0..k-1
    clusters = {int(aluno_ids[i]): int(labels0[i] + 1) for i in range(len(aluno_ids))}  # 1..k_eff

    # médias por grupo em cada tópico (para gráfico)
    sums = [[0.0 for _ in feat_ids] for _ in range(k_eff)]
    counts = [0 for _ in range(k_eff)]
    for i, uid in enumerate(aluno_ids):
        g = labels0[i]
        counts[g] += 1
        for j in range(len(feat_ids)):
            sums[g][j] += X[i][j]

    group_means: List[List[float]] = []
    for g in range(k_eff):
        if counts[g] == 0:
            group_means.append([0.0] * len(feat_ids))
        else:
            group_means.append([sums[g][j] / counts[g] for j in range(len(feat_ids))])

    chart_data = {
        "labels": [t["nome"] for t in topicos_ord],
        "datasets": [
            {"label": f"Grupo {g+1}", "data": [round(v * 100, 2) for v in group_means[g]]}
            for g in range(k_eff)
        ],
    }

    return clusters, chart_data


def _alunos_cards(turma_id: int, clusters: Dict[int, int]) -> List[Dict]:
    """
    Cards da tabela "Alunos da turma" com:
      - grupo (se tiver no clusters)
      - total de interações
      - taxa de erro global
    """
    alunos = _alunos_da_turma(turma_id)
    aluno_ids = [int(a.id) for a in alunos]
    if not aluno_ids:
        return []

    rows = (
        db.session.query(
            TentativaDesafio.usuario_id.label("uid"),
            func.count(Interacao.id).label("total"),
            func.coalesce(func.sum(case((Interacao.foi_correta.is_(False), 1), else_=0)), 0).label("erros"),
        )
        .join(Interacao, Interacao.tentativa_id == TentativaDesafio.id)
        .filter(TentativaDesafio.turma_id == turma_id, TentativaDesafio.usuario_id.in_(aluno_ids))
        .group_by(TentativaDesafio.usuario_id)
        .all()
    )
    stats = {int(r.uid): (int(r.total or 0), int(r.erros or 0)) for r in rows}

    cards = []
    for a in alunos:
        uid = int(a.id)
        total, erros = stats.get(uid, (0, 0))
        taxa = (erros / total) if total else 0.0
        cards.append(
            {
                "id": uid,
                "nome": a.nome,
                "email": a.email,
                "total": total,
                "taxa_erro": float(taxa),
                "grupo": clusters.get(uid),  # pode ser None
            }
        )

    # ordena por grupo depois nome
    cards.sort(key=lambda x: (x["grupo"] or 9999, (x["nome"] or "").lower()))
    return cards


# =========================
# ANÁLISE (K-means + Detalhes do aluno)
# =========================

from collections import defaultdict
import random
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, case
from flask import request
from flask_admin import BaseView, expose

# precisa existir no seu painel_admin.py:
# from .modelos import db, Usuario, Turma, Matricula, Topico, TentativaDesafio, Interacao
# class AdminAccessMixin: ...


def _parse_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return int(s)
    except Exception:
        return None


def _alunos_da_turma(turma_id: int):
    return (
        db.session.query(Usuario)
        .join(Matricula, Matricula.usuario_id == Usuario.id)
        .filter(Matricula.turma_id == turma_id, Matricula.papel == "aluno")
        .order_by(Usuario.nome.asc())
        .all()
    )


def _topicos_da_turma(turma_id: int) -> List[Tuple[int, str]]:
    rows = (
        db.session.query(Interacao.topico_id, Topico.nome)
        .join(TentativaDesafio, TentativaDesafio.id == Interacao.tentativa_id)
        .join(Topico, Topico.id == Interacao.topico_id)
        .filter(TentativaDesafio.turma_id == turma_id)
        .group_by(Interacao.topico_id, Topico.nome)
        .all()
    )
    topicos = [(int(r[0]), str(r[1])) for r in rows if r[0] is not None]
    topicos.sort(key=lambda x: x[1].lower())
    return topicos


def _dados_por_topico(turma_id: int, aluno_id: Optional[int]) -> List[Dict[str, Any]]:
    q = (
        db.session.query(
            Interacao.topico_id.label("topico_id"),
            Topico.nome.label("topico_nome"),
            func.count(Interacao.id).label("total"),
            func.coalesce(func.sum(case((Interacao.foi_correta.is_(False), 1), else_=0)), 0).label("erros"),
        )
        .join(TentativaDesafio, TentativaDesafio.id == Interacao.tentativa_id)
        .join(Topico, Topico.id == Interacao.topico_id)
        .filter(TentativaDesafio.turma_id == turma_id)
    )
    if aluno_id is not None:
        q = q.filter(TentativaDesafio.usuario_id == aluno_id)

    rows = q.group_by(Interacao.topico_id, Topico.nome).all()

    out: List[Dict[str, Any]] = []
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
    out.sort(key=lambda d: d["topico_nome"].lower())
    return out


def _donut_data(turma_id: int, aluno_id: Optional[int]) -> Tuple[int, Dict[str, int]]:
    q = (
        db.session.query(
            func.count(Interacao.id).label("total"),
            func.coalesce(func.sum(case((Interacao.foi_correta.is_(False), 1), else_=0)), 0).label("erros"),
        )
        .join(TentativaDesafio, TentativaDesafio.id == Interacao.tentativa_id)
        .filter(TentativaDesafio.turma_id == turma_id)
    )
    if aluno_id is not None:
        q = q.filter(TentativaDesafio.usuario_id == aluno_id)

    r = q.one()
    total = int(r.total or 0)
    erros = int(r.erros or 0)
    acertos = max(0, total - erros)
    return total, {"acertos": acertos, "erros": erros, "total": total}


def _kmeans_simple(X: List[List[float]], k: int, iters: int = 50, seed: int = 42) -> List[int]:
    n = len(X)
    if n == 0:
        return []
    d = len(X[0]) if X[0] else 0
    if d == 0:
        return [0] * n

    k = max(1, min(int(k), n))
    rnd = random.Random(seed)
    centroids = [X[i][:] for i in rnd.sample(range(n), k)]
    labels = [0] * n

    def dist2(a: List[float], b: List[float]) -> float:
        return sum((a[j] - b[j]) ** 2 for j in range(d))

    for _ in range(iters):
        changed = False

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

        sums = [[0.0] * d for _ in range(k)]
        counts = [0] * k
        for i in range(n):
            c = labels[i]
            counts[c] += 1
            for j in range(d):
                sums[c][j] += X[i][j]

        for c in range(k):
            if counts[c] == 0:
                centroids[c] = X[rnd.randrange(n)][:]  # reinit
            else:
                centroids[c] = [sums[c][j] / counts[c] for j in range(d)]

        if not changed:
            break

    return labels


def _kmeans_por_turma(turma_id: int, k: int) -> Tuple[Dict[int, int], Dict[str, Any]]:
    alunos = _alunos_da_turma(turma_id)
    aluno_ids = [int(a.id) for a in alunos]
    if not aluno_ids:
        return {}, {"labels": [], "datasets": []}

    topicos = _topicos_da_turma(turma_id)
    if not topicos:
        return {}, {"labels": [], "datasets": []}

    feat_ids = [tid for tid, _ in topicos]
    feat_names = [nome for _, nome in topicos]

    rows = (
        db.session.query(
            TentativaDesafio.usuario_id.label("uid"),
            Interacao.topico_id.label("tid"),
            func.count(Interacao.id).label("total"),
            func.coalesce(func.sum(case((Interacao.foi_correta.is_(False), 1), else_=0)), 0).label("erros"),
        )
        .join(Interacao, Interacao.tentativa_id == TentativaDesafio.id)
        .filter(TentativaDesafio.turma_id == turma_id, TentativaDesafio.usuario_id.in_(aluno_ids))
        .group_by(TentativaDesafio.usuario_id, Interacao.topico_id)
        .all()
    )

    taxa_map: Dict[Tuple[int, int], float] = {}
    for r in rows:
        total = int(r.total or 0)
        erros = int(r.erros or 0)
        taxa_map[(int(r.uid), int(r.tid))] = (erros / total) if total else 0.0

    mean_by_topic: Dict[int, float] = {}
    for tid in feat_ids:
        vals = [v for (uid, t), v in taxa_map.items() if t == tid]
        mean_by_topic[tid] = (sum(vals) / len(vals)) if vals else 0.0

    used_ids: List[int] = []
    X: List[List[float]] = []
    for uid in aluno_ids:
        has_any = any((uid, tid) in taxa_map for tid in feat_ids)
        if not has_any:
            continue
        used_ids.append(uid)
        X.append([float(taxa_map.get((uid, tid), mean_by_topic.get(tid, 0.0))) for tid in feat_ids])

    if not used_ids:
        return {}, {"labels": [], "datasets": []}

    k_eff = max(1, min(int(k), len(used_ids)))
    labels0 = _kmeans_simple(X, k_eff, iters=60, seed=42)

    clusters: Dict[int, int] = {used_ids[i]: int(labels0[i] + 1) for i in range(len(used_ids))}

    sums = [[0.0 for _ in feat_ids] for _ in range(k_eff)]
    counts = [0 for _ in range(k_eff)]
    for i, _uid in enumerate(used_ids):
        g = labels0[i]
        counts[g] += 1
        for j in range(len(feat_ids)):
            sums[g][j] += X[i][j]

    datasets = []
    for g in range(k_eff):
        denom = counts[g] if counts[g] else 1
        data_pct = [round((sums[g][j] / denom) * 100, 2) for j in range(len(feat_ids))]
        datasets.append({"label": f"Grupo {g+1} (n={counts[g]})", "data": data_pct})

    chart_data = {"labels": feat_names, "datasets": datasets}
    return clusters, chart_data


def _alunos_cards(turma_id: int, clusters: Dict[int, int]) -> List[Dict[str, Any]]:
    alunos = _alunos_da_turma(turma_id)
    aluno_ids = [int(a.id) for a in alunos]
    if not aluno_ids:
        return []

    rows = (
        db.session.query(
            TentativaDesafio.usuario_id.label("uid"),
            func.count(Interacao.id).label("total"),
            func.coalesce(func.sum(case((Interacao.foi_correta.is_(False), 1), else_=0)), 0).label("erros"),
        )
        .join(Interacao, Interacao.tentativa_id == TentativaDesafio.id)
        .filter(TentativaDesafio.turma_id == turma_id, TentativaDesafio.usuario_id.in_(aluno_ids))
        .group_by(TentativaDesafio.usuario_id)
        .all()
    )
    stats = {int(r.uid): (int(r.total or 0), int(r.erros or 0)) for r in rows}

    cards: List[Dict[str, Any]] = []
    for a in alunos:
        uid = int(a.id)
        total, erros = stats.get(uid, (0, 0))
        taxa = (erros / total) if total else 0.0
        cards.append(
            {
                "id": uid,
                "nome": a.nome,
                "email": a.email,
                "total": total,
                "taxa_erro": float(taxa),
                "grupo": clusters.get(uid),
            }
        )
    return cards


def _aluno_matriz(turma_id: int, aluno_id: int) -> List[Dict[str, Any]]:
    # tabela horizontal: uma coluna por tópico (ordem fixa da turma)
    topicos = _topicos_da_turma(turma_id)
    base = {
        tid: {"topico_id": tid, "topico_nome": nome, "total": 0, "erros": 0, "taxa_erro": 0.0}
        for tid, nome in topicos
    }

    rows = _dados_por_topico(turma_id, aluno_id)
    for r in rows:
        base[int(r["topico_id"])] = r

    out = list(base.values())
    out.sort(key=lambda d: d["topico_nome"].lower())
    return out


class AnaliseView(AdminAccessMixin, BaseView):
    @expose("/", methods=("GET",))
    def index(self):
        turmas = Turma.query.order_by(Turma.nome.asc()).all()

        turma_id = _parse_int(request.args.get("turma_id"))
        aluno_id = _parse_int(request.args.get("aluno_id"))
        k = _parse_int(request.args.get("k")) or 3
        k = max(1, min(int(k), 10))

        ctx: Dict[str, Any] = {
            "turmas": turmas,
            "turma_id": turma_id,
            "aluno_id": aluno_id,
            "k": k,
            "chart_data": {"labels": [], "datasets": []},
            "dados_turma": [],
            "total_interacoes_turma": 0,
            "donut_turma": {"acertos": 0, "erros": 0, "total": 0},
            "alunos_cards": [],
            # detalhes aluno
            "aluno_grupo": None,
            "aluno_selecionado": None,
            "aluno_topicos": [],
            "total_interacoes_aluno": 0,
            "donut_aluno": {"acertos": 0, "erros": 0, "total": 0},
        }

        if not turma_id:
            return self.render("admin/analise.html", **ctx)

        # valida aluno_id pertence à turma
        if aluno_id is not None:
            ids_turma = {int(a.id) for a in _alunos_da_turma(turma_id)}
            if int(aluno_id) not in ids_turma:
                aluno_id = None
                ctx["aluno_id"] = None

        clusters, chart = _kmeans_por_turma(turma_id, k)
        ctx["chart_data"] = chart
        ctx["alunos_cards"] = _alunos_cards(turma_id, clusters)

        ctx["dados_turma"] = _dados_por_topico(turma_id, None)
        tot_t, donut_t = _donut_data(turma_id, None)
        ctx["total_interacoes_turma"] = tot_t
        ctx["donut_turma"] = donut_t

        if aluno_id is not None:
            ctx["aluno_grupo"] = clusters.get(int(aluno_id))
            aobj = db.session.get(Usuario, int(aluno_id))
            if aobj:
                ctx["aluno_selecionado"] = {"id": int(aobj.id), "nome": aobj.nome, "email": aobj.email}

            ctx["aluno_topicos"] = _aluno_matriz(turma_id, int(aluno_id))
            tot_a, donut_a = _donut_data(turma_id, int(aluno_id))
            ctx["total_interacoes_aluno"] = tot_a
            ctx["donut_aluno"] = donut_a

        return self.render("admin/analise.html", **ctx)


# ============================================================
# Hubs (Turmas / Alunos / Conteúdos / Atividades / Usuários)
# (mantidos como você já tinha)
# ============================================================

def _salvar_imagem_enunciado(file_storage):
    """
    Salva arquivo em: /static/uploads/enunciados/
    Retorna string relativa para salvar no banco: "uploads/enunciados/<nome>"
    """
    if not file_storage or not getattr(file_storage, "filename", ""):
        return None

    filename = secure_filename(file_storage.filename)
    ext = Path(filename).suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        raise ValueError("Formato de imagem inválido. Use PNG/JPG/WebP/GIF.")

    upload_dir = Path(current_app.static_folder) / "uploads" / "enunciados"
    upload_dir.mkdir(parents=True, exist_ok=True)

    new_name = f"en_{uuid.uuid4().hex}{ext}"
    dest = upload_dir / new_name
    file_storage.save(dest)

    return f"uploads/enunciados/{new_name}"


class TurmasHubView(AdminAccessMixin, BaseView):
    @expose("/", methods=("GET", "POST"))
    def index(self):
        if request.method == "POST":
            action = request.form.get("action", "")

            if action == "create_turma":
                nome = (request.form.get("nome") or "").strip()
                codigo = (request.form.get("codigo") or "").strip()
                descricao = (request.form.get("descricao") or "").strip()

                if not nome or not codigo:
                    flash("Nome e código são obrigatórios.", "error")
                elif Turma.query.filter_by(codigo=codigo).first():
                    flash("Já existe uma turma com esse código.", "error")
                else:
                    db.session.add(Turma(nome=nome, codigo=codigo, descricao=descricao))
                    db.session.commit()
                    flash("Turma criada com sucesso.", "success")

                return redirect(url_for("turmas.index"))

            if action == "edit_turma":
                turma_id = request.form.get("turma_id")
                nome = (request.form.get("nome") or "").strip()
                codigo = (request.form.get("codigo") or "").strip()
                descricao = (request.form.get("descricao") or "").strip()

                turma = Turma.query.get(int(turma_id)) if turma_id else None
                if not turma:
                    flash("Turma inválida.", "error")
                    return redirect(url_for("turmas.index"))

                if not nome or not codigo:
                    flash("Nome e código são obrigatórios.", "error")
                    return redirect(url_for("turmas.index"))

                existe = Turma.query.filter(Turma.codigo == codigo, Turma.id != turma.id).first()
                if existe:
                    flash("Já existe outra turma com esse código.", "error")
                    return redirect(url_for("turmas.index"))

                turma.nome = nome
                turma.codigo = codigo
                turma.descricao = descricao
                db.session.commit()
                flash("Turma atualizada.", "success")
                return redirect(url_for("turmas.index"))

            if action == "delete_turma":
                turma_id = request.form.get("turma_id")
                turma = Turma.query.get(int(turma_id)) if turma_id else None
                if not turma:
                    flash("Turma inválida.", "error")
                    return redirect(url_for("turmas.index"))

                Matricula.query.filter_by(turma_id=turma.id).delete(synchronize_session=False)
                try:
                    turma.disciplinas = []
                except Exception:
                    pass

                db.session.delete(turma)
                db.session.commit()
                flash("Turma removida.", "success")
                return redirect(url_for("turmas.index"))

            if action == "set_disciplinas":
                turma_id = request.form.get("turma_id")
                ids = request.form.getlist("disciplina_ids")

                turma = Turma.query.get(int(turma_id)) if turma_id else None
                if not turma:
                    flash("Turma inválida.", "error")
                    return redirect(url_for("turmas.index"))

                selecionadas = []
                if ids:
                    selecionadas = Disciplina.query.filter(Disciplina.id.in_([int(x) for x in ids])).all()

                turma.disciplinas = selecionadas
                db.session.commit()
                flash("Disciplinas atualizadas.", "success")
                return redirect(url_for("turmas.index"))

            if action == "add_alunos":
                turma_id = request.form.get("turma_id")
                usuario_ids = request.form.getlist("usuario_ids")

                turma = Turma.query.get(int(turma_id)) if turma_id else None
                if not turma:
                    flash("Turma inválida.", "error")
                    return redirect(url_for("turmas.index"))

                added = 0
                for uid in usuario_ids:
                    uid_int = int(uid)
                    existe = Matricula.query.filter_by(turma_id=turma.id, usuario_id=uid_int).first()
                    if not existe:
                        db.session.add(Matricula(turma_id=turma.id, usuario_id=uid_int, papel="aluno"))
                        added += 1

                db.session.commit()
                flash(f"{added} aluno(s) matriculado(s).", "success")
                return redirect(url_for("turmas.index"))

            if action == "remove_aluno":
                turma_id = request.form.get("turma_id")
                usuario_id = request.form.get("usuario_id")

                if not turma_id or not usuario_id:
                    flash("Dados inválidos.", "error")
                    return redirect(url_for("turmas.index"))

                Matricula.query.filter_by(
                    turma_id=int(turma_id),
                    usuario_id=int(usuario_id),
                    papel="aluno",
                ).delete(synchronize_session=False)

                db.session.commit()
                flash("Aluno removido da turma.", "success")
                return redirect(url_for("turmas.index"))

            return redirect(url_for("turmas.index"))

        turmas = Turma.query.order_by(Turma.criado_em.desc()).all()
        alunos = Usuario.query.filter(Usuario.is_admin == False).order_by(Usuario.nome.asc()).all()  # noqa: E712
        disciplinas = Disciplina.query.order_by(Disciplina.nome.asc()).all()

        cards = []
        for t in turmas:
            alunos_q = (
                db.session.query(Usuario)
                .join(Matricula, Matricula.usuario_id == Usuario.id)
                .filter(Matricula.turma_id == t.id, Matricula.papel == "aluno")
                .order_by(Usuario.nome.asc())
                .all()
            )
            cards.append(
                {
                    "id": t.id,
                    "nome": t.nome,
                    "codigo": t.codigo,
                    "descricao": t.descricao or "",
                    "alunos": alunos_q,
                    "n_alunos": len(alunos_q),
                    "disciplinas": list(getattr(t, "disciplinas", [])),
                    "n_disciplinas": len(getattr(t, "disciplinas", [])),
                }
            )

        return self.render(
            "admin/turmas_hub.html",
            turmas_cards=cards,
            alunos=alunos,
            disciplinas=disciplinas,
        )


class AlunosHubView(AdminAccessMixin, BaseView):
    @expose("/", methods=("GET", "POST"))
    def index(self):
        if request.method == "POST":
            action = request.form.get("action", "")

            if action == "create_aluno":
                nome = (request.form.get("nome") or "").strip()
                email = (request.form.get("email") or "").strip().lower()
                senha = (request.form.get("senha") or "").strip()

                if not nome or not email or not senha:
                    flash("Nome, e-mail e senha são obrigatórios.", "error")
                elif Usuario.query.filter_by(email=email).first():
                    flash("Já existe um usuário com esse e-mail.", "error")
                else:
                    u = Usuario(
                        nome=nome,
                        email=email,
                        senha_hash=generate_password_hash(senha),
                        is_admin=False,
                    )
                    db.session.add(u)
                    db.session.commit()
                    flash("Aluno criado com sucesso.", "success")

            elif action == "matricular_em_turmas":
                usuario_id = request.form.get("usuario_id")
                turma_ids = request.form.getlist("turma_ids")

                aluno = Usuario.query.get(int(usuario_id)) if usuario_id else None
                if not aluno:
                    flash("Aluno inválido.", "error")
                else:
                    added = 0
                    for tid in turma_ids:
                        tid_int = int(tid)
                        existe = Matricula.query.filter_by(turma_id=tid_int, usuario_id=aluno.id).first()
                        if not existe:
                            db.session.add(Matricula(turma_id=tid_int, usuario_id=aluno.id, papel="aluno"))
                            added += 1
                    db.session.commit()
                    flash(f"{added} matrícula(s) criada(s).", "success")

            return redirect(url_for("alunos.index"))

        q = (request.args.get("q") or "").strip().lower()
        alunos_query = Usuario.query.filter(Usuario.is_admin == False)  # noqa: E712
        if q:
            alunos_query = alunos_query.filter(
                db.or_(
                    Usuario.nome.ilike(f"%{q}%"),
                    Usuario.email.ilike(f"%{q}%"),
                )
            )
        alunos = alunos_query.order_by(Usuario.nome.asc()).all()
        turmas = Turma.query.order_by(Turma.nome.asc()).all()

        cards = []
        for a in alunos:
            turmas_do_aluno = (
                db.session.query(Turma)
                .join(Matricula, Matricula.turma_id == Turma.id)
                .filter(Matricula.usuario_id == a.id)
                .order_by(Turma.nome.asc())
                .all()
            )
            cards.append(
                {
                    "id": a.id,
                    "nome": a.nome,
                    "email": a.email,
                    "turmas": turmas_do_aluno,
                }
            )

        return self.render(
            "admin/alunos_hub.html",
            alunos_cards=cards,
            turmas=turmas,
            q=q,
        )


class ConteudosHubView(AdminAccessMixin, BaseView):
    @expose("/", methods=("GET", "POST"))
    def index(self):
        if request.method == "POST":
            action = request.form.get("action", "")

            if action == "create_disciplina":
                nome = (request.form.get("nome") or "").strip()
                descricao = (request.form.get("descricao") or "").strip()

                if not nome:
                    flash("Nome da disciplina é obrigatório.", "error")
                elif Disciplina.query.filter_by(nome=nome).first():
                    flash("Já existe uma disciplina com esse nome.", "error")
                else:
                    db.session.add(Disciplina(nome=nome, descricao=descricao))
                    db.session.commit()
                    flash("Disciplina criada com sucesso.", "success")

            elif action == "create_topico":
                disciplina_id = request.form.get("disciplina_id")
                nome = (request.form.get("nome") or "").strip()
                descricao = (request.form.get("descricao") or "").strip()

                if not disciplina_id or not nome:
                    flash("Disciplina e nome do tópico são obrigatórios.", "error")
                else:
                    d = Disciplina.query.get(int(disciplina_id))
                    if not d:
                        flash("Disciplina inválida.", "error")
                    else:
                        existe = Topico.query.filter_by(disciplina_id=d.id, nome=nome).first()
                        if existe:
                            flash("Já existe um tópico com esse nome nessa disciplina.", "error")
                        else:
                            db.session.add(Topico(disciplina_id=d.id, nome=nome, descricao=descricao))
                            db.session.commit()
                            flash("Tópico criado com sucesso.", "success")

            elif action == "delete_disciplina":
                did = request.form.get("id")
                d = Disciplina.query.get(int(did)) if did else None
                if not d:
                    flash("Disciplina inválida.", "error")
                else:
                    db.session.delete(d)
                    db.session.commit()
                    flash("Disciplina removida.", "success")

            elif action == "delete_topico":
                tid = request.form.get("id")
                t = Topico.query.get(int(tid)) if tid else None
                if not t:
                    flash("Tópico inválido.", "error")
                else:
                    db.session.delete(t)
                    db.session.commit()
                    flash("Tópico removido.", "success")

            return redirect(url_for("conteudos.index"))

        disciplinas = Disciplina.query.order_by(Disciplina.nome.asc()).all()

        disciplinas_cards = []
        for d in disciplinas:
            topics = []
            for t in d.topicos:
                n_desafios = len(t.desafios)
                n_perguntas = 0
                for des in t.desafios:
                    n_perguntas += len(des.perguntas)
                topics.append(
                    {
                        "id": t.id,
                        "nome": t.nome,
                        "descricao": t.descricao or "",
                        "n_desafios": n_desafios,
                        "n_perguntas": n_perguntas,
                    }
                )

            disciplinas_cards.append(
                {
                    "id": d.id,
                    "nome": d.nome,
                    "descricao": d.descricao or "",
                    "n_topicos": len(topics),
                    "topicos": topics,
                }
            )

        return self.render(
            "admin/conteudos.html",
            disciplinas_cards=disciplinas_cards,
            disciplinas_dropdown=disciplinas,
        )


def _save_enunciado_image(file_storage):
    """
    Salva em: app/static/uploads/enunciados/
    Retorna caminho RELATIVO ao static: 'uploads/enunciados/en_xxx.jpg'
    """
    if not file_storage or not getattr(file_storage, "filename", ""):
        return None

    filename = secure_filename(file_storage.filename)
    if "." not in filename:
        raise ValueError("Arquivo de imagem sem extensão.")

    ext = filename.rsplit(".", 1)[1].lower().strip()
    if ext not in ALLOWED_IMG_EXT:
        raise ValueError("Extensão de imagem não permitida.")

    newname = f"en_{uuid.uuid4().hex}.{ext}"
    relpath = f"uploads/enunciados/{newname}"
    abspath = os.path.join(current_app.static_folder, relpath)

    os.makedirs(os.path.dirname(abspath), exist_ok=True)
    file_storage.save(abspath)
    return relpath


def _try_delete_static_file(relpath: str | None):
    """
    Remove arquivo se estiver dentro do static/uploads/enunciados.
    """
    if not relpath:
        return
    rel = str(relpath).replace("\\", "/").lstrip("/")
    if rel.lower() in {"none", "null", ""}:
        return
    if not rel.startswith("uploads/enunciados/"):
        return
    abspath = os.path.join(current_app.static_folder, rel)
    try:
        if os.path.exists(abspath):
            os.remove(abspath)
    except Exception:
        pass


def _preview_text(d: Desafio) -> str:
    txt = (getattr(d, "enunciado_texto", "") or "").strip()
    if not txt:
        txt = (getattr(d, "enunciado_latex", "") or "").strip()
    if not txt:
        return ""
    txt = " ".join(txt.split())
    return (txt[:140] + "…") if len(txt) > 140 else txt


class AtividadesHubView(BaseView):
    """
    View /admin/atividades
    Compatível com o template: app/templates/admin/atividades.html (que te enviei)
    """

    def is_accessible(self):
        return bool(getattr(current_user, "is_authenticated", False) and getattr(current_user, "is_admin", False))

    def inaccessible_callback(self, name, **kwargs):
        flash("Faça login como administrador.", "warning")
        return redirect(url_for("site.entrar"))

    @expose("/", methods=["GET", "POST"])
    def index(self):
        # ---------- POST (ações) ----------
        if request.method == "POST":
            action = (request.form.get("action") or "").strip()

            # ===== create_desafio =====
            if action == "create_desafio":
                topico_id = int(request.form.get("topico_id") or 0)
                titulo = (request.form.get("titulo") or "").strip()
                enunciado_texto = (request.form.get("enunciado_texto") or "").strip()

                if not topico_id or not titulo:
                    flash("Preencha tópico e título.", "warning")
                    return redirect(url_for("atividades.index"))

                img_file = request.files.get("enunciado_imagem")
                img_rel = None
                try:
                    img_rel = _save_enunciado_image(img_file)
                except ValueError as e:
                    flash(str(e), "danger")
                    return redirect(url_for("atividades.index"))

                d = Desafio(
                    topico_id=topico_id,
                    titulo=titulo,
                    enunciado_texto=enunciado_texto,
                    enunciado_imagem=img_rel,  # <-- None ou 'uploads/enunciados/...'
                )
                db.session.add(d)
                db.session.commit()
                flash("Questão criada com sucesso.", "success")
                return redirect(url_for("atividades.index"))

            # ===== edit_desafio =====
            if action == "edit_desafio":
                desafio_id = int(request.form.get("desafio_id") or 0)
                topico_id = int(request.form.get("topico_id") or 0)
                titulo = (request.form.get("titulo") or "").strip()
                enunciado_texto = (request.form.get("enunciado_texto") or "").strip()

                if not desafio_id:
                    flash("ID da questão inválido.", "danger")
                    return redirect(url_for("atividades.index"))

                d = db.session.get(Desafio, desafio_id)
                if not d:
                    flash("Questão não encontrada.", "danger")
                    return redirect(url_for("atividades.index"))

                if not topico_id or not titulo:
                    flash("Preencha tópico e título.", "warning")
                    return redirect(url_for("atividades.index"))

                d.topico_id = topico_id
                d.titulo = titulo
                d.enunciado_texto = enunciado_texto

                # remover imagem atual
                remover = (request.form.get("remover_imagem") or "").strip() == "1"
                if remover:
                    _try_delete_static_file(d.enunciado_imagem)
                    d.enunciado_imagem = None

                # trocar imagem (se enviou)
                img_file = request.files.get("enunciado_imagem")
                if img_file and getattr(img_file, "filename", ""):
                    try:
                        new_rel = _save_enunciado_image(img_file)
                    except ValueError as e:
                        flash(str(e), "danger")
                        return redirect(url_for("atividades.index"))

                    _try_delete_static_file(d.enunciado_imagem)
                    d.enunciado_imagem = new_rel

                # evita gravar "None" string
                if isinstance(d.enunciado_imagem, str) and d.enunciado_imagem.lower().strip() in {"none", "null", ""}:
                    d.enunciado_imagem = None

                db.session.commit()
                flash("Questão atualizada com sucesso.", "success")
                return redirect(url_for("atividades.index"))

            # ===== delete_desafio =====
            if action == "delete_desafio":
                desafio_id = int(request.form.get("id") or 0)
                d = db.session.get(Desafio, desafio_id)
                if not d:
                    flash("Questão não encontrada.", "warning")
                    return redirect(url_for("atividades.index"))

                # apaga imagem do disco
                _try_delete_static_file(getattr(d, "enunciado_imagem", None))

                # apaga perguntas vinculadas
                Pergunta.query.filter_by(desafio_id=d.id).delete()
                db.session.delete(d)
                db.session.commit()

                flash("Questão removida.", "success")
                return redirect(url_for("atividades.index"))

            # ===== create_pergunta =====
            if action == "create_pergunta":
                desafio_id = int(request.form.get("desafio_id") or 0)
                enunciado = (request.form.get("enunciado") or "").strip()
                alt_a = (request.form.get("alt_a") or "").strip()
                alt_b = (request.form.get("alt_b") or "").strip()
                alt_c = (request.form.get("alt_c") or "").strip() or None
                alt_d = (request.form.get("alt_d") or "").strip() or None
                correta = (request.form.get("correta") or "a").strip().lower()

                if not desafio_id or not enunciado or not alt_a or not alt_b:
                    flash("Preencha questão, enunciado e alternativas A/B.", "warning")
                    return redirect(url_for("atividades.index"))

                if correta not in {"a", "b", "c", "d"}:
                    correta = "a"

                p = Pergunta(
                    desafio_id=desafio_id,
                    enunciado=enunciado,
                    alt_a=alt_a,
                    alt_b=alt_b,
                    alt_c=alt_c,
                    alt_d=alt_d,
                    correta=correta,
                )
                db.session.add(p)
                db.session.commit()
                flash("Pergunta criada.", "success")
                return redirect(url_for("atividades.index"))

            # ===== edit_pergunta =====
            if action == "edit_pergunta":
                pergunta_id = int(request.form.get("pergunta_id") or 0)
                desafio_id = int(request.form.get("desafio_id") or 0)
                p = db.session.get(Pergunta, pergunta_id)
                if not p:
                    flash("Pergunta não encontrada.", "warning")
                    return redirect(url_for("atividades.index"))

                p.desafio_id = desafio_id or p.desafio_id
                p.enunciado = (request.form.get("enunciado") or "").strip()
                p.alt_a = (request.form.get("alt_a") or "").strip()
                p.alt_b = (request.form.get("alt_b") or "").strip()
                p.alt_c = (request.form.get("alt_c") or "").strip() or None
                p.alt_d = (request.form.get("alt_d") or "").strip() or None

                correta = (request.form.get("correta") or "a").strip().lower()
                p.correta = correta if correta in {"a", "b", "c", "d"} else "a"

                db.session.commit()
                flash("Pergunta atualizada.", "success")
                return redirect(url_for("atividades.index"))

            # ===== delete_pergunta =====
            if action == "delete_pergunta":
                pergunta_id = int(request.form.get("id") or 0)
                p = db.session.get(Pergunta, pergunta_id)
                if not p:
                    flash("Pergunta não encontrada.", "warning")
                    return redirect(url_for("atividades.index"))
                db.session.delete(p)
                db.session.commit()
                flash("Pergunta removida.", "success")
                return redirect(url_for("atividades.index"))

            flash("Ação inválida.", "warning")
            return redirect(url_for("atividades.index"))

        # ---------- GET (render) ----------
        disciplina_id = request.args.get("disciplina_id", type=int)
        topico_id = request.args.get("topico_id", type=int)

        disciplinas_dropdown = Disciplina.query.order_by(Disciplina.nome.asc()).all()

        topicos_dropdown = (
            Topico.query.join(Disciplina, Topico.disciplina_id == Disciplina.id)
            .order_by(Disciplina.nome.asc(), Topico.nome.asc())
            .all()
        )

        topicos_q = Topico.query.join(Disciplina, Topico.disciplina_id == Disciplina.id)
        if disciplina_id:
            topicos_q = topicos_q.filter(Topico.disciplina_id == disciplina_id)
        if topico_id:
            topicos_q = topicos_q.filter(Topico.id == topico_id)

        topicos = topicos_q.order_by(Disciplina.nome.asc(), Topico.nome.asc()).all()

        # Para os selects dos modais
        topicos_all = (
            Topico.query.join(Disciplina, Topico.disciplina_id == Disciplina.id)
            .order_by(Disciplina.nome.asc(), Topico.nome.asc())
            .all()
        )
        desafios_all = (
            Desafio.query.join(Topico, Desafio.topico_id == Topico.id)
            .join(Disciplina, Topico.disciplina_id == Disciplina.id)
            .order_by(Disciplina.nome.asc(), Topico.nome.asc(), Desafio.id.desc())
            .all()
        )

        topicos_cards = []
        for t in topicos:
            desafios = (
                Desafio.query.filter_by(topico_id=t.id)
                .order_by(Desafio.id.desc())
                .all()
            )

            desafios_payload = []
            n_perguntas_total = 0

            for d in desafios:
                perguntas = Pergunta.query.filter_by(desafio_id=d.id).order_by(Pergunta.id.asc()).all()
                n_perguntas_total += len(perguntas)

                img = getattr(d, "enunciado_imagem", None)
                if isinstance(img, str) and img.lower().strip() in {"none", "null", ""}:
                    img = None

                desafios_payload.append({
                    "id": d.id,
                    "titulo": d.titulo,
                    "enunciado_texto": getattr(d, "enunciado_texto", "") or "",
                    "enunciado_imagem": img,  # <-- None ou 'uploads/...'
                    "preview": _preview_text(d),
                    "n_perguntas": len(perguntas),
                    "perguntas": perguntas,
                })

            topicos_cards.append({
                "topico_id": t.id,
                "topico_nome": t.nome,
                "topico_descricao": getattr(t, "descricao", "") or "",
                "disciplina_nome": t.disciplina.nome if t.disciplina else "",
                "n_desafios": len(desafios),
                "n_perguntas": n_perguntas_total,
                "desafios": desafios_payload
            })

        return self.render(
            "admin/atividades.html",
            disciplinas_dropdown=disciplinas_dropdown,
            topicos_dropdown=topicos_dropdown,
            topicos_cards=topicos_cards,
            topicos_all=topicos_all,
            desafios_all=desafios_all,
            disciplina_id=disciplina_id,
            topico_id=topico_id
        )


class UsuariosHubView(AdminAccessMixin, BaseView):
    @expose("/", methods=("GET", "POST"))
    def index(self):
        if request.method == "POST":
            action = request.form.get("action", "")

            if action == "toggle_admin":
                usuario_id = request.form.get("usuario_id")
                is_admin_raw = request.form.get("is_admin", "0")

                u = Usuario.query.get(int(usuario_id)) if usuario_id else None
                if not u:
                    flash("Usuário inválido.", "error")
                    return redirect(url_for("usuarios.index"))

                if u.id == current_user.id and str(is_admin_raw) in ("0", "false", "False"):
                    flash("Você não pode remover seu próprio acesso de admin.", "error")
                    return redirect(url_for("usuarios.index"))

                u.is_admin = True if str(is_admin_raw) == "1" else False
                db.session.commit()
                flash("Permissão atualizada.", "success")
                return redirect(url_for("usuarios.index", q=request.args.get("q", "")))

            flash("Ação inválida.", "error")
            return redirect(url_for("usuarios.index"))

        q = (request.args.get("q") or "").strip().lower()
        only_admin = (request.args.get("only_admin") or "").strip()

        query = Usuario.query
        if q:
            query = query.filter(
                db.or_(
                    Usuario.nome.ilike(f"%{q}%"),
                    Usuario.email.ilike(f"%{q}%"),
                )
            )
        if only_admin == "1":
            query = query.filter(Usuario.is_admin == True)  # noqa: E712

        usuarios = query.order_by(Usuario.is_admin.desc(), Usuario.nome.asc()).all()

        cards = []
        for u in usuarios:
            cards.append(
                {
                    "id": u.id,
                    "nome": u.nome,
                    "email": u.email,
                    "is_admin": bool(u.is_admin),
                    "criado_em": u.criado_em,
                }
            )

        return self.render(
            "admin/usuarios_hub.html",
            usuarios_cards=cards,
            q=q,
            only_admin=only_admin,
        )


# ============================================================
# Admin factory
# ============================================================


def configurar_admin(app):
    admin = Admin(
        app,
        name="Solve WM",
        url="/admin",
        index_view=SecureIndexView(url="/admin"),
        template_mode="bootstrap4",
    )

    admin.add_view(TurmasHubView(name="Turmas", endpoint="turmas", url="/admin/turmas"))
    admin.add_view(AlunosHubView(name="Alunos", endpoint="alunos", url="/admin/alunos"))
    admin.add_view(ConteudosHubView(name="Conteúdos", endpoint="conteudos", url="/admin/conteudos"))
    admin.add_view(AtividadesHubView(name="Atividades", endpoint="atividades", url="/admin/atividades"))
    admin.add_view(AnaliseView(name="Análise", endpoint="analise", url="/admin/analise"))
    admin.add_view(UsuariosHubView(name="Usuários", endpoint="usuarios", url="/admin/usuarios"))

    # CRUDs antigos (fallback)
    admin.add_view(SecureModelView(Turma, db.session, name="Turmas (CRUD)", endpoint="turma"))
    admin.add_view(SecureModelView(Matricula, db.session, name="Matrículas (CRUD)", endpoint="matricula"))
    admin.add_view(SecureModelView(Disciplina, db.session, name="Disciplinas (CRUD)", endpoint="disciplina"))
    admin.add_view(SecureModelView(Topico, db.session, name="Tópicos (CRUD)", endpoint="topico"))
    admin.add_view(SecureModelView(Desafio, db.session, name="Desafios (CRUD)", endpoint="desafio"))
    admin.add_view(SecureModelView(Pergunta, db.session, name="Perguntas (CRUD)", endpoint="pergunta"))
    admin.add_view(SecureModelView(Usuario, db.session, name="Usuários (CRUD)", endpoint="usuario"))

    return admin
