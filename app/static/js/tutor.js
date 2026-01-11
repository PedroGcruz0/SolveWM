(() => {
  const state = {
    tentativaId: null,
    turmaId: null,
    desafio: null,
    pergunta: null,
    total: 0,
    indice: 0,
    busy: false,
    esperandoProximoDesafio: false,
  };

  const els = {
    wrap: document.querySelector(".tutor-wrap"),
    status: document.getElementById("tutorStatus"),

    desafioBox: document.getElementById("desafioBox"),
    desafioMeta: document.getElementById("desafioMeta"),
    desafioTitulo: document.getElementById("desafioTitulo"),
    desafioTexto: document.getElementById("desafioTexto"),
    desafioImagemWrap: document.getElementById("desafioImagemWrap"),
    desafioImagem: document.getElementById("desafioImagem"),

    quizBox: document.getElementById("quizBox"),
    quizProgress: document.getElementById("quizProgress"),
    perguntaEnunciado: document.getElementById("perguntaEnunciado"),
    alternativas: document.getElementById("alternativas"),
    feedback: document.getElementById("feedback"),
    btnContinuar: document.getElementById("btnContinuar"),

    fimBox: document.getElementById("fimBox"),
    fimMsg: document.getElementById("fimMsg"),
    btnProximoDesafio: document.getElementById("btnProximoDesafio"),
  };

  function setStatus(msg = "") {
    if (els.status) els.status.textContent = msg;
  }

  function show(el) { if (el) el.style.display = ""; }
  function hide(el) { if (el) el.style.display = "none"; }

  async function postJson(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(body || {}),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.error || `Erro HTTP ${res.status}`);
    return data;
  }

  function setText(el, str) {
    if (!el) return;
    el.textContent = (str ?? "").toString();
  }

  function setImagem(url) {
    if (!url) {
      hide(els.desafioImagemWrap);
      if (els.desafioImagem) els.desafioImagem.removeAttribute("src");
      return;
    }
    els.desafioImagem.src = url;
    show(els.desafioImagemWrap);
  }

  function typeset() {
    if (window.MathJax?.typesetPromise) {
      window.MathJax.typesetPromise();
    }
  }

  function resetTela() {
    hide(els.fimBox);
    hide(els.quizBox);
    hide(els.desafioBox);
    hide(els.feedback);
    hide(els.btnContinuar);
    els.alternativas.innerHTML = "";
  }

  function render(payload) {
    // fim global
    if (payload.done) {
      resetTela();
      show(els.fimBox);
      els.fimMsg.className = "alert alert-success mb-3";
      setText(els.fimMsg, payload.message || "Você concluiu todos os desafios desta turma.");
      els.btnProximoDesafio.style.display = "none";
      return;
    }

    // fim do desafio atual
    if (payload.fim_do_desafio) {
      state.esperandoProximoDesafio = true;
      hide(els.quizBox);

      show(els.desafioBox);
      // mantém dados do desafio exibidos

      show(els.fimBox);
      els.fimMsg.className = "alert alert-success mb-3";
      setText(els.fimMsg, payload.message || "Você terminou este desafio.");
      els.btnProximoDesafio.style.display = "";
      return;
    }

    // pergunta normal
    state.esperandoProximoDesafio = false;

    state.tentativaId = payload.tentativa_id;
    state.desafio = payload.desafio || {};
    state.pergunta = payload.pergunta || {};
    state.total = payload.total_perguntas || 0;
    state.indice = payload.indice_pergunta || 1;

    // desafio header
    show(els.desafioBox);

    const disciplina = state.desafio.disciplina || "";
    const topico = state.desafio.topico || "";
    setText(
      els.desafioMeta,
      [disciplina && `Disciplina: ${disciplina}`, topico && `Tópico: ${topico}`].filter(Boolean).join(" — ")
    );

    setText(els.desafioTitulo, state.desafio.titulo || "");
    setImagem(state.desafio.enunciado_imagem_url || null);

    const texto = (state.desafio.enunciado_texto || "").trim();
    const latex = (state.desafio.enunciado_latex || "").trim();
    setText(els.desafioTexto, texto || latex || "");

    // quiz
    show(els.quizBox);
    hide(els.fimBox);

    setText(els.quizProgress, `Pergunta ${state.indice} de ${state.total}`);
    setText(els.perguntaEnunciado, state.pergunta.enunciado || "");

    // alternativas (dict a/b/c/d)
    const alts = state.pergunta.alternativas || {};
    els.alternativas.innerHTML = Object.entries(alts).map(([k, v]) => {
      const letra = k.toUpperCase();
      return `
        <button type="button" class="quiz-alt-btn" data-alt="${k}" data-pergunta-id="${state.pergunta.id}">
          <span class="me-1">${letra}.</span> <span class="alt-text"></span>
        </button>
      `;
    }).join("");

    // preencher texto das alternativas via textContent (seguro + MathJax pega delimitadores)
    const btns = els.alternativas.querySelectorAll("button[data-alt]");
    [...btns].forEach((btn) => {
      const k = (btn.dataset.alt || "").toLowerCase();
      const span = btn.querySelector(".alt-text");
      if (span) span.textContent = (alts[k] ?? "").toString();
    });

    hide(els.feedback);
    hide(els.btnContinuar);

    typeset();
  }

  async function carregarProximo() {
    if (state.busy) return;
    try {
      state.busy = true;
      setStatus("Carregando...");

      const data = await postJson("/api/tutor/proximo", {
        turma_id: state.turmaId
      });

      setStatus("");
      render(data);
    } catch (e) {
      console.error(e);
      setStatus(e.message || "Erro ao carregar.");
    } finally {
      state.busy = false;
    }
  }

  async function responder(perguntaId, alt) {
    if (state.busy) return;
    try {
      state.busy = true;
      setStatus("Enviando resposta...");

      els.alternativas.querySelectorAll("button[data-alt]").forEach((b) => (b.disabled = true));

      const data = await postJson("/api/tutor/responder", {
        tentativa_id: state.tentativaId,
        pergunta_id: perguntaId,
        alternativa: alt,
      });

      setStatus("");

      // feedback
      const correta = (data.resposta_correta || "").toUpperCase();
      const foiCorreta = !!data.foi_correta;

      show(els.feedback);
      els.feedback.style.borderColor = foiCorreta ? "rgba(25,135,84,.35)" : "rgba(220,53,69,.35)";
      els.feedback.textContent = foiCorreta
        ? `✅ Correta!`
        : `❌ Incorreta. Resposta certa: ${correta}.`;

      show(els.btnContinuar);
      els.btnContinuar.textContent = data.tentativa_concluida ? "Finalizar desafio" : "Continuar";

      typeset();
    } catch (e) {
      console.error(e);
      setStatus(e.message || "Erro ao responder.");
      els.alternativas.querySelectorAll("button[data-alt]").forEach((b) => (b.disabled = false));
    } finally {
      state.busy = false;
    }
  }

  function bind() {
    els.alternativas.addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-alt][data-pergunta-id]");
      if (!btn) return;

      const perguntaId = parseInt(btn.dataset.perguntaId, 10);
      const alt = (btn.dataset.alt || "").toLowerCase();
      responder(perguntaId, alt);
    });

    els.btnContinuar.addEventListener("click", () => {
      // sempre puxa /proximo: se ainda tem perguntas, vem a próxima; se acabou, vem fim_do_desafio
      carregarProximo();
    });

    els.btnProximoDesafio.addEventListener("click", () => {
      resetTela();
      carregarProximo();
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    state.turmaId = els.wrap?.dataset?.turmaId ? parseInt(els.wrap.dataset.turmaId, 10) : null;
    bind();
    carregarProximo();
  });
})();
