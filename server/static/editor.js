const LAYER_NAMES = { locomotion: '移动层', interaction: '交互层', combat: '战斗层' };
const ARCHETYPES = ['idle', 'movement', 'perception', 'combat', 'interaction', 'special'];
const STATE_COLORS = {
  '巡逻': '#6b8cff', '站桩': '#5f6b85', '追击': '#f0a04b', '驻留': '#e8c25a',
  '空闲': '#8b909c', '对话': '#63c98a', '待战': '#8b909c', '攻击': '#f2607a', '后撤': '#b07cf0',
};

let config = null;
let current = null;

const $ = (id) => document.getElementById(id);

function stateColor(name) {
  return STATE_COLORS[name] || '#8b909c';
}

function getState(layerId, stateId) {
  return config.layers[layerId].states.find((s) => s.id === stateId);
}

async function load() {
  const npcId = $('npcSelect').value;
  const res = await fetch(`/api/npc/raw?npcId=${npcId}`);
  if (!res.ok) {
    alert('加载失败');
    return;
  }
  config = await res.json();
  current = null;
  renderTree();
  renderForm();
  renderJson();
  $('jsonMeta').textContent = '';
  $('issues').innerHTML = '<span class="muted">尚未保存</span>';
}

function renderTree() {
  const tree = $('tree');

  if (!config.layers) {
    tree.innerHTML = '<p class="muted">这是继承配置，请编辑父级 guard_base。</p>';
    return;
  }

  tree.innerHTML = Object.entries(config.layers)
    .map(([lid, layer]) => {
      const items = layer.states
        .map((s) => {
          const active = current && current.layerId === lid && current.stateId === s.id;
          return `<div class="tree-item ${active ? 'active' : ''}" data-layer="${lid}" data-state="${s.id}">
            <span class="dot" style="background:${stateColor(s.name)}"></span>
            <span>${s.name}</span>
            <small>${s.archetype}</small>
          </div>`;
        })
        .join('');

      return `<div class="tree-group">
        <div class="tree-head"><span>${LAYER_NAMES[lid] || lid}</span><small>${layer.states.length}</small></div>
        ${items}
      </div>`;
    })
    .join('');

  tree.querySelectorAll('.tree-item').forEach((el) => {
    el.addEventListener('click', () => {
      current = { layerId: el.dataset.layer, stateId: el.dataset.state };
      renderTree();
      renderForm();
    });
  });
}

function renderForm() {
  const empty = $('formEmpty');
  const form = $('form');

  if (!current || !config.layers) {
    empty.hidden = false;
    form.hidden = true;
    return;
  }

  const s = getState(current.layerId, current.stateId);
  const transitions = s.transitions || [];

  empty.hidden = true;
  form.hidden = false;

  form.innerHTML = `
    <div class="row"><label>ID</label><input value="${s.id}" readonly></div>
    <div class="row"><label>名称</label><input id="f-name" value="${s.name}"></div>
    <div class="row"><label>原型</label>
      <select id="f-archetype">
        ${ARCHETYPES.map((a) => `<option value="${a}" ${a === s.archetype ? 'selected' : ''}>${a}</option>`).join('')}
      </select>
    </div>
    <div class="row"><label>优先级</label><input id="f-priority" type="number" value="${s.priority ?? 0}"></div>
    <div class="row"><label>需要能力</label><input id="f-requires" value="${(s.requires || []).join(', ')}" placeholder="Move, Animate"></div>
    <div class="row"><label>锁定能力</label><input id="f-locks" value="${(s.locks || []).join(', ')}" placeholder="Attack"></div>
    <div class="row"><label>终止状态</label>
      <select id="f-terminal">
        <option value="false" ${!s.terminal ? 'selected' : ''}>否</option>
        <option value="true" ${s.terminal ? 'selected' : ''}>是</option>
      </select>
    </div>

    <h3>参数（JSON）</h3>
    <div class="row"><label></label>
      <textarea id="f-params" rows="4">${JSON.stringify(s.params || {}, null, 2)}</textarea>
    </div>

    <h3>状态转移（${transitions.length}）</h3>
    <div class="transitions">
      ${transitions
        .map(
          (t, i) => `<div class="transition">
            <span class="arrow">→</span>
            <b>${t.to}</b>
            <input data-ti="${i}" data-field="priority" type="number" value="${t.priority}" title="优先级">
            <input data-ti="${i}" data-field="condition" value="${String(t.condition).replace(/"/g, '&quot;')}" title="条件">
            <button class="mini danger" data-del="${i}">×</button>
          </div>`
        )
        .join('')}
    </div>
  `;

  $('f-name').addEventListener('input', (e) => {
    s.name = e.target.value;
    afterEdit();
  });
  $('f-archetype').addEventListener('change', (e) => {
    s.archetype = e.target.value;
    afterEdit();
  });
  $('f-priority').addEventListener('input', (e) => {
    s.priority = Number(e.target.value) || 0;
    afterEdit();
  });
  $('f-requires').addEventListener('input', (e) => {
    s.requires = splitList(e.target.value);
    afterEdit();
  });
  $('f-locks').addEventListener('input', (e) => {
    s.locks = splitList(e.target.value);
    afterEdit();
  });
  $('f-terminal').addEventListener('change', (e) => {
    s.terminal = e.target.value === 'true';
    afterEdit();
  });
  $('f-params').addEventListener('change', (e) => {
    try {
      s.params = JSON.parse(e.target.value || '{}');
      e.target.style.borderColor = '';
      afterEdit();
    } catch (err) {
      e.target.style.borderColor = '#f2607a';
    }
  });

  form.querySelectorAll('.transition input').forEach((input) => {
    input.addEventListener('input', () => {
      const t = s.transitions[Number(input.dataset.ti)];
      if (!t) return;
      if (input.dataset.field === 'priority') t.priority = Number(input.value) || 0;
      else t.condition = input.value;
      afterEdit();
    });
  });

  form.querySelectorAll('[data-del]').forEach((btn) => {
    btn.addEventListener('click', () => {
      s.transitions.splice(Number(btn.dataset.del), 1);
      renderForm();
      afterEdit();
    });
  });
}

function splitList(text) {
  return text.split(',').map((x) => x.trim()).filter(Boolean);
}

function afterEdit() {
  renderJson();
  $('jsonMeta').textContent = '已修改（未保存）';
}

function renderJson() {
  $('jsonView').textContent = JSON.stringify(config, null, 2);
}

async function save() {
  const npcId = $('npcSelect').value;
  const res = await fetch('/api/npc/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ npcId, config }),
  });
  const result = await res.json();
  renderIssues(result);
  if (result.ok) $('jsonMeta').textContent = '已保存';
}

function renderIssues(result) {
  const box = $('issues');

  if (result.reason) {
    box.innerHTML = `<div class="issue error"><b>失败</b> ${result.reason}</div>`;
    return;
  }

  if (!result.issues || !result.issues.length) {
    box.innerHTML = '<span class="muted">校验通过，无问题</span>';
    return;
  }

  box.innerHTML = result.issues
    .map(
      (i) => `<div class="issue ${i.level}">
        <b>${i.rule}</b> ${i.message}
        <div class="path">${i.path}</div>
      </div>`
    )
    .join('');
}

$('btnReload').addEventListener('click', load);
$('btnSave').addEventListener('click', save);
$('btnExportCsv').addEventListener('click', () => {
  window.open(`/api/export/datatable?npcId=${$('npcSelect').value}`, '_blank');
});
$('btnExportDoc').addEventListener('click', () => {
  window.open(`/api/export/doc?npcId=${$('npcSelect').value}`, '_blank');
});
$('npcSelect').addEventListener('change', load);

load();
