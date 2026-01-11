from __future__ import annotations

from sqlalchemy import func, case
from typing import Optional, Any

from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.exc import IntegrityError

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

# =========================
# Usuários / Auth
# =========================

def criar_usuario(nome: str, email: str, senha: str, is_admin: bool = False) -> Usuario:
    email = email.strip().lower()
    u = Usuario(
        nome=nome.strip(),
        email=email,
        senha_hash=generate_password_hash(senha),
        is_admin=is_admin,
    )
    db.session.add(u)
    db.session.commit()
    return u


def autenticar_usuario(email: str, senha: str) -> Optional[Usuario]:
    email = email.strip().lower()
    u = Usuario.query.filter_by(email=email).first()
    if not u:
        return None
    if not check_password_hash(u.senha_hash, senha):
        return None
    return u


def obter_usuario(usuario_id: int) -> Optional[Usuario]:
    return Usuario.query.get(usuario_id)


# =========================
# Turmas / Matrículas
# =========================

def buscar_turma_por_codigo(codigo: str) -> Optional[Turma]:
    codigo = (codigo or "").strip()
    if not codigo:
        return None
    return Turma.query.filter_by(codigo=codigo).first()


def usuario_tem_turma(usuario_id: int, turma_id: int, papel: str | None = None) -> bool:
    q = Matricula.query.filter_by(usuario_id=usuario_id, turma_id=turma_id)
    if papel is not None:
        q = q.filter_by(papel=papel)
    return q.first() is not None


def matricular(usuario_id: int, turma_id: int, papel: str = "aluno") -> Matricula:
    """
    Cria matrícula se não existir; se já existir, retorna a existente.
    """
    existente = Matricula.query.filter_by(usuario_id=usuario_id, turma_id=turma_id).first()
    if existente:
        return existente

    m = Matricula(usuario_id=usuario_id, turma_id=turma_id, papel=papel)
    db.session.add(m)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existente = Matricula.query.filter_by(usuario_id=usuario_id, turma_id=turma_id).first()
        if existente:
            return existente
        raise
    return m


def turmas_do_usuario(usuario_id: int, papel: Optional[str] = None) -> list[Turma]:
    q = Turma.query.join(Matricula, Matricula.turma_id == Turma.id).filter(
        Matricula.usuario_id == usuario_id
    )
    if papel:
        q = q.filter(Matricula.papel == papel)
    return q.order_by(Turma.nome.asc()).all()


# =========================
# Conteúdos (Disciplina/Topico/Desafio/Pergunta)
# =========================

def disciplinas_da_turma(turma_id: int) -> list[Disciplina]:
    turma = Turma.query.get(turma_id)
    return list(getattr(turma, "disciplinas", []) or []) if turma else []


def topicos_da_disciplina(disciplina_id: int) -> list[Topico]:
    return Topico.query.filter_by(disciplina_id=disciplina_id).order_by(Topico.nome.asc()).all()


def desafios_do_topico(topico_id: int) -> list[Desafio]:
    return Desafio.query.filter_by(topico_id=topico_id).order_by(Desafio.criado_em.desc()).all()


def obter_desafio(desafio_id: int) -> Optional[Desafio]:
    return Desafio.query.get(desafio_id)


def obter_pergunta(pergunta_id: int) -> Optional[Pergunta]:
    return Pergunta.query.get(pergunta_id)


# =========================
# Query base (robusta) de desafios disponíveis por turma
# =========================

def _query_desafios_disponiveis_na_turma(turma_id: int):
    """
    Monta um query de Desafio:
      - vinculado à turma (quando existir vínculo no seu schema)
      - com pelo menos 1 Pergunta
    """
    q = (
        db.session.query(Desafio)
        .join(Topico, Desafio.topico_id == Topico.id)
        .filter(
            db.session.query(Pergunta.id)
            .filter(Pergunta.desafio_id == Desafio.id)
            .exists()
        )
    )

    # Se o seu schema tiver Topico.turma_id
    if hasattr(Topico, "turma_id"):
        q = q.filter(getattr(Topico, "turma_id") == turma_id)
        return q

    # Se o seu schema tiver Disciplina.turma_id
    if hasattr(Disciplina, "turma_id"):
        q = q.join(Disciplina, Topico.disciplina_id == Disciplina.id).filter(
            getattr(Disciplina, "turma_id") == turma_id
        )
        return q

    # Se existir relação Turma.disciplinas (m2m ou 1-n via relationship)
    turma = Turma.query.get(turma_id)
    disciplinas = list(getattr(turma, "disciplinas", []) or []) if turma else []
    disciplinas_ids = [d.id for d in disciplinas]
    if disciplinas_ids:
        q = q.filter(Topico.disciplina_id.in_(disciplinas_ids))
        return q

    return q


def contar_desafios_disponiveis_na_turma(turma_id: int) -> int:
    return int(_query_desafios_disponiveis_na_turma(turma_id).count())


def contar_desafios_concluidos_usuario(usuario_id: int, turma_id: int) -> int:
    return int(
        db.session.query(TentativaDesafio.desafio_id)
        .filter(
            TentativaDesafio.usuario_id == usuario_id,
            TentativaDesafio.turma_id == turma_id,
            TentativaDesafio.finalizada.is_(True),
        )
        .distinct()
        .count()
    )


# =========================
# Seleção e execução de desafios (ALUNO)
# =========================

def selecionar_proximo_desafio(usuario_id: int, turma_id: int) -> Optional[Desafio]:
    """
    Próximo desafio disponível:
      - não repetir desafios já finalizados (TentativaDesafio.finalizada=True)
      - ignora desafios sem perguntas
    """
    # desafios já concluídos
    concluidos = [
        row[0]
        for row in (
            db.session.query(TentativaDesafio.desafio_id)
            .filter(
                TentativaDesafio.usuario_id == usuario_id,
                TentativaDesafio.turma_id == turma_id,
                TentativaDesafio.finalizada.is_(True),
            )
            .distinct()
            .all()
        )
    ]

    q = _query_desafios_disponiveis_na_turma(turma_id)

    if concluidos:
        q = q.filter(~Desafio.id.in_(concluidos))

    return q.order_by(Desafio.id.asc()).first()


def iniciar_tentativa(usuario_id: int, turma_id: int, desafio: Desafio) -> TentativaDesafio:
    """
    Evita criar várias tentativas “abertas” do mesmo desafio (ex.: refresh).
    """
    existente = TentativaDesafio.query.filter_by(
        usuario_id=usuario_id,
        turma_id=turma_id,
        desafio_id=desafio.id,
        finalizada=False,
    ).first()
    if existente:
        return existente

    t = TentativaDesafio(
        usuario_id=usuario_id,
        turma_id=turma_id,
        desafio_id=desafio.id,
        topico_id=desafio.topico_id,
        finalizada=False,
    )
    db.session.add(t)
    db.session.commit()
    return t


def registrar_interacao(tentativa_id: int, pergunta_id: int, alternativa: str) -> Interacao:
    tentativa = db.session.get(TentativaDesafio, int(tentativa_id))
    if not tentativa:
        raise ValueError("Tentativa não encontrada")

    p = db.session.get(Pergunta, int(pergunta_id))
    if not p:
        raise ValueError("Pergunta não encontrada")

    alternativa = (alternativa or "").strip().lower()
    if alternativa not in {"a", "b", "c", "d"}:
        raise ValueError("Alternativa inválida")

    correta = (p.correta or "").strip().lower()
    foi_correta = alternativa == correta

    existente = Interacao.query.filter_by(tentativa_id=tentativa.id, pergunta_id=p.id).first()
    if existente:
        existente.alternativa = alternativa
        existente.foi_correta = foi_correta
        db.session.commit()
        return existente

    inter = Interacao(
        tentativa_id=tentativa.id,
        pergunta_id=p.id,
        topico_id=tentativa.topico_id,
        alternativa=alternativa,
        foi_correta=foi_correta,
    )
    db.session.add(inter)
    db.session.commit()
    return inter


def registrar_resposta(
    tentativa_id: int,
    pergunta_id: int,
    alternativa: str,
    usuario_id: int | None = None,
) -> dict[str, Any]:
    """
    Retorna dict (compatível com seu rotas.py / tutor.js):
       foi_correta
       resposta_correta
    """
    p = db.session.get(Pergunta, int(pergunta_id))
    if not p:
        raise ValueError("Pergunta não encontrada")

    inter = registrar_interacao(
        tentativa_id=tentativa_id,
        pergunta_id=pergunta_id,
        alternativa=alternativa,
    )

    return {
        "foi_correta": bool(inter.foi_correta),
        "resposta_correta": (p.correta or "a").strip().lower(),
    }


def finalizar_tentativa(tentativa_id: int, limiar_domino: float = 0.8) -> TentativaDesafio:
    tentativa = db.session.get(TentativaDesafio, int(tentativa_id))
    if not tentativa:
        raise ValueError("Tentativa não encontrada")

    total = Interacao.query.filter_by(tentativa_id=tentativa.id).count()
    corretas = Interacao.query.filter_by(tentativa_id=tentativa.id, foi_correta=True).count()

    taxa = (corretas / total) if total else 0.0
    tentativa.taxa_acerto_final = float(taxa)
    tentativa.dominou = bool(taxa >= limiar_domino)
    tentativa.finalizada = True

    db.session.commit()
    return tentativa


# =========================
# (Opcional) Análises simples
# =========================

def taxa_erro_por_topico(turma_id: int) -> list[dict[str, Any]]:
    rows = (
        db.session.query(
            Interacao.topico_id.label("topico_id"),
            func.count(Interacao.id).label("total"),
            func.sum(case((Interacao.foi_correta.is_(False), 1), else_=0)).label("erros"),
        )
        .join(TentativaDesafio, TentativaDesafio.id == Interacao.tentativa_id)
        .filter(TentativaDesafio.turma_id == turma_id)
        .group_by(Interacao.topico_id)
        .all()
    )

    topicos = {t.id: t.nome for t in Topico.query.all()}
    out: list[dict[str, Any]] = []
    for r in rows:
        total = int(r.total or 0)
        erros = int(r.erros or 0)
        taxa = (erros / total) if total else 0.0
        out.append(
            {
                "topico_id": int(r.topico_id),
                "topico_nome": topicos.get(int(r.topico_id), f"Topico {r.topico_id}"),
                "total": total,
                "erros": erros,
                "taxa_erro": float(taxa),
            }
        )
    return out


def kmeans_grupos_por_turma(
    turma_id: int,
    k: int = 3,
    min_interacoes_por_aluno: int = 3,
) -> dict[str, Any]:
    from sklearn.cluster import KMeans
    import numpy as np

    # tópicos que aparecem nessa turma via interações (mais consistente)
    topicos = (
        db.session.query(Topico)
        .join(Interacao, Interacao.topico_id == Topico.id)
        .join(TentativaDesafio, TentativaDesafio.id == Interacao.tentativa_id)
        .filter(TentativaDesafio.turma_id == turma_id)
        .order_by(Topico.nome.asc())
        .all()
    )
    if not topicos:
        return {
            "grupos_por_aluno": {},
            "medias_por_grupo_topico": {},
            "contagem_por_grupo": {},
            "topicos": [],
            "alunos_ids_usados": [],
        }

    topico_ids = [t.id for t in topicos]
    idx_topico = {tid: i for i, tid in enumerate(topico_ids)}

    alunos_ids = [
        r[0]
        for r in (
            db.session.query(Matricula.usuario_id)
            .filter(Matricula.turma_id == turma_id, Matricula.papel == "aluno")
            .distinct()
            .all()
        )
    ]
    if not alunos_ids:
        return {
            "grupos_por_aluno": {},
            "medias_por_grupo_topico": {},
            "contagem_por_grupo": {},
            "topicos": topicos,
            "alunos_ids_usados": [],
        }

    erros_expr = func.sum(case((Interacao.foi_correta.is_(False), 1), else_=0))

    rows = (
        db.session.query(
            TentativaDesafio.usuario_id.label("usuario_id"),
            Interacao.topico_id.label("topico_id"),
            func.count(Interacao.id).label("total"),
            erros_expr.label("erros"),
        )
        .join(TentativaDesafio, TentativaDesafio.id == Interacao.tentativa_id)
        .filter(TentativaDesafio.turma_id == turma_id)
        .group_by(TentativaDesafio.usuario_id, Interacao.topico_id)
        .all()
    )

    tot_por_aluno = {}
    for r in rows:
        tot_por_aluno[r.usuario_id] = tot_por_aluno.get(r.usuario_id, 0) + int(r.total or 0)

    alunos_usados = [uid for uid in alunos_ids if tot_por_aluno.get(uid, 0) >= min_interacoes_por_aluno]
    if len(alunos_usados) < 2:
        return {
            "grupos_por_aluno": {uid: 0 for uid in alunos_usados},
            "medias_por_grupo_topico": {},
            "contagem_por_grupo": {0: len(alunos_usados)},
            "topicos": topicos,
            "alunos_ids_usados": alunos_usados,
        }

    X = np.full((len(alunos_usados), len(topico_ids)), np.nan, dtype=float)
    pos_aluno = {uid: i for i, uid in enumerate(alunos_usados)}

    for r in rows:
        uid = int(r.usuario_id)
        tid = int(r.topico_id)
        if uid not in pos_aluno or tid not in idx_topico:
            continue
        total = int(r.total or 0)
        erros = int(r.erros or 0)
        X[pos_aluno[uid], idx_topico[tid]] = (erros / total) if total else np.nan

    col_means = np.nanmean(X, axis=0)
    col_means = np.where(np.isnan(col_means), 0.0, col_means)
    inds = np.where(np.isnan(X))
    X[inds] = np.take(col_means, inds[1])

    k_eff = max(2, min(int(k), len(alunos_usados)))
    km = KMeans(n_clusters=k_eff, n_init="auto", random_state=42)
    labels = km.fit_predict(X)

    grupos_por_aluno = {uid: int(labels[pos_aluno[uid]]) for uid in alunos_usados}

    medias_por_grupo_topico: dict[int, dict[int, float]] = {}
    contagem_por_grupo: dict[int, int] = {}

    for g in range(k_eff):
        idxs = np.where(labels == g)[0]
        contagem_por_grupo[g] = int(len(idxs))
        if len(idxs) == 0:
            continue
        medias = X[idxs].mean(axis=0)
        medias_por_grupo_topico.update({
            topico_ids[j]: {**medias_por_grupo_topico.get(topico_ids[j], {}), g: float(medias[j])}
            for j in range(len(topico_ids))
        })

    return {
        "grupos_por_aluno": grupos_por_aluno,
        "medias_por_grupo_topico": medias_por_grupo_topico,
        "contagem_por_grupo": contagem_por_grupo,
        "topicos": topicos,
        "alunos_ids_usados": alunos_usados,
        "k_eff": k_eff,
    }
