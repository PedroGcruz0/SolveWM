from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from .modelos import db, Usuario, Turma, Pergunta, TentativaDesafio, Interacao, Desafio, Topico, Disciplina, turmas_disciplinas
from .formularios import FormEntrar, FormCadastro
from .servicos import (
    buscar_turma_por_codigo,
    matricular,
    turmas_do_usuario,
    usuario_tem_turma,
    selecionar_proximo_desafio,
    iniciar_tentativa,
    registrar_resposta,
    finalizar_tentativa
)
from sqlalchemy import exists, select
site_bp = Blueprint("site", __name__)

def _desafio_to_dict(desafio: Desafio):
    disciplina = desafio.topico.disciplina.nome if desafio.topico and desafio.topico.disciplina else ""
    topico = desafio.topico.nome if desafio.topico else ""

    img_url = None
    if desafio.enunciado_imagem:
        nome = desafio.enunciado_imagem.strip()
        prefix = "uploads/enunciados/"
        if nome.startswith(prefix):
            nome = nome[len(prefix):]
        img_url = url_for("static", filename=f"uploads/enunciados/{nome}", _external=False)

    return {
        "id": desafio.id,
        "titulo": desafio.titulo,
        "disciplina": disciplina,
        "topico": topico,
        "enunciado_texto": desafio.enunciado_texto or "",
        "enunciado_latex": desafio.enunciado_latex or "",
        "enunciado_imagem_url": img_url,
    }


def _pergunta_to_dict(p: Pergunta):
    alts = {"a": p.alt_a, "b": p.alt_b}
    if p.alt_c:
        alts["c"] = p.alt_c
    if p.alt_d:
        alts["d"] = p.alt_d

    return {
        "id": p.id,
        "enunciado": p.enunciado,
        "alternativas": alts,
        "ordem": p.ordem,
    }

def _payload_tentativa(t: TentativaDesafio):
    desafio = t.desafio
    perguntas = list(desafio.perguntas)
    perguntas.sort(key=lambda p: (p.ordem or 0, p.id))

    interacoes = (
        Interacao.query
        .filter_by(tentativa_id=t.id)
        .order_by(Interacao.id.asc())
        .all()
    )

    historico = [
        {
            "pergunta_id": i.pergunta_id,
            "alternativa": (i.alternativa or "").lower(),
            "foi_correta": bool(i.foi_correta),
            "correta": (i.pergunta.correta or "").lower() if i.pergunta else None,
        }
        for i in interacoes
    ]

    return {
        "done": False,
        "tentativa_id": t.id,
        "desafio": _desafio_to_dict(desafio),
        "perguntas": [_pergunta_to_dict(p) for p in perguntas],
        "historico": historico,
    }




@site_bp.route("/")
def index():
    return render_template("inicio.html")


@site_bp.route("/entrar", methods=["GET", "POST"])
def entrar():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect("/admin")
        return redirect(url_for("site.area_aluno"))

    form = FormEntrar()
    if form.validate_on_submit():
        u = Usuario.query.filter_by(email=form.email.data.strip().lower()).first()
        if not u or not check_password_hash(u.senha_hash, form.senha.data):
            flash("Email ou senha inválidos.", "warning")
            return redirect(url_for("site.entrar"))

        login_user(u, remember=form.lembrar.data)

        if u.is_admin:
            return redirect("/admin")
        return redirect(url_for("site.area_aluno"))

    return render_template("entrar.html", form=form)


@site_bp.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if current_user.is_authenticated:
        return redirect(url_for("site.area_aluno"))

    form = FormCadastro()
    if form.validate_on_submit():
        turma = buscar_turma_por_codigo(form.codigo_turma.data)
        if not turma:
            flash("Código de turma inválido.", "danger")
            return redirect(url_for("site.cadastro"))

        u = Usuario(
            nome=form.nome.data.strip(),
            email=form.email.data.strip().lower(),
            senha_hash=generate_password_hash(form.senha.data),
            is_admin=False,
        )
        db.session.add(u)
        db.session.commit()

        matricular(u.id, turma.id, papel="aluno")

        flash("Cadastro concluído! Faça login.", "success")
        return redirect(url_for("site.entrar"))

    return render_template("cadastro.html", form=form)


@site_bp.route("/sair")
@login_required
def sair():
    logout_user()
    session.pop("turma_ativa_id", None)
    session.pop("turma_id", None)  # compatibilidade (caso exista no seu projeto)
    return redirect(url_for("site.index"))


@site_bp.route("/aluno")
@login_required
def area_aluno():
    if current_user.is_admin:
        return redirect("/admin")

    turmas = turmas_do_usuario(current_user.id, papel="aluno")
    return render_template("aluno.html", turmas=turmas)


@site_bp.route("/selecionar-turma/<int:turma_id>")
@login_required
def selecionar_turma(turma_id: int):
    if not usuario_tem_turma(current_user.id, turma_id, papel="aluno"):
        flash("Você não está matriculado nesta turma.", "warning")
        return redirect(url_for("site.area_aluno"))

    session["turma_ativa_id"] = turma_id
    # (mantém também a chave antiga, se em algum lugar você ainda usa)
    session["turma_id"] = turma_id
    return redirect(url_for("site.tutor"))


@site_bp.route("/tutor")
@login_required
def tutor():
    if current_user.is_admin:
        return redirect("/admin")

    turma_id = session.get("turma_ativa_id")
    if not turma_id:
        return redirect(url_for("site.area_aluno"))

    turma = db.session.get(Turma, turma_id)
    return render_template("tutor.html", turma=turma)

@site_bp.route("/api/tutor/proximo", methods=["POST"])
@login_required
def api_proximo():
    data = request.get_json(silent=True) or {}
    turma_id = data.get("turma_id") or session.get("turma_ativa_id")

    if not turma_id:
        return jsonify({"error": "turma_id é obrigatório"}), 400

    # garante que o aluno está na turma
    if not usuario_tem_turma(current_user.id, int(turma_id), papel="aluno"):
        return jsonify({"error": "Usuário não matriculado nesta turma."}), 403

    turma_id = int(turma_id)
    aluno_id = current_user.id

    # 1) tenta continuar tentativa em andamento
    tentativa = (
        TentativaDesafio.query
        .filter_by(turma_id=turma_id, usuario_id=aluno_id, finalizada=False)
        .order_by(TentativaDesafio.id.desc())
        .first()
    )

    # 2) se não tem tentativa, escolhe próximo desafio não concluído que TENHA perguntas
    if not tentativa:
        # subquery desafios concluídos
        concluidos_q = (
            db.session.query(TentativaDesafio.desafio_id)
            .filter_by(turma_id=turma_id, usuario_id=aluno_id, finalizada=True)
        )

        # desafios dessa turma (via disciplina/topico) + que tenham perguntas
        desafio = (
            db.session.query(Desafio)
            .join(Topico, Desafio.topico_id == Topico.id)
            .join(Disciplina, Topico.disciplina_id == Disciplina.id)
            .join(turmas_disciplinas, turmas_disciplinas.c.disciplina_id == Disciplina.id)
            .filter(turmas_disciplinas.c.turma_id == turma_id)
            .filter(~Desafio.id.in_(concluidos_q))
            .filter(exists().where(Pergunta.desafio_id == Desafio.id))
            .order_by(Topico.id.asc(), Desafio.criado_em.asc(), Desafio.id.asc())
            .first()
        )

        if not desafio:
            return jsonify({"done": True, "message": "Você concluiu todos os desafios desta turma."}), 200

        tentativa = TentativaDesafio(
            usuario_id=aluno_id,
            turma_id=turma_id,
            desafio_id=desafio.id,
            topico_id=desafio.topico_id,
            finalizada=False,
        )
        db.session.add(tentativa)
        db.session.commit()

    return jsonify(_montar_payload(tentativa)), 200


def _montar_payload(tentativa: TentativaDesafio):
    desafio = tentativa.desafio

    # garante: se por algum motivo não tiver perguntas, finaliza e pede novo
    total = Pergunta.query.filter_by(desafio_id=desafio.id).count()
    if total == 0:
        tentativa.finalizada = True
        db.session.commit()
        return {
            "fim_do_desafio": True,
            "message": "Este desafio não possui perguntas cadastradas e foi ignorado.",
        }

    # respondidas
    respondidas = {i.pergunta_id for i in tentativa.interacoes}

    # próxima pergunta
    prox = (
        Pergunta.query
        .filter_by(desafio_id=desafio.id)
        .order_by(Pergunta.ordem.asc(), Pergunta.id.asc())
        .all()
    )
    restantes = [p for p in prox if p.id not in respondidas]

    if not restantes:
        tentativa.finalizada = True
        db.session.commit()
        return {
            "fim_do_desafio": True,
            "message": "Você terminou este desafio. Clique em “Próximo desafio” para continuar.",
            "tentativa_id": tentativa.id,
            "desafio": _desafio_to_dict(desafio),
        }

    pergunta = restantes[0]
    indice = len(respondidas) + 1

    return {
        "fim_do_desafio": False,
        "tentativa_id": tentativa.id,
        "desafio": _desafio_to_dict(desafio),
        "pergunta": _pergunta_to_dict(pergunta),
        "total_perguntas": total,
        "indice_pergunta": indice,
    }

@site_bp.route("/api/tutor/responder", methods=["POST"])
@login_required
def api_responder():
    data = request.get_json(silent=True) or {}
    tentativa_id = data.get("tentativa_id")
    pergunta_id = data.get("pergunta_id")
    alternativa = (data.get("alternativa") or "").lower().strip()

    if not tentativa_id or not pergunta_id or alternativa not in ("a","b","c","d"):
        return jsonify({"error": "Campos obrigatórios: tentativa_id, pergunta_id, alternativa (a|b|c|d)"}), 400

    tentativa = db.session.get(TentativaDesafio, int(tentativa_id))
    if not tentativa or tentativa.usuario_id != current_user.id:
        return jsonify({"error": "Tentativa inválida."}), 400

    pergunta = db.session.get(Pergunta, int(pergunta_id))
    if not pergunta or pergunta.desafio_id != tentativa.desafio_id:
        return jsonify({"error": "Pergunta inválida para este desafio."}), 400

    # já respondeu?
    ja = Interacao.query.filter_by(tentativa_id=tentativa.id, pergunta_id=pergunta.id).first()
    if ja:
        return jsonify({"error": "Pergunta já respondida."}), 400

    foi_correta = (alternativa == (pergunta.correta or "").lower().strip())
    inter = Interacao(
        tentativa_id=tentativa.id,
        pergunta_id=pergunta.id,
        topico_id=tentativa.topico_id,
        alternativa=alternativa,
        foi_correta=bool(foi_correta),
    )
    db.session.add(inter)
    db.session.commit()

    total = Pergunta.query.filter_by(desafio_id=tentativa.desafio_id).count()
    respondidas = Interacao.query.filter_by(tentativa_id=tentativa.id).count()
    tentativa_concluida = (respondidas >= total)

    if tentativa_concluida:
        tentativa.finalizada = True
        db.session.commit()

    return jsonify({
        "foi_correta": bool(foi_correta),
        "resposta_correta": (pergunta.correta or "").lower(),
        "tentativa_concluida": bool(tentativa_concluida),
    }), 200



@site_bp.route("/api/tutor/finalizar", methods=["POST"])
@login_required
def api_finalizar():
    payload = request.get_json(silent=True) or {}
    tentativa_id = payload.get("tentativa_id")
    if not tentativa_id:
        return jsonify(error="Payload inválido."), 400

    tentativa = db.session.get(TentativaDesafio, int(tentativa_id))
    if not tentativa or tentativa.usuario_id != current_user.id:
        return jsonify(error="Tentativa inválida."), 400

    t = finalizar_tentativa(int(tentativa_id), limiar_domino=0.8)
    return jsonify(
        finalizada=True,
        dominou=bool(t.dominou),
        taxa=float(t.taxa_acerto_final or 0.0)
    ), 200