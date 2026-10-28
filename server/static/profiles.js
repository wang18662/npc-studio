/**
 * AI 参数档案编辑器 · Schema 驱动版
 *
 * 核心变化：
 *   前端不认识任何具体的引擎字段，只认识 schema 里的通用键。
 *   引擎字段名只出现在 adapter 的 mapping 里，由 toEngine() 翻译。
 *
 * 数据仍以引擎字段名的 CSV 保存，读写时通过 adapter 转换——
 * 这样 UE 侧一行不用改。
 */

let schema = null;
let adapter = null;
let rows = [];
let current = -1;

const $ = (id) => document.getElementById(id);

// ============================================================
// 通用键 ↔ 引擎字段名
// ============================================================

function toEngine(key) {
  return (adapter && adapter.mapping && adapter.mapping[key]) || key;
}

function readValue(row, key) {
  const col = toEngine(key);
  return row[col];
}

function writeValue(row, key, value) {
  row[toEngine(key)] = String(value);
}

// ============================================================
// 启动
// ============================================================

async function boot() {
  const [schemaRes, adapterRes, profilesRes] = await Promise.all([
    fetch('/api/schema?id=npc.pursue').then((r) => r.json()),
    fetch('/api/adapter?id=shooterai').then((r) => r.json()),
    fetch('/api/profiles').then((r) => r.json()),
  ]);

  schema = schemaRes;
  adapter = adapterRes;
  rows = profilesRes.rows || [];

  $('schemaName').textContent = `${schema.title} · ${schema.fields.length} 个字段`;
  $('adapterName').textContent = adapter.displayName;

  renderList();
  if (rows.length) select(0);
  else {
    $('empty').hidden = false;
    $('editor').hidden = true;
  }
}

// ============================================================
// 列表
// ============================================================

function renderList() {
  $('list').innerHTML = rows
    .map(
      (r, i) => `<div class="item ${i === current ? 'active' : ''}" data-i="${i}">${
        r.Name || '(未命名)'
      }</div>`
    )
    .join('');

  document.querySelectorAll('.item').forEach((el) => {
    el.addEventListener('click', () => select(Number(el.dataset.i)));
  });
}

function select(i) {
  current = i;
  renderList();
  fillCompareOptions();
  renderForm();
  renderDiff();
}

// ============================================================
// 表单（完全由 schema 生成）
// ============================================================

function renderForm() {
  const row = rows[current];
  if (!row || !schema) return;

  $('empty').hidden = true;
  $('editor').hidden = false;
  $('f-name').value = row.Name || '';

  $('form').innerHTML = schema.groups
    .map((group) => {
      const fields = schema.fields.filter((f) => f.group === group.id);
      if (!fields.length) return '';
      return `<div class="group">
        <div class="group-head">${group.title}</div>
        <div class="grid">${fields.map((f) => renderField(f, row)).join('')}</div>
      </div>`;
    })
    .join('');

  bindEvents(row);
  check();
}

function renderField(field, row) {
  const raw = readValue(row, field.key);
  const value = raw === undefined || raw === '' ? (field.default ?? '') : raw;
  const tip = field.description ? ` title="${escapeAttr(field.description)}"` : '';

  // 这个字段参与了哪些约束——改之前就知道会牵连什么。
  const related = constraintsFor(field.key);
  const badge = related.length
    ? `<span class="c-badge" title="${escapeAttr(
        related.map((c) => `${c.id}: ${c.expr}`).join('\n')
      )}">${related.map((c) => c.id).join(' ')}</span>`
    : '';

  if (field.type === 'bool') {
    const on = isTrue(value);
    return `<div class="field"${tip}>
      <label>${field.label}${badge}</label>
      <select data-key="${field.key}">
        <option value="True" ${on ? 'selected' : ''}>True</option>
        <option value="False" ${!on ? 'selected' : ''}>False</option>
      </select>
    </div>`;
  }

  const min = field.min !== undefined ? `min="${field.min}"` : '';
  const max = field.max !== undefined ? `max="${field.max}"` : '';
  const unit = field.unit ? `<span class="unit">${field.unit}</span>` : '';

  return `<div class="field"${tip}>
    <label>${field.label}${badge}${unit}</label>
    <input type="number" step="any" data-key="${field.key}" value="${value}" ${min} ${max}>
  </div>`;
}

/** 找出某字段参与的所有约束。 */
function constraintsFor(fieldKey) {
  if (!schema || !schema.constraints) return [];
  const norm = normalizeKey(fieldKey);
  return schema.constraints.filter((constraint) =>
    normalizeExpr(constraint.expr).includes(norm)
  );
}

function bindEvents(row) {
  $('f-name').oninput = (e) => {
    row.Name = e.target.value;
    renderList();
  };

  document.querySelectorAll('[data-key]').forEach((el) => {
    el.addEventListener('change', () => {
      writeValue(row, el.dataset.key, el.value);
      check();
    });
  });
}

// ============================================================
// 约束校验（规则来自 schema.constraints）
// ============================================================

function normalizeKey(key) {
  return key.replace(/\./g, '_');
}

function normalizeExpr(expr) {
  return expr.replace(/([a-z]+)\.([a-zA-Z]+)/g, '$1_$2');
}

function buildContext(row) {
  const ctx = {};
  schema.fields.forEach((field) => {
    const raw = readValue(row, field.key);
    const value = raw === undefined || raw === '' ? field.default : raw;
    ctx[normalizeKey(field.key)] =
      field.type === 'bool' ? (isTrue(value) ? 1 : 0) : parseFloat(value) || 0;
  });
  return ctx;
}

function check() {
  const row = rows[current];
  if (!row || !schema) return;

  const ctx = buildContext(row);
  const names = Object.keys(ctx);
  const values = names.map((n) => ctx[n]);
  const issues = [];

  schema.constraints.forEach((constraint) => {
    try {
      const fn = new Function(...names, `return (${normalizeExpr(constraint.expr)});`);
      if (!fn(...values)) issues.push(constraint.message);
    } catch (err) {
      issues.push(`校验表达式有误（${constraint.id}）：${err.message}`);
    }
  });

  $('issues').innerHTML = issues.length
    ? issues.map((t) => `<div class="issue">${escapeHtml(t)}</div>`).join('')
    : '<div class="issue ok">参数约束检查通过</div>';
}

// ============================================================
// 保存 / 导出
// ============================================================

async function save() {
  const res = await fetch('/api/profiles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rows }),
  });
  const data = await res.json();
  alert(`已保存 ${data.count} 条档案`);
}

// ============================================================
// 工具
// ============================================================

function isTrue(v) {
  const s = String(v).toLowerCase();
  return s === 'true' || s === '1';
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}

function escapeAttr(text) {
  return escapeHtml(text).replace(/\n/g, ' ');
}

// ============================================================
// 档案对比
// ============================================================

function fillCompareOptions() {
  const select = $('compareSelect');
  const previous = select.value;

  select.innerHTML =
    '<option value="">（不对比）</option>' +
    rows
      .map((row, index) =>
        index === current ? '' : `<option value="${index}">${row.Name || '(未命名)'}</option>`
      )
      .join('');

  // 尽量保留原来的选择；如果那个索引变成当前档案了就清空
  const kept = Number(previous);
  if (previous && kept !== current && rows[kept]) {
    select.value = previous;
  } else {
    select.value = '';
  }
}

function renderDiff() {
  const box = $('diffView');
  const selected = $('compareSelect').value;

  if (selected === '') {
    box.hidden = true;
    return;
  }

  const currentRow = rows[current];
  const otherRow = rows[Number(selected)];
  if (!currentRow || !otherRow) {
    box.hidden = true;
    return;
  }

  const onlyDiff = $('onlyDiff').checked;
  const lines = [];

  schema.fields.forEach((field) => {
    const rawA = readValue(currentRow, field.key);
    const rawB = readValue(otherRow, field.key);
    const a = rawA === undefined || rawA === '' ? field.default : rawA;
    const b = rawB === undefined || rawB === '' ? field.default : rawB;

    const same = String(a) === String(b);
    if (onlyDiff && same) return;

    lines.push({ field, a, b, same, delta: deltaText(field, a, b) });
  });

  box.hidden = false;

  if (!lines.length) {
    box.innerHTML = '<div class="diff-empty">两个档案的参数完全一致。</div>';
    return;
  }

  const changedCount = lines.filter((line) => !line.same).length;

  box.innerHTML = `
    <div class="diff-head">
      <span><b>${escapeHtml(currentRow.Name || '')}</b> vs <b>${escapeHtml(
    otherRow.Name || ''
  )}</b></span>
      <span>${changedCount} 项不同</span>
    </div>
    <table class="diff-table">
      <thead>
        <tr>
          <th>参数</th>
          <th>${escapeHtml(currentRow.Name || '')}</th>
          <th>${escapeHtml(otherRow.Name || '')}</th>
          <th>差异</th>
        </tr>
      </thead>
      <tbody>
        ${lines
          .map(
            (line) => `<tr class="${line.same ? '' : 'changed'}">
              <td>${line.field.label}</td>
              <td class="val-a">${line.a}${line.field.unit || ''}</td>
              <td class="val-b">${line.b}${line.field.unit || ''}</td>
              <td class="diff-delta">${line.delta}</td>
            </tr>`
          )
          .join('')}
      </tbody>
    </table>
  `;
}

function deltaText(field, a, b) {
  if (String(a) === String(b)) return '—';

  if (field.type === 'bool') {
    return isTrue(b) ? '开' : '关';
  }

  const na = parseFloat(a);
  const nb = parseFloat(b);
  if (!Number.isFinite(na) || !Number.isFinite(nb)) return '不同';

  const diff = nb - na;
  if (diff === 0) return '—';
  return `${diff > 0 ? '+' : ''}${Number(diff.toFixed(3))}`;
}

// ============================================================
// 版本历史
// ============================================================

async function toggleHistory() {
  const panel = $('historyPanel');

  if (!panel.hidden) {
    panel.hidden = true;
    return;
  }

  const data = await fetch('/api/profiles/history').then((r) => r.json());
  const items = data.items || [];

  panel.hidden = false;

  if (!items.length) {
    panel.innerHTML =
      '<div class="history-empty">还没有历史版本。<br>每次点「保存」会自动留一份，最多保留 50 份。</div>';
    return;
  }

  panel.innerHTML =
    `<div class="history-tip">相同内容只保留一份；回滚前会自动备份当前状态。</div>` +
    items
      .map(
        (item) => `<div class="history-item">
        <span class="time">${formatStamp(item.stamp)}</span>
        <span class="meta">${item.count} 条 · ${escapeHtml(item.names.join(' / '))}</span>
        <button class="mini rollback" data-file="${item.file}">回滚</button>
      </div>`
      )
      .join('');

  panel.querySelectorAll('.rollback').forEach((btn) => {
    btn.addEventListener('click', () => rollback(btn.dataset.file));
  });
}

function formatStamp(stamp) {
  const match = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})/.exec(stamp);
  if (!match) return stamp;
  return `${match[1]}-${match[2]}-${match[3]} ${match[4]}:${match[5]}:${match[6]}`;
}

async function rollback(filename) {
  if (!confirm('回滚到这个版本？\n\n当前内容会先自动备份一份，回滚之后也能再回来。')) {
    return;
  }

  const result = await fetch('/api/profiles/rollback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file: filename }),
  }).then((r) => r.json());

  if (!result.ok) {
    alert(result.reason || '回滚失败');
    return;
  }

  $('historyPanel').hidden = true;
  await boot();
  alert('已回滚到该版本');
}

// ============================================================
// 事件绑定
// ============================================================

$('compareSelect').addEventListener('change', renderDiff);
$('onlyDiff').addEventListener('change', renderDiff);
$('btnHistory').addEventListener('click', toggleHistory);

$('btnSave').addEventListener('click', save);
$('btnNew').addEventListener('click', () => {
  const template = rows[current] || {};
  rows.push({ ...template, Name: 'New_Profile' });
  select(rows.length - 1);
});
$('btnDuplicate').addEventListener('click', () => {
  if (current < 0) return;
  rows.push({ ...rows[current], Name: `${rows[current].Name}_Copy` });
  select(rows.length - 1);
});
$('btnDelete').addEventListener('click', () => {
  if (current < 0) return;
  if (!confirm(`删除档案「${rows[current].Name}」？`)) return;
  rows.splice(current, 1);
  current = Math.min(current, rows.length - 1);
  renderList();
  if (current >= 0) renderForm();
  else {
    $('editor').hidden = true;
    $('empty').hidden = false;
  }
});
$('btnExport').addEventListener('click', () => window.open('/api/profiles/export', '_blank'));

boot();
