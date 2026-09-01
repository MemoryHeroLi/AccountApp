// 公共工具：请求封装、格式化、弹窗、类别配色
async function api(url, options = {}) {
  const res = await fetch(url, {
    headers: options.body ? { 'Content-Type': 'application/json' } : {},
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `请求失败 (${res.status})`);
  return data;
}

function money(n) {
  const v = Number(n);
  return '¥' + (Math.abs(v) < 0.005 ? 0 : v.toFixed(2));
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

const CATEGORY_COLORS = [
  '#ef5350', '#5c6bc0', '#26a69a', '#ffa726', '#ab47bc', '#66bb6a',
  '#29b6f6', '#ec407a', '#8d6e63', '#78909c', '#d4e157', '#ffca28',
];
function categoryColor(name) {
  let h = 0;
  for (const c of String(name)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return CATEGORY_COLORS[h % CATEGORY_COLORS.length];
}

function toast(msg, isErr = false) {
  const el = document.createElement('div');
  el.className = 'toast' + (isErr ? ' err' : '');
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), isErr ? 4000 : 2200);
}

function categoryBadge(tx) {
  if (!tx.category_name) return '<span class="badge pending">待分类</span>';
  const c = categoryColor(tx.category_name);
  const label = tx.subcategory_name
    ? `${tx.category_name} › ${tx.subcategory_name}`
    : tx.category_name;
  return `<span class="badge" style="background:${c}1a;color:${c}">${esc(label)}</span>`;
}

// 一级分类 + 二级分类两个 td（供交易/规则/类别三页共用）
function catCells(topName, subName) {
  if (!topName) return '<td><span class="badge pending">待分类</span></td><td class="text-muted">-</td>';
  const c = categoryColor(topName);
  return `<td><span class="badge" style="background:${c}1a;color:${c}">${esc(topName)}</span></td>
          <td>${subName ? `<span class="badge" style="background:${c}22;color:${c}">${esc(subName)}</span>` : '<span class="text-muted">-</span>'}</td>`;
}

// 一级分类下拉选项（"全部类别" / "请选择一级分类" 等由调用方加）
function topOptions(cats) {
  return cats.filter(c => !c.parent_id)
    .map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('');
}

// 填充二级分类下拉（联动一级），可选回填选中值
function fillSub(sel, cats, topId, subId) {
  sel.innerHTML = '<option value="">（无二级分类）</option>';
  cats.filter(c => c.parent_id === topId).forEach(c => {
    const opt = document.createElement('option');
    opt.value = c.id;
    opt.textContent = c.name;
    sel.appendChild(opt);
  });
  if (subId) sel.value = String(subId);
}

// 多选下拉组件（消费日历/统计分析筛选栏共用）
// 用法：const ms = multiSelect(el, {placeholder: '全部类别', onChange: fn})
//       ms.setOptions([{value, label}, ...]) / ms.setDisabled('提示文字') / ms.values() / ms.clear()
function multiSelect(el, { placeholder = '全部', onChange = null } = {}) {
  el.classList.add('msel');
  el.innerHTML =
    '<button type="button" class="msel-btn"><span class="msel-label"></span><span class="msel-arrow">▾</span></button>' +
    '<div class="msel-panel"></div>';
  const btn = el.querySelector('.msel-btn');
  const label = el.querySelector('.msel-label');
  const panel = el.querySelector('.msel-panel');
  let items = [];
  let selected = new Set();   // 存字符串形式的 value
  let disabled = false;

  function render() {
    const chosen = items.filter(it => selected.has(String(it.value)));
    label.textContent = !chosen.length ? placeholder
      : chosen.length <= 2 ? chosen.map(c => c.label).join('、')
      : `已选 ${chosen.length} 项`;
    panel.innerHTML = items.map(it => `
      <label class="msel-item">
        <input type="checkbox" value="${esc(it.value)}"${selected.has(String(it.value)) ? ' checked' : ''}>
        <span>${esc(it.label)}</span>
      </label>`).join('');
  }

  btn.onclick = () => {
    if (disabled) return;
    document.querySelectorAll('.msel.open').forEach(m => {
      if (m !== el) m.classList.remove('open');
    });
    el.classList.toggle('open');
  };
  panel.onchange = e => {
    if (e.target.checked) selected.add(e.target.value);
    else selected.delete(e.target.value);
    render();
    if (onChange) onChange();
  };
  document.addEventListener('click', e => {
    if (!el.contains(e.target)) el.classList.remove('open');
  });

  return {
    setOptions(next) {
      items = next;
      const valid = new Set(next.map(it => String(it.value)));
      selected = new Set([...selected].filter(v => valid.has(v)));  // 保留仍存在的勾选
      disabled = false;
      el.classList.remove('disabled');
      btn.disabled = false;
      render();
    },
    setDisabled(text) {
      items = [];
      selected.clear();
      disabled = true;
      el.classList.add('disabled');
      btn.disabled = true;
      label.textContent = text;
      panel.innerHTML = '';
      el.classList.remove('open');
    },
    values() { return [...selected]; },
    clear() { selected.clear(); render(); },
  };
}

function sourceBadge(tx) {
  return `<span class="badge src-${tx.source}">${esc(tx.source_name)}</span>`;
}

function amountCell(tx) {
  if (tx.refund_amount > 0) {
    const raw = tx.amount + tx.refund_amount;
    return `<span class="amount ${tx.amount === 0 ? 'zero' : ''}">` +
           (tx.amount === 0 ? '' : '') +
           `<s>${money(raw)}</s>${money(tx.amount)}</span>`;
  }
  return `<span class="amount">${money(tx.amount)}</span>`;
}
