const chat = document.getElementById("chat");
const turmaSelect = document.getElementById("turmaSelect");

let estado = {
  turma_id: null,
  tentativa_id: null,
  perguntas: [],
  idx: 0,
  acertos: 0,
  desafio: null
};

function addBot(html) {
  const wrap = document.createElement("div");
  wrap.className = "msg";
  wrap.innerHTML = `
    <div class="avatar">S</div>
    <div class="bubble">${html}</div>
  `;
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  return wrap;
}

function looksLikeLatex(s) {
  if (!s) return false;
  const t = String(s).trim();
  return t.includes("\\") || t.includes("^") || t.includes("_") || t.includes("\\frac") || t.includes("\\sqrt");
}

function renderMaybeLatex(s) {
  if (!s) return "";
  const t = String(s).trim().replace(/^\$/g, "").replace(/\$$/g, "");
  if (looksLikeLatex(t)) return `\\(${t}\\)`;
  return t.replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function renderEnunciadoDesafio(d) {
  if (!d) return "";
  if (d.tipo_enunciado === "imagem" && d.enunciado_imagem_url) {
    return `<div class="box-enunciado"><img src="${d.enunciado_imagem_url}" style="max-width:100%;border-radius:12px;"></div>`;
  }
  if (d.tipo_enunciado === "latex" && d.enunciado_latex) {
    return `<div class="box-enunciado">\\(${d.enunciado_latex}\\)</div>`;
  }
  return `<div class="box-enunciado">${(d.enunciado_texto || "").replace(/</g,"&lt;").replace(/>/g,"&gt;")}</div>`;
}

async function carregarTurmas() {
  const r = await fetch("/api/turmas?papel=aluno");
  const data = await r.json();

  turmaSelect.innerHTML = "";
  if (!data.turmas || data.turmas.length === 0) {
    turmaSelect.innerHTML = `<option value="">Sem turmas</option>`;
    turmaSelect.disabled = true;
    addBot("Você não tem turma. Peça ao professor.");
    return;
  }

  data.turmas.forEach(t => {
    const opt = document.createElement("option");
    opt.value = t.id;
    opt.textContent = `${t.nome} (${t.codigo})`;
    turmaSelect.appendChild(opt);
  });

  const saved = localStorage.getItem("turma_id");
  const first = saved && data.turmas.some(t => String(t.id) === String(saved)) ? saved : data.turmas[0].id;

  estado.turma_id = Number(first);
  turmaSelect.value = String(first);

  await proximo();
}

async function proximo() {
  chat.innerHTML = "";
  addBot("Buscando desafio...");

  const r = await fetch("/api/treino/proximo", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ turma_id: estado.turma_id })
  });

  if (!r.ok) {
    const e = await r.json();
    chat.innerHTML = "";
    addBot(`<strong>${e.error || "Erro"}</strong>`);
    return;
  }

  const data = await r.json();
  estado.tentativa_id = data.tentativa_id;
  estado.perguntas = data.perguntas || [];
  estado.idx = 0;
  estado.acertos = 0;
  estado.desafio = data.desafio;

  chat.innerHTML = "";

  addBot(`
    <div class="small-muted"><strong>Habilidade:</strong> ${data.desafio.habilidade}</div>
    <div class="fw-bold">${data.desafio.titulo}</div>
    ${renderEnunciadoDesafio(data.desafio)}
  `);

  MathJax.typesetPromise().catch(()=>{});
  mostrarPergunta();
}

function mostrarPergunta() {
  if (estado.idx >= estado.perguntas.length) {
    const total = estado.perguntas.length;
    const pct = total ? Math.round((estado.acertos / total) * 100) : 0;
    const ok = pct >= 70;

    addBot(`
      <div class="fw-bold">Fim do desafio</div>
      <div>Acertos: <strong>${estado.acertos}</strong> / <strong>${total}</strong> (${pct}%)</div>
      <div class="mt-2"><strong>${ok ? "Dominou ✅" : "Precisa reforçar."}</strong></div>
      <button id="btnNext" class="btn btn-primary btn-sm mt-3">Próximo</button>
    `);

    document.getElementById("btnNext").onclick = proximo;
    return;
  }

  const p = estado.perguntas[estado.idx];
  const html = `
    <div class="small-muted">Passo ${estado.idx + 1} de ${estado.perguntas.length}</div>
    <div class="mt-1">${renderMaybeLatex(p.enunciado)}</div>
    <div class="mt-3 d-grid gap-2">
      ${["a","b","c","d"].map(k => p.alternativas[k] ? `<button class="alt" data-k="${k}"><strong>${k.toUpperCase()}.</strong> ${renderMaybeLatex(p.alternativas[k])}</button>` : "").join("")}
    </div>
    <div id="fb" class="mt-2 fw-bold"></div>
  `;

  const node = addBot(html);
  node.querySelectorAll(".alt").forEach(btn => btn.onclick = () => responder(p.id, btn.dataset.k, node));
  MathJax.typesetPromise().catch(()=>{});
}

async function responder(pergunta_id, alternativa, node) {
  node.querySelectorAll(".alt").forEach(b => b.disabled = true);

  const r = await fetch("/api/treino/responder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tentativa_id: estado.tentativa_id, pergunta_id, alternativa })
  });

  const data = await r.json();
  if (!r.ok) {
    addBot(`<strong>${data.error || "Erro"}</strong>`);
    return;
  }

  const fb = node.querySelector("#fb");
  if (data.foi_correta) {
    estado.acertos += 1;
    fb.textContent = "Correto!";
    fb.style.color = "#2f8f4e";
    node.querySelector(`.alt[data-k="${alternativa}"]`)?.classList.add("ok");
  } else {
    fb.textContent = `Incorreto. Correta: ${data.resposta_correta.toUpperCase()}`;
    fb.style.color = "#c0392b";
    node.querySelector(`.alt[data-k="${alternativa}"]`)?.classList.add("bad");
    node.querySelector(`.alt[data-k="${data.resposta_correta}"]`)?.classList.add("ok");
  }

  estado.idx += 1;
  setTimeout(mostrarPergunta, 900);
}

turmaSelect.addEventListener("change", async () => {
  estado.turma_id = Number(turmaSelect.value);
  localStorage.setItem("turma_id", String(estado.turma_id));
  await proximo();
});

window.addEventListener("load", carregarTurmas);
