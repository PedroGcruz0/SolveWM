const chatBox = document.getElementById('chat-box');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const imageInput = document.getElementById('image-input');

function scrollToBottom() {
  setTimeout(() => { chatBox.scrollTop = chatBox.scrollHeight; }, 100);
}

function appendMessage(htmlContent, sender) {
  const messageDiv = document.createElement('div');
  messageDiv.classList.add('message', `${sender}-message`);

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.innerHTML = htmlContent;

  if (sender === 'bot') {
    const avatar = document.createElement('img');
    avatar.src = '/static/img_logo.png';
    avatar.alt = 'Bot';
    avatar.className = 'bot-avatar';
    messageDiv.appendChild(avatar);
  }

  messageDiv.appendChild(bubble);
  chatBox.appendChild(messageDiv);
  scrollToBottom();
  return messageDiv;
}

async function handleApiResponse(response, thinkingMessage) {
  if (response.redirected) { window.location.href = response.url; return null; }

  const contentType = response.headers.get("content-type");
  if (!contentType || !contentType.includes("application/json")) {
    if (thinkingMessage) thinkingMessage.querySelector('.bubble').innerHTML = `<strong>Erro:</strong> Resposta inválida do servidor.`;
    throw new TypeError("Resposta não é JSON.");
  }

  const data = await response.json();
  if (!response.ok) throw new Error(data.tipo || data.raw_latex || 'Erro desconhecido.');
  return data;
}

async function handleTextMessage() {
  const text = userInput.value.trim();
  if (!text) return;

  appendMessage(text, 'user');
  userInput.value = '';

  const thinking = appendMessage('Calculando...', 'bot');
  try {
    const resp = await fetch('/calcular_texto', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expressao: text })
    });
    const json = await handleApiResponse(resp, thinking);
    if (!json) return;

    thinking.remove();
    renderFinalResponse(json);
  } catch (e) {
    thinking.querySelector('.bubble').innerHTML = `<strong>Erro:</strong> ${e.message}`;
  }
}

async function handleImageUpload() {
  const file = imageInput.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = (e) => appendMessage(`<img src="${e.target.result}" style="max-width:100%;max-height:240px;border-radius:12px;">`, 'user');
  reader.readAsDataURL(file);

  const thinking = appendMessage('Analisando imagem...', 'bot');

  const formData = new FormData();
  formData.append('file', file);

  try {
    const r1 = await fetch('/process_image', { method: 'POST', body: formData });
    const d1 = await handleApiResponse(r1, thinking);
    if (!d1) return;

    const r2 = await fetch('/calcular_latex', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ funcao: d1.raw_latex })
    });
    const d2 = await handleApiResponse(r2, thinking);
    if (!d2) return;

    thinking.remove();
    renderFinalResponse(d2);
  } catch (e) {
    thinking.querySelector('.bubble').innerHTML = `<strong>Erro:</strong> ${e.message}`;
  } finally {
    imageInput.value = '';
  }
}

function renderFinalResponse(data) {
  let html = `<p>${data.tipo}</p>`;
  if (data.metodos && data.metodos.length) {
    html += '<h6>Métodos sugeridos:</h6><ul>' + data.metodos.map(m => `<li>${m}</li>`).join('') + '</ul>';
  }
  appendMessage(html, 'bot');
}

sendBtn.addEventListener('click', handleTextMessage);
userInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); handleTextMessage(); } });
imageInput.addEventListener('change', handleImageUpload);

new MutationObserver(scrollToBottom).observe(chatBox, { childList: true });
