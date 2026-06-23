/* TCC — application JavaScript */

/* ── CSRF token for fetch() ──────────────────────────────────────────────────── */
const _csrfMeta = document.querySelector('meta[name="csrf-token"]');
const CSRF_TOKEN = _csrfMeta ? _csrfMeta.content : '';

function csrfFetch(url, options = {}) {
  const headers = Object.assign({ 'X-CSRFToken': CSRF_TOKEN }, options.headers || {});
  return fetch(url, Object.assign({}, options, { headers }));
}

/* ── Flash auto-dismiss ──────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.flash-close').forEach(btn => {
    btn.addEventListener('click', () => btn.closest('.flash').remove());
  });
  // Auto-dismiss success flashes after 5 s
  document.querySelectorAll('.flash-success').forEach(el => {
    setTimeout(() => el.style.opacity === '' && el.remove(), 5000);
  });
});

/* ── Tabs (simple vanilla, no Alpine required) ────────────────────────────────────── */
function initTabs(container) {
  const btns   = container.querySelectorAll('.tab-btn');
  const panels = container.querySelectorAll('.tab-panel');
  btns.forEach(btn => {
    btn.addEventListener('click', () => {
      btns.forEach(b => b.classList.remove('active'));
      panels.forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      const target = btn.dataset.tab;
      const panel  = container.querySelector(`#tab-${target}`);
      if (panel) panel.classList.add('active');
    });
  });
}
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-tabs]').forEach(initTabs);
});

/* ── Manager-password modal helpers ──────────────────────────────────────────── */
function openConfirmModal(modalId) {
  const el = document.getElementById(modalId);
  if (el) {
    el.style.display = 'flex';
    const pwField = el.querySelector('input[type="password"]');
    if (pwField) { pwField.value = ''; pwField.focus(); }
  }
}
function closeConfirmModal(modalId) {
  const el = document.getElementById(modalId);
  if (el) el.style.display = 'none';
}
// Close modal when clicking the backdrop directly
document.addEventListener('click', e => {
  if (e.target.classList.contains('tcc-modal-backdrop')) {
    e.target.style.display = 'none';
  }
});

/* ── Number formatting ────────────────────────────────────────────────────── */
function formatGNF(n) {
  return 'GNF ' + parseInt(n || 0).toLocaleString('en');
}
