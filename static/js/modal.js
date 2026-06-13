/**
 * WishModal — wish detail, like, edit, image thumbnail.
 */
class WishModal {
  constructor({ board }) {
    this.board = board;
    this.el = document.getElementById('wish-modal');
    this.backdrop = document.getElementById('modal-backdrop');
    this._currentWish = null;
    this._storedPassword = null; // null = owner (no password needed), string = verified password
    this._isOwner = false;

    this.el.querySelector('.modal-close').addEventListener('click', () => this.close());
    this.backdrop.addEventListener('click', () => this.close());
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') { this.close(); return; }
      // Ctrl+Enter (Cmd+Return on Mac) saves while the edit panel is open —
      // btn-save exists only in edit mode, so it doubles as the guard.
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && this.isOpen
          && document.getElementById('btn-save')) {
        e.preventDefault();
        this._doSave();
      }
    });

    // On-screen navigation mirrors the j/k/r keyboard shortcuts for touch users.
    // Left = previous (j, older); right = next (k, younger).
    this._navPrev = document.getElementById('modal-nav-prev');
    this._navNext = document.getElementById('modal-nav-next');
    const navRandom = document.getElementById('modal-nav-random');
    this._navPrev?.addEventListener('click', () => this.navigate('older'));
    this._navNext?.addEventListener('click', () => this.navigate('younger'));
    navRandom?.addEventListener('click', () => this.random());
    if (this._navPrev) this._navPrev.title = `${i18n.t('shortcuts.older')} (j)`;
    if (this._navNext) this._navNext.title = `${i18n.t('shortcuts.younger')} (k)`;
    if (navRandom) navRandom.title = `${i18n.t('shortcuts.random')} (r)`;
  }

  async open(wish) {
    this._currentWish = wish;
    this._storedPassword = null;
    this._isOwner = typeof CURRENT_USER_ID !== 'undefined'
      && CURRENT_USER_ID !== null
      && wish.owner_id === CURRENT_USER_ID;
    this._isAdmin = typeof IS_ADMIN !== 'undefined' && IS_ADMIN === true;

    fetch(`/api/wishes/${wish.id}/view`, { method: 'POST' });
    this._renderMain(wish);
    this._updateNav(wish);
    this.el.classList.add('open');
    this.backdrop.classList.add('open');

    // Owners and admins skip the unlock step entirely
    if (this._isOwner || this._isAdmin) {
      this._renderEditPanel();
    }
  }

  close() {
    this.el.classList.remove('open');
    this.backdrop.classList.remove('open');
    this._currentWish = null;
  }

  get isOpen() { return this.el.classList.contains('open'); }

  /**
   * Step to an adjacent wish by creation time while the modal is open.
   * direction 'older' → next (earlier created_at); 'younger' → previous.
   * Wishes are ordered globally by created_at, so neighbours may sit far
   * apart on the tree — that's expected.
   */
  navigate(direction) {
    if (!this.isOpen || !this._currentWish) return;
    const list = this._orderedWishes();
    if (list.length < 2) return;

    let idx = list.findIndex(w => w.id === this._currentWish.id);
    if (idx === -1) return;
    idx += (direction === 'older' ? 1 : -1);
    if (idx < 0 || idx >= list.length) return; // stop at the ends
    this.open(list[idx]);
  }

  /** Open a random wish from the current board (mirrors the `r` shortcut). */
  random() {
    const list = window.wishGrid?.wishes || [];
    if (!list.length) return;
    this.open(list[Math.floor(Math.random() * list.length)]);
  }

  /** Wishes ordered youngest → oldest, the order used for younger/older steps. */
  _orderedWishes() {
    return (window.wishGrid?.wishes || [])
      .filter(w => w.created_at)
      .sort((a, b) => _ts(b.created_at) - _ts(a.created_at));
  }

  /** Grey out prev/next at the ends of the list so the controls read true. */
  _updateNav(wish) {
    const list = this._orderedWishes();
    const idx = list.findIndex(w => w.id === wish.id);
    const atEnds = idx === -1 || list.length < 2;
    // previous (j) steps older → off at the oldest end;
    // next (k) steps younger → off at the newest end.
    if (this._navPrev) this._navPrev.disabled = atEnds || idx === list.length - 1;
    if (this._navNext) this._navNext.disabled = atEnds || idx === 0;
  }

  _renderMain(wish) {
    const body = this.el.querySelector('.modal-body');
    // The Columbarium holds only one state (dead), so a status chip there would be
    // redundant — only tree wishes (active/fulfilled, or an expiring countdown) get one.
    let statusLabel = {
      active: i18n.t('wish.status.active'),
      fulfilled: i18n.t('wish.status.fulfilled'),
    }[wish.status] || '';
    let statusClass = wish.status;

    // A recently-placed wish shows "New" (keeping the active colour), matching the
    // green "new" firefly. Date-based (created within the last 24h) so it's
    // independent of what the grid has loaded — created_at is naive UTC, parsed
    // via the same helper the grid uses.
    const isNew = wish.status === 'active' && wish.board === 'tree'
      && wish.created_at && typeof _utcMillis === 'function'
      && _utcMillis(wish.created_at) >= Date.now() - 24 * 60 * 60 * 1000;

    // Expiring active wishes (≤7 days left) show a countdown to their Columbarium
    // move instead of the plain "active" chip, so a clicker understands the blink.
    // "New" takes precedence over the countdown, mirroring the firefly.
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const dueDate = wish.due_date ? new Date(wish.due_date + 'T00:00:00') : null;
    const daysLeft = dueDate ? Math.round((dueDate - today) / 86400000) : null;
    if (isNew) {
      statusLabel = i18n.t('wish.status.new');
      statusClass = 'active';
    } else if (wish.status === 'active' && daysLeft !== null && daysLeft <= 7) {
      // The lazy sweep moves a wish only once its due_date has *passed*
      // (due_date < today), i.e. at the start of the day after the due date —
      // so the actual move is (daysLeft + 1) days away, not daysLeft.
      const moveInDays = daysLeft + 1;
      statusLabel = moveInDays >= 2  ? i18n.t('wish.status.expiring').replace('{n}', moveInDays)
                  : moveInDays === 1 ? i18n.t('wish.status.expiringTomorrow')
                  :                    i18n.t('wish.status.expiringSoon');
      statusClass = 'expiring';
    }

    const dueStr      = wish.due_date    ? new Date(wish.due_date).toLocaleDateString()    : '—';
    const createdStr  = wish.created_at  ? new Date(wish.created_at).toLocaleDateString()  : '—';
    const fulfilledStr = wish.fulfilled_at ? new Date(wish.fulfilled_at).toLocaleDateString() : null;

    let attachmentHtml = '';
    if (wish.has_attachment) {
      const isImage = (wish.attachment_mimetype || '').startsWith('image/');
      if (isImage) {
        attachmentHtml = `
          <div class="modal-thumbnail">
            <a href="/api/attachment/${wish.id}" target="_blank" rel="noopener">
              <img src="/api/attachment/${wish.id}" alt="${_esc(wish.attachment_filename)}" class="attachment-thumb" />
            </a>
            <div class="attachment-label">${_esc(wish.attachment_filename)}</div>
          </div>`;
      } else {
        attachmentHtml = `
          <a class="attachment-link" href="/api/attachment/${wish.id}" target="_blank" rel="noopener">
            ${i18n.t('wish.downloadAttachment')}: ${_esc(wish.attachment_filename)}
          </a>`;
      }
    }

    // Show unlock section for non-owners/non-admins on either board, so anonymous
    // creators can unlock with their password and edit/delete (tree and columbarium alike).
    const showUnlock = !this._isOwner && !this._isAdmin;

    // The status now lives in the header bar (the space the decorative ✦ used to
    // hold, left of the nav buttons) rather than at the top of the body.
    const statusHost = this.el.querySelector('.modal-status-host');
    if (statusHost) {
      statusHost.innerHTML = statusLabel
        ? `<div class="modal-status ${statusClass}">${statusLabel}</div>`
        : '';
    }

    body.innerHTML = `
      <div class="modal-text">${_esc(wish.text)}</div>
      ${wish.name ? `<div class="modal-name">— ${_esc(wish.name)}</div>` : ''}
      <div class="modal-meta">
        <span>${i18n.t('wish.due')}: <strong>${dueStr}</strong></span>
        <span>${i18n.t('wish.placed')}: <strong>${createdStr}</strong></span>
        ${fulfilledStr ? `<span>${i18n.t('wish.fulfilledOn')}: <strong>${fulfilledStr}</strong></span>` : ''}
      </div>
      ${attachmentHtml}
      <div class="modal-stats">
        <span id="modal-views">${wish.views} ${i18n.t('wish.views')}</span>
        <span id="modal-likes">${wish.likes} ${this._likeT('likes')}</span>
      </div>
      <div class="modal-actions" id="modal-actions">
        <button class="btn-like" id="btn-like">${this._likeT('likeBtn')}</button>
        <button class="btn-share" id="btn-share">${i18n.t('wish.share')}</button>
        ${showUnlock ? this._unlockHtml() : ''}
      </div>
      <div id="edit-panel" style="display:none"></div>
    `;

    document.getElementById('btn-like').addEventListener('click', () => this._doLike());
    document.getElementById('btn-share').addEventListener('click', () => this._doShare());
    document.getElementById('btn-unlock')?.addEventListener('click', () => this._doUnlock());

    fetch(`/api/wishes/${wish.id}/liked`)
      .then(r => r.json())
      .then(data => { if (data.liked) this._setLiked(true); });
  }

  _setLiked(liked) {
    const btn = document.getElementById('btn-like');
    if (!btn) return;
    if (liked) {
      btn.textContent = this._likeT('unlikeBtn');
      btn.classList.add('liked');
    } else {
      btn.textContent = this._likeT('likeBtn');
      btn.classList.remove('liked');
    }
  }

  _likeT(key) {
    const ck = 'columbarium.' + key;
    const wk = 'wish.' + key;
    return this.board === 'columbarium' ? i18n.t(ck) || i18n.t(wk) : i18n.t(wk);
  }

  _unlockHtml() {
    return `
      <div class="unlock-section">
        <input type="password" id="unlock-password"
          placeholder="${i18n.t('wish.passwordPlaceholderShort')}" class="unlock-input" />
        <button id="btn-unlock" class="btn-secondary">${i18n.t('wish.unlock')}</button>
      </div>`;
  }

  // Append password to FormData only when a password was entered (non-owners have null)
  _appendPassword(fd) {
    if (this._storedPassword !== null) fd.append('password', this._storedPassword);
  }

  async _doShare() {
    // Bake the current page language into the link so the OG preview matches it
    // even when fetched by a crawler (which carries no language cookie).
    const lang = (typeof i18n !== 'undefined' && i18n.getLang) ? i18n.getLang() : 'ko';
    const url = `${window.location.origin}/wish/${this._currentWish.id}?lang=${lang}`;
    const ok = await _copyText(url);
    _showToast(ok ? i18n.t('wish.linkCopied') : url, ok ? 'success' : 'info');
  }

  async _doLike() {
    const btn = document.getElementById('btn-like');
    btn.disabled = true;
    const resp = await fetch(`/api/wishes/${this._currentWish.id}/like`, { method: 'POST' });
    const data = await resp.json();
    document.getElementById('modal-likes').textContent = `${data.likes} ${this._likeT('likes')}`;
    btn.disabled = false;
    this._setLiked(data.liked);
  }

  async _doUnlock() {
    const pw = document.getElementById('unlock-password').value;
    if (!pw) return;
    const btn = document.getElementById('btn-unlock');
    btn.textContent = i18n.t('wish.unlocking');
    btn.disabled = true;

    const fd = new FormData();
    fd.append('password', pw);
    const resp = await fetch(`/api/wishes/${this._currentWish.id}/verify`, { method: 'POST', body: fd });

    if (resp.ok) {
      this._storedPassword = pw;
      document.querySelector('.unlock-section')?.remove();
      this._renderEditPanel();
    } else {
      btn.textContent = i18n.t('wish.unlock');
      btn.disabled = false;
      _showToast(i18n.t('error.wrongPassword'), 'error');
    }
  }

  _renderEditPanel() {
    const panel = document.getElementById('edit-panel');
    const wish = this._currentWish;
    const isFulfilled = wish.status === 'fulfilled';
    // "Let go" retires an active wish to the Columbarium early — only meaningful
    // for a wish still living on the tree (not one already fulfilled or interred).
    const showLetGo = wish.status === 'active' && wish.board === 'tree';
    panel.style.display = '';

    const showAttachment = this._isOwner || this._isAdmin;
    const attachmentControls = showAttachment ? `
      <div class="edit-row">
        ${wish.has_attachment
          ? `<button id="btn-remove-attachment" class="btn-danger-sm">${i18n.t('wish.removeAttachment')}</button>`
          : ''}
        <label class="field-label">${i18n.t(wish.has_attachment ? 'wish.replaceAttachment' : 'wish.attachment')}</label>
        <input type="file" id="edit-attachment" accept="image/*,application/pdf,text/plain" />
        <span class="form-hint" data-i18n="wish.attachmentHint">${i18n.t('wish.attachmentHint')}</span>
      </div>` : '';

    panel.innerHTML = `
      <div class="edit-panel">
        <h4 class="edit-title">Edit</h4>
        <label class="field-label">${i18n.t('wish.editText')}</label>
        <textarea id="edit-text" class="edit-textarea" rows="4">${_esc(wish.text)}</textarea>
        ${attachmentControls}
        <div class="edit-actions">
          <button id="btn-save" class="btn-primary">${i18n.t('wish.save')}</button>
          <button id="btn-fulfill" class="btn-secondary">
            ${isFulfilled ? i18n.t('wish.markUnfulfilled') : i18n.t('wish.markFulfilled')}
          </button>
          ${showLetGo ? `<button id="btn-letgo" class="btn-secondary" title="${i18n.t('wish.letGoHint')}">${i18n.t('wish.letGo')}</button>` : ''}
          <button id="btn-delete" class="btn-danger">${i18n.t('wish.delete')}</button>
        </div>
      </div>`;

    document.getElementById('btn-save').addEventListener('click', () => this._doSave());
    document.getElementById('btn-fulfill')?.addEventListener('click', () => this._doFulfill());
    document.getElementById('btn-letgo')?.addEventListener('click', () => this._doFail());
    document.getElementById('btn-delete').addEventListener('click', () => this._doDelete());
    document.getElementById('btn-remove-attachment')?.addEventListener('click', () => this._doRemoveAttachment());
  }

  async _doSave() {
    const btn = document.getElementById('btn-save');
    btn.textContent = i18n.t('wish.saving');
    btn.disabled = true;

    const fd = new FormData();
    this._appendPassword(fd);
    fd.append('text', document.getElementById('edit-text').value);
    const file = document.getElementById('edit-attachment')?.files[0];
    if (file) fd.append('attachment', file);

    const resp = await fetch(`/api/wishes/${this._currentWish.id}`, { method: 'PATCH', body: fd });
    if (resp.ok) {
      const updated = await resp.json();
      this._currentWish = updated;
      _showToast('Saved!', 'success');
      this.close();
      if (window.wishGrid) window.wishGrid.init();
    } else {
      const err = await resp.json().catch(() => ({}));
      _showToast(err.detail || i18n.t('error.generic'), 'error');
    }
    btn.textContent = i18n.t('wish.save');
    btn.disabled = false;
  }

  async _doRemoveAttachment() {
    const fd = new FormData();
    this._appendPassword(fd);
    fd.append('remove_attachment', 'true');
    const resp = await fetch(`/api/wishes/${this._currentWish.id}`, { method: 'PATCH', body: fd });
    if (resp.ok) {
      const updated = await resp.json();
      this._currentWish = updated;
      _showToast('Attachment removed', 'success');
      this._renderMain(updated);
      document.querySelector('.unlock-section')?.remove();
      this._renderEditPanel();
    }
  }

  async _doFulfill() {
    const wish = this._currentWish;
    let endpoint = wish.status === 'fulfilled'
      ? `/api/wishes/${wish.id}/unfulfill`
      : `/api/wishes/${wish.id}/fulfill`;
    // Send no body — password rides in the query (proxies mangle empty bodies).
    if (this._storedPassword !== null) {
      endpoint += `?password=${encodeURIComponent(this._storedPassword)}`;
    }
    const resp = await fetch(endpoint, { method: 'POST' });
    if (resp.ok) {
      const updated = await resp.json();
      this._currentWish = updated;
      this._renderMain(updated);
      document.querySelector('.unlock-section')?.remove();
      this._renderEditPanel();
      _showToast('Updated!', 'success');
      if (window.wishGrid) window.wishGrid.init();
    } else {
      const err = await resp.json().catch(() => ({}));
      _showToast(err.detail || i18n.t('error.generic'), 'error');
    }
  }

  async _doFail() {
    if (!confirm(i18n.t('wish.confirmLetGo'))) return;
    // Send no body — password rides in the query (proxies mangle empty bodies).
    let endpoint = `/api/wishes/${this._currentWish.id}/fail`;
    if (this._storedPassword !== null) {
      endpoint += `?password=${encodeURIComponent(this._storedPassword)}`;
    }
    const resp = await fetch(endpoint, { method: 'POST' });
    if (resp.ok) {
      // The wish has left the tree for the Columbarium, so close rather than re-render.
      this._currentWish = await resp.json();
      _showToast(i18n.t('wish.letGoDone'), 'success');
      this.close();
      if (window.wishGrid) window.wishGrid.init();
    } else {
      const err = await resp.json().catch(() => ({}));
      _showToast(err.detail || i18n.t('error.generic'), 'error');
    }
  }

  async _doDelete() {
    if (!confirm(i18n.t('wish.confirmDelete'))) return;
    // Send no DELETE body — proxies strip it. Password (non-owners) goes in the query.
    let url = `/api/wishes/${this._currentWish.id}`;
    if (this._storedPassword !== null) {
      url += `?password=${encodeURIComponent(this._storedPassword)}`;
    }
    const resp = await fetch(url, { method: 'DELETE' });
    if (resp.ok) {
      _showToast('Wish deleted', 'success');
      this.close();
      if (window.wishGrid) window.wishGrid.init();
    } else {
      const err = await resp.json().catch(() => ({}));
      _showToast(err.detail || i18n.t('error.generic'), 'error');
    }
  }

}

function _esc(str) {
  return (str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Parse a backend timestamp as UTC (created_at is naive UTC, no tz suffix). */
function _ts(s) {
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(s);
  return new Date(hasTz ? s : s + 'Z').getTime();
}

