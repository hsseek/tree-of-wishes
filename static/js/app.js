/**
 * app.js — bootstraps grid + modal for the current board page.
 * PAGE_BOARD is set as a global by the template.
 */

document.addEventListener('DOMContentLoaded', async () => {
  await i18n.init();
  _updateLangToggle();

  const gridContainer = document.getElementById('wish-grid');
  if (!gridContainer) return;

  const modal = new WishModal({ board: PAGE_BOARD });
  window.wishModal = modal;

  const grid = new WishGrid({ container: gridContainer, board: PAGE_BOARD, onOpen: w => modal.open(w) });
  window.wishGrid = grid;
  await grid.init();

  _initShortcuts();

  // Auto-open a wish linked from search on another page
  const openId = new URLSearchParams(window.location.search).get('open');
  if (openId) {
    history.replaceState(null, '', window.location.pathname);
    const r = await fetch(`/api/wishes/${openId}`);
    if (r.ok) modal.open(await r.json());
  }

  // Make a Wish button (tree only)
  document.getElementById('btn-new-wish')?.addEventListener('click', () => {
    document.getElementById('new-wish-overlay')?.classList.add('open');
  });

  // Search
  document.getElementById('search-form')?.addEventListener('submit', async e => {
    e.preventDefault();
    const q = document.getElementById('search-input')?.value.trim();
    if (q) await _doSearch(q);
  });

  // Language toggle
  document.getElementById('lang-toggle')?.addEventListener('click', async () => {
    const next = i18n.getLang() === 'en' ? 'ko' : 'en';
    await i18n.setLang(next);
    _updateLangToggle();
    if (typeof CURRENT_USER_ID !== 'undefined' && CURRENT_USER_ID !== null) {
      const fd = new FormData();
      fd.append('language', next);
      fetch('/api/me/language', { method: 'PATCH', body: fd }).catch(() => {});
    }
  });
});

function _updateLangToggle() {
  const btn = document.getElementById('lang-toggle');
  if (btn) btn.textContent = i18n.getLang() === 'en' ? '한국어' : 'English';
}

// ─── New wish form ─────────────────────────────────────────────────────────────

function closeNewWish() {
  document.getElementById('new-wish-overlay')?.classList.remove('open');
}

async function submitNewWish(e) {
  e.preventDefault();
  const form = e.target;
  const btn = form.querySelector('[type=submit]');
  btn.disabled = true;
  btn.textContent = i18n.t('wish.submitting');

  const fd = new FormData(form);
  try {
    const resp = await fetch('/api/wishes', { method: 'POST', body: fd });
    if (resp.ok) {
      form.reset();
      closeNewWish();
      _showToast('Wish placed on the tree!', 'success');
      window.wishGrid?.init();
    } else {
      const err = await resp.json().catch(() => ({}));
      _showToast(_apiErrMsg(resp.status, err.detail), 'error');
    }
  } finally {
    btn.disabled = false;
    btn.textContent = i18n.t('wish.submit');
  }
}

function _apiErrMsg(status, detail) {
  if (status === 429) return i18n.t('error.tooManyRequests');
  if (status === 413) return i18n.t('error.fileTooLarge');
  if (status === 415) return i18n.t('error.fileTypeNotAllowed');
  if ((detail || '').includes('future')) return i18n.t('error.dueDatePast');
  return detail || i18n.t('error.generic');
}

// ─── Search ────────────────────────────────────────────────────────────────────

async function _doSearch(q) {
  const resultsEl = document.getElementById('search-results');
  resultsEl.innerHTML = `<span>${i18n.t('search.searching')}</span>`;
  resultsEl.style.display = 'block';

  const resp = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
  const data = await resp.json();

  if (!data.results?.length) {
    resultsEl.innerHTML = `<p class="search-empty">${i18n.t('search.noResults')}</p>`;
    return;
  }

  const wishMap = {};
  data.results.forEach(w => { wishMap[w.id] = w; });

  const items = data.results.map(w => {
    const board = i18n.t(w.board === 'tree' ? 'search.board.tree' : 'search.board.columbarium');
    const text  = (w.text || '').slice(0, 80) + (w.text?.length > 80 ? '…' : '');
    return `<div class="search-result-item">
      <span class="search-result-board">[${board}]</span>
      <span class="search-result-text">${_esc(text)}</span>
      ${w.name ? `<span class="search-result-name">— ${_esc(w.name)}</span>` : ''}
      <button class="search-result-goto" data-id="${w.id}" data-board="${w.board}">${i18n.t('search.goTo')}</button>
    </div>`;
  }).join('');

  resultsEl.innerHTML = `<div class="search-results-list">${items}</div>`;

  resultsEl.querySelectorAll('.search-result-goto').forEach(btn => {
    btn.addEventListener('click', () => {
      const wish = wishMap[parseInt(btn.dataset.id)];
      if (btn.dataset.board === PAGE_BOARD) {
        window.wishModal?.open(wish);
      } else {
        window.location.href = `/${btn.dataset.board}?open=${wish.id}`;
      }
    });
  });
}

function _esc(str) {
  return (str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function _showToast(msg, type = 'info') {
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.textContent = msg;
  document.body.appendChild(t);
  requestAnimationFrame(() => t.classList.add('toast-show'));
  setTimeout(() => { t.classList.remove('toast-show'); setTimeout(() => t.remove(), 400); }, 2800);
}

// ─── Keyboard shortcuts ──────────────────────────────────────────────────────────

function _initShortcuts() {
  document.addEventListener('keydown', e => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;

    // Don't hijack typing. (The modal binds its own global Esc handler, so Esc
    // still closes the modal even from a field.)
    const ae = document.activeElement;
    const typing = ae && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA'
      || ae.tagName === 'SELECT' || ae.isContentEditable);
    if (typing) return;

    const modal = window.wishModal;

    switch (e.key) {
      case 'j': // next wish — older
        if (modal?.isOpen) { e.preventDefault(); modal.navigate('older'); }
        break;
      case 'k': // previous wish — younger
        if (modal?.isOpen) { e.preventDefault(); modal.navigate('younger'); }
        break;
      case '/': // focus search
        e.preventDefault();
        modal?.close();
        document.getElementById('search-input')?.focus();
        break;
      case 'r': // open a random wish
        e.preventDefault();
        _openRandomWish();
        break;
      case '?': // toggle help
        e.preventDefault();
        _toggleShortcutsHelp();
        break;
      case 'Escape': { // close the help overlay (modal handles its own Esc)
        const ov = document.getElementById('shortcuts-overlay');
        if (ov?.classList.contains('open')) _toggleShortcutsHelp(false);
        break;
      }
    }
  });
}

function _openRandomWish() {
  const wishes = window.wishGrid?.wishes || [];
  if (!wishes.length) { _showToast(i18n.t('shortcuts.noWishes'), 'info'); return; }
  const w = wishes[Math.floor(Math.random() * wishes.length)];
  window.wishModal?.open(w);
}

function _toggleShortcutsHelp(force) {
  const ov = document.getElementById('shortcuts-overlay') || _buildShortcutsHelp();
  const show = force === undefined ? !ov.classList.contains('open') : force;
  ov.classList.toggle('open', show);
}

function _buildShortcutsHelp() {
  const rows = [
    ['j',   i18n.t('shortcuts.older')],
    ['k',   i18n.t('shortcuts.younger')],
    ['r',   i18n.t('shortcuts.random')],
    ['/',   i18n.t('shortcuts.search')],
    ['Esc', i18n.t('shortcuts.close')],
    ['?',   i18n.t('shortcuts.help')],
  ].map(([key, label]) =>
    `<div class="sc-row"><kbd class="sc-key">${_esc(key)}</kbd><span class="sc-label">${_esc(label)}</span></div>`
  ).join('');

  const ov = document.createElement('div');
  ov.id = 'shortcuts-overlay';
  ov.className = 'shortcuts-overlay';
  ov.innerHTML = `
    <div class="shortcuts-card" role="dialog" aria-modal="true">
      <button class="shortcuts-close" aria-label="Close">×</button>
      <h3 class="shortcuts-title">${_esc(i18n.t('shortcuts.title'))}</h3>
      <div class="sc-rows">${rows}</div>
      <p class="shortcuts-hint">${_esc(i18n.t('shortcuts.hint'))}</p>
    </div>`;
  document.body.appendChild(ov);

  ov.addEventListener('click', e => { if (e.target === ov) _toggleShortcutsHelp(false); });
  ov.querySelector('.shortcuts-close').addEventListener('click', () => _toggleShortcutsHelp(false));
  return ov;
}
