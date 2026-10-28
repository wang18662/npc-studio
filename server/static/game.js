const canvas = document.getElementById('view');
const ctx = canvas.getContext('2d');

const GRID = 20;
const CELL = canvas.width / GRID;

const STATE_COLORS = {
  '巡逻': '#6b8cff',
  '站桩': '#5f6b85',
  '追击': '#f0a04b',
  '驻留': '#e8c25a',
  '空闲': '#8b909c',
  '对话': '#63c98a',
  '待战': '#8b909c',
  '攻击': '#f2607a',
  '后撤': '#b07cf0',
};

const LAYER_LABELS = {
  locomotion: '移动层',
  interaction: '交互层',
  combat: '战斗层',
};

let state = null;
let player = { x: 4, y: 4 };
let initialized = false;
const keys = new Set();

function toPixel(v) {
  return v * CELL + CELL / 2;
}

function drawGrid() {
  ctx.strokeStyle = '#23262e';
  ctx.lineWidth = 1;
  for (let i = 0; i <= GRID; i++) {
    const p = i * CELL + 0.5;
    ctx.beginPath();
    ctx.moveTo(p, 0);
    ctx.lineTo(p, canvas.height);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(0, p);
    ctx.lineTo(canvas.width, p);
    ctx.stroke();
  }
}

function drawCircle(x, y, r, fill, stroke) {
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  if (fill) {
    ctx.fillStyle = fill;
    ctx.fill();
  }
  if (stroke) {
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }
}

function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  drawGrid();

  if (!state) return;

  const npcX = toPixel(state.npc.x);
  const npcY = toPixel(state.npc.y);
  const plX = toPixel(player.x);
  const plY = toPixel(player.y);

  // 视野 8m
  ctx.beginPath();
  ctx.arc(npcX, npcY, 8 * CELL, 0, Math.PI * 2);
  ctx.strokeStyle = 'rgba(79, 156, 249, 0.20)';
  ctx.setLineDash([5, 5]);
  ctx.stroke();
  ctx.setLineDash([]);

  // 攻击范围 2m
  ctx.beginPath();
  ctx.arc(npcX, npcY, 2 * CELL, 0, Math.PI * 2);
  ctx.strokeStyle = 'rgba(242, 96, 122, 0.32)';
  ctx.stroke();

  // 连线
  ctx.beginPath();
  ctx.moveTo(npcX, npcY);
  ctx.lineTo(plX, plY);
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.10)';
  ctx.setLineDash([3, 4]);
  ctx.stroke();
  ctx.setLineDash([]);

  drawCircle(plX, plY, 10, '#f97362');
  drawCircle(npcX, npcY, 13, '#4f9cf9');

  // NPC 头顶三个状态色点
  ['locomotion', 'interaction', 'combat'].forEach((lid, i) => {
    const info = state.layers[lid];
    if (!info) return;
    drawCircle(npcX - 12 + i * 12, npcY - 26, 4, STATE_COLORS[info.state] || '#8b909c');
  });
}

function localDistance() {
  if (!state) return 0;
  return Math.hypot(player.x - state.npc.x, player.y - state.npc.y);
}

function renderPanel() {
  if (!state) return;

  const dist = localDistance();
  document.getElementById('time').textContent = `${state.time.toFixed(1)}s`;
  document.getElementById('dist').textContent = `${dist.toFixed(1)} m`;

  document.getElementById('layers').innerHTML = Object.entries(state.layers)
    .map(([lid, info]) => {
      const color = STATE_COLORS[info.state] || '#8b909c';
      return `<div class="layer">
        <span class="name">${LAYER_LABELS[lid] || lid}</span>
        <span class="state" style="background:${color}22;color:${color}">${info.state}</span>
      </div>`;
    })
    .join('');

  const lockEntries = Object.entries(state.locks);
  document.getElementById('locks').innerHTML = lockEntries.length
    ? lockEntries
        .map(([cap, owner]) => `<div class="lock"><span>${cap}</span><b>${owner}</b></div>`)
        .join('')
    : '<div class="lock"><span>无</span></div>';

  document.getElementById('events').innerHTML = state.events.length
    ? state.events.map((e) => `<span class="event">${e}</span>`).join('')
    : '<span style="color:#5f6675">—</span>';

  const history = state.history || [];
  document.getElementById('history').innerHTML = history.length
    ? history
        .map(
          (h) => `<div class="hist-item">
            <span class="t">${h.time.toFixed(1)}s</span>
            <span class="l">${h.layer.slice(0, 4)}</span>
            <span>${h.from} → ${h.to}</span>
          </div>`
        )
        .join('')
    : '<span style="color:#5f6675">—</span>';
}

async function poll() {
  try {
    const res = await fetch('/api/state');
    state = await res.json();
    if (!initialized && state.player) {
      player = { ...state.player };
      initialized = true;
    }
    renderPanel();
  } catch (err) {
    // 服务器未就绪时静默重试
  }
}

function sendMove() {
  fetch('/api/move', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ x: player.x, y: player.y }),
  }).catch(() => {});
}

document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT') return;

  const key = e.key.toLowerCase();
  keys.add(key);
  if (key === 'e') {
    const talking = state?.layers?.interaction?.state === '对话';
    fetch(talking ? '/api/end-dialogue' : '/api/interact', { method: 'POST' }).catch(() => {});
  }
  if (['arrowup', 'arrowdown', 'arrowleft', 'arrowright', ' '].includes(key)) {
    e.preventDefault();
  }
});

// ---------- 对话 ----------

const chatlog = document.getElementById('chatlog');
const msgInput = document.getElementById('msg');
const sendBtn = document.getElementById('send');

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function appendChat(who, text, cls) {
  const div = document.createElement('div');
  div.className = `chat-item ${cls}`;
  div.innerHTML = `<b>${who}</b><span>${escapeHtml(text)}</span>`;
  chatlog.appendChild(div);
  chatlog.scrollTop = chatlog.scrollHeight;
}

async function sendMessage() {
  const text = msgInput.value.trim();
  if (!text) return;
  msgInput.value = '';
  appendChat('你', text, 'me');

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });
    const data = await res.json();
    appendChat('守卫', data.reply, 'npc');

    if (data.tool) {
      const t = data.tool;
      appendChat(
        '系统',
        t.ok ? `工具执行成功：${t.tool}` : `工具被拒（${t.failedAt}）：${t.reason}`,
        'sys'
      );
    }
  } catch (err) {
    appendChat('系统', '请求失败，请确认服务器正在运行', 'sys');
  }
}

sendBtn.addEventListener('click', sendMessage);
msgInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') sendMessage();
});

document.addEventListener('keyup', (e) => keys.delete(e.key.toLowerCase()));

let lastMoveAt = 0;
function movementLoop(ts) {
  const speed = 0.12;
  let dx = 0;
  let dy = 0;

  if (keys.has('w') || keys.has('arrowup')) dy -= 1;
  if (keys.has('s') || keys.has('arrowdown')) dy += 1;
  if (keys.has('a') || keys.has('arrowleft')) dx -= 1;
  if (keys.has('d') || keys.has('arrowright')) dx += 1;

  if (dx || dy) {
    player = {
      x: Math.max(0, Math.min(GRID - 0.01, player.x + dx * speed)),
      y: Math.max(0, Math.min(GRID - 0.01, player.y + dy * speed)),
    };
    if (ts - lastMoveAt > 50) {
      lastMoveAt = ts;
      sendMove();
    }
  }
  requestAnimationFrame(movementLoop);
}

function renderLoop() {
  draw();
  requestAnimationFrame(renderLoop);
}

setInterval(poll, 100);
poll();
renderLoop();
requestAnimationFrame(movementLoop);
