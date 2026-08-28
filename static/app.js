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
