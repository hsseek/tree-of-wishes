/**
 * WishGrid — unified entry point.
 * Delegates to FireflyCanvas (tree) or ColumbariumWall (columbarium).
 * Both share a single WishPopover instance for hover preview.
 */
class WishGrid {
  constructor({ container, board, onOpen }) {
    this._popover = new WishPopover();
    this._impl = board === 'tree'
      ? new FireflyCanvas({ container, board, onOpen, popover: this._popover })
      : new ColumbariumWall({ container, board, onOpen, popover: this._popover });
  }
  async init()     { return this._impl.init(); }
  async loadMore() { return this._impl.loadMore(); }
  get wishes()     { return this._impl.wishes || []; }
}

// ─── WishPopover ──────────────────────────────────────────────────────────────

class WishPopover {
  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'wish-popover';
    document.body.appendChild(this.el);
    this._hideTimer = null;
  }

  show(wish, anchorEl) {
    clearTimeout(this._hideTimer);

    const statusMap = { active: '✦ Active', fulfilled: '✦ Fulfilled', dead: '◈ Passed' };
    const dueStr = wish.due_date ? new Date(wish.due_date + 'T00:00:00').toLocaleDateString() : '—';
    const preview = wish.text.length > 180 ? wish.text.slice(0, 180) + '…' : wish.text;

    this.el.innerHTML = `
      <div class="pop-status ${wish.status}">${statusMap[wish.status] || wish.status}</div>
      ${wish.name ? `<div class="pop-name">— ${_escHtml(wish.name)}</div>` : ''}
      <div class="pop-text">${_escHtml(preview)}</div>
      <div class="pop-meta">
        <span>Due ${dueStr}</span>
        <span>♡ ${wish.likes}</span>
        <span>👁 ${wish.views}</span>
      </div>`;

    this.el.classList.add('pop-visible');
    // Position after render so we have the element's dimensions
    requestAnimationFrame(() => this._position(anchorEl));
  }

  hide() {
    this._hideTimer = setTimeout(() => this.el.classList.remove('pop-visible'), 120);
  }

  _position(anchor) {
    const rect = anchor.getBoundingClientRect();
    const pw = this.el.offsetWidth || 290;
    const ph = this.el.offsetHeight || 120;
    const margin = 12;

    let left = rect.left + rect.width / 2 - pw / 2;
    let top  = rect.top - ph - margin;

    // Flip below if above viewport
    if (top < margin) top = rect.bottom + margin;
    // Clamp horizontally
    left = Math.max(margin, Math.min(left, window.innerWidth - pw - margin));
    // Clamp vertically (shouldn't overflow bottom, but just in case)
    top  = Math.max(margin, Math.min(top, window.innerHeight - ph - margin));

    this.el.style.left = left + 'px';
    this.el.style.top  = top  + 'px';
  }
}

// ─── FireflyCanvas (Tree) ────────────────────────────────────────────────────

class FireflyCanvas {
  constructor({ container, onOpen, popover }) {
    this.container = container;
    this.onOpen    = onOpen;
    this.popover   = popover;
    this.wishes    = [];
    this.page      = 0;
    this.hasMore   = true;
    this.loading   = false;
  }

  async init() {
    this.wishes = [];
    this.page   = 0;
    this.hasMore = true;

    // Load all pages (cap at 20 to avoid runaway loops)
    while (this.hasMore && this.page < 20) {
      await this._loadPage();
    }
    this._render();
  }

  async loadMore() {
    if (!this.hasMore || this.loading) return;
    await this._loadPage();
    this._render();
  }

  async _loadPage() {
    this.loading = true;
    try {
      const resp = await fetch(`/api/wishes?board=tree&page=${this.page}`);
      const data = await resp.json();
      this.wishes.push(...data.wishes);
      this.hasMore = data.has_more;
      this.page++;
    } catch (e) {
      console.error('FireflyCanvas fetch error:', e);
      this.hasMore = false;
    } finally {
      this.loading = false;
    }
  }

  _render() {
    const n = this.wishes.length;
    this.container.innerHTML = '';
    this.container.classList.add('firefly-canvas');

    if (n === 0) {
      this.container.innerHTML = '<div class="canvas-empty">No wishes yet. Be the first to make one.</div>';
      this.container.style.height = '60vh';
      return;
    }

    const W = this.container.offsetWidth || window.innerWidth;
    const density_coeff = 1.15; // current density; double → twice as dense, halve → half as dense
    const canvasH = Math.max(n * 30, window.innerHeight * 1.2) / density_coeff;
    this.container.style.height = canvasH + 'px';

    const positions = _scatter(n, W, canvasH, 30 / density_coeff, 40);

    const popularThreshold = _top10Threshold(this.wishes);
    const newIds = _newWishIds(this.wishes);
    this.wishes.forEach((wish, i) => {
      const { x, y } = positions[i];
      this.container.appendChild(
        this._makeFirefly(wish, x, y, wish.likes >= popularThreshold, newIds.has(wish.id))
      );
    });

    if (this.hasMore) {
      const btn = document.createElement('button');
      btn.className = 'load-more-canvas';
      btn.textContent = i18n.t('btn.loadMore');
      btn.onclick = () => this.loadMore();
      this.container.appendChild(btn);
    }
  }

  _makeFirefly(wish, x, y, isPopular = false, isNew = false) {
    const fulfilled = wish.status === 'fulfilled';

    // Compute days until expiry for dying visualization (active wishes only)
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const dueDate = wish.due_date ? new Date(wish.due_date + 'T00:00:00') : null;
    const daysLeft = dueDate ? Math.round((dueDate - today) / 86400000) : null;
    const isDying    = wish.status === 'active' && daysLeft !== null && daysLeft <= 7 && daysLeft > 1;
    const isCritical = wish.status === 'active' && daysLeft !== null && daysLeft <= 1;

    // Random animation params — all plain numbers, no string coercion tricks
    const rx          = 15 + Math.random() * 32;   // px
    const ry          = 8  + Math.random() * 22;    // px
    const durX        = 28 + Math.random() * 44;   // seconds (4× slower: was 7–18)
    const durY        = 20 + Math.random() * 36;   // seconds (4× slower: was 5–14)
    const delayX      = -(Math.random() * durX);    // negative → start at random phase
    const delayY      = -(Math.random() * durY);
    // Dying wishes flicker faster — critical 2-4s, dying 4-7s, normal 6-16s
    const flickerDur  = isCritical ? (2.0 + Math.random() * 2.0)
                      : isDying    ? (4.0 + Math.random() * 3.0)
                      :               6   + Math.random() * 10;
    const flickerDelay = -(Math.random() * flickerDur);

    const wrap = document.createElement('div');
    let wrapClass = 'ff-wrap';
    // "New" takes visual precedence over the gold "popular" glow.
    if (isNew)           wrapClass += ' ff-new';
    else if (isPopular)  wrapClass += ' ff-popular';
    if (isCritical) wrapClass += ' ff-critical';
    else if (isDying) wrapClass += ' ff-dying';
    wrap.className = wrapClass;
    // All vars must be on the same element that .ff-x/.ff-y/.ff-glyph inherit from
    wrap.style.cssText = [
      `left:${x.toFixed(1)}px`,
      `top:${y.toFixed(1)}px`,
      `--rx:${rx.toFixed(1)}px`,
      `--ry:${ry.toFixed(1)}px`,
      `--dur-x:${durX.toFixed(2)}s`,
      `--dur-y:${durY.toFixed(2)}s`,
      `--delay-x:${delayX.toFixed(2)}s`,
      `--delay-y:${delayY.toFixed(2)}s`,
      `--flicker-dur:${flickerDur.toFixed(2)}s`,
      `--flicker-delay:${flickerDelay.toFixed(2)}s`,
    ].join(';');

    const keyword = _keyword(wish.text);
    const firstName = wish.name ? wish.name.split(/\s+/)[0] : '';
    const flower = isPopular ? ['🏵️','🌺','🌼'][Math.floor(Math.random() * 3)] : '';
    const keywordStr  = keyword   ? _escHtml(keyword)    : '';
    const nameStr     = firstName ? _escHtml(firstName)  : '';
    const firstPart   = keywordStr && flower ? `${keywordStr} ${flower}` : keywordStr;
    const nameLineHtml = nameStr ? `<div class="ff-label-name">${nameStr}</div>` : '';
    const labelHtml = firstPart || nameStr
      ? `<div class="ff-label${fulfilled ? ' ff-label-fulfilled' : ''}">${firstPart}${nameLineHtml}</div>`
      : '';

    wrap.innerHTML = `
      <div class="ff-x">
        <div class="ff-y">
          <span class="ff-glyph ${fulfilled ? 'ff-fulfilled' : 'ff-active'}">✦</span>
          ${labelHtml}
        </div>
      </div>`;

    wrap.addEventListener('click', () => this.onOpen(wish));
    wrap.addEventListener('pointerenter', e => { if (e.pointerType === 'mouse') this.popover.show(wish, wrap); });
    wrap.addEventListener('pointerleave', e => { if (e.pointerType === 'mouse') this.popover.hide(); });

    return wrap;
  }
}

// ─── ColumbariumWall (Columbarium) ────────────────────────────────────────────

class ColumbariumWall {
  constructor({ container, onOpen, popover }) {
    this.container          = container;
    this.onOpen             = onOpen;
    this.popover            = popover;
    this.wishes             = [];
    this.page               = 0;
    this.hasMore            = true;
    this.loading            = false;
    this._loaded            = 0;
    this._popularThreshold  = Infinity;
  }

  async init() {
    this.wishes  = [];
    this.page    = 0;
    this.hasMore = true;
    this._loaded = 0;
    await this._loadPage();
    this._render();
  }

  async loadMore() {
    if (!this.hasMore || this.loading) return;
    const prevLen = this.wishes.length;
    await this._loadPage();

    const newThreshold = _top10Threshold(this.wishes);
    if (newThreshold !== this._popularThreshold) {
      this._popularThreshold = newThreshold;
      this.container.querySelectorAll('.niche').forEach((el, i) => {
        const w = this.wishes[i];
        if (!w) return;
        const isPopular = w.likes >= this._popularThreshold;
        el.classList.toggle('niche-popular', isPopular);
        const likesEl = el.querySelector('.niche-likes');
        if (likesEl) likesEl.textContent = (isPopular ? '💐' : '✿') + ' ' + w.likes;
      });
    }

    const lmBtn = this.container.querySelector('.load-more-niche');
    this.wishes.slice(prevLen).forEach(w => {
      this.container.insertBefore(this._makeNiche(w), lmBtn);
    });
    this._updateLoadMore();
  }

  async _loadPage() {
    this.loading = true;
    try {
      const resp = await fetch(`/api/wishes?board=columbarium&page=${this.page}`);
      const data = await resp.json();
      this.wishes.push(...data.wishes);
      this.hasMore = data.has_more;
      this.page++;
    } catch (e) {
      console.error('ColumbariumWall fetch error:', e);
      this.hasMore = false;
    } finally {
      this.loading = false;
    }
  }

  _render() {
    this._popularThreshold = _top10Threshold(this.wishes);
    this.container.innerHTML = '';
    this.container.classList.add('columbarium-wall');
    this.wishes.forEach(w => this.container.appendChild(this._makeNiche(w)));
    this._updateLoadMore();
  }

  _updateLoadMore() {
    this.container.querySelector('.load-more-niche')?.remove();
    if (this.hasMore) {
      const cell = document.createElement('div');
      cell.className = 'load-more-niche';
      const btn = document.createElement('button');
      btn.className = 'btn-load-more-niche';
      btn.textContent = i18n.t('btn.loadMore');
      btn.addEventListener('click', () => this.loadMore());
      cell.appendChild(btn);
      this.container.appendChild(cell);
    }
  }

  _makeNiche(wish) {
    // Randomise the ember animation timing per niche so they don't all pulse together
    const dur       = (3 + Math.random() * 4).toFixed(1);
    const delay     = -(Math.random() * parseFloat(dur)).toFixed(1);
    const isPopular = wish.likes >= this._popularThreshold;

    const el = document.createElement('div');
    el.className = 'niche' + (isPopular ? ' niche-popular' : '');
    el.style.setProperty('--ember-dur',   dur + 's');
    el.style.setProperty('--ember-delay', delay + 's');

    const keyword = _keyword(wish.text);
    const nameHtml = wish.name
      ? `<div class="niche-text">${_escHtml(wish.name)}</div>`
      : '';

    el.innerHTML = `
      <span class="niche-ember">◈</span>
      ${keyword ? `<div class="niche-name">${_escHtml(keyword)}</div>` : ''}
      ${nameHtml}
      <div class="niche-likes">${isPopular ? '💐' : '✿'} ${wish.likes}</div>`;

    el.addEventListener('click', () => this.onOpen(wish));
    el.addEventListener('pointerenter', e => { if (e.pointerType === 'mouse') this.popover.show(wish, el); });
    el.addEventListener('pointerleave', e => { if (e.pointerType === 'mouse') this.popover.hide(); });

    return el;
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Scatter N points in a W×H area with approximate minimum distance.
 * Falls back to best available position after 40 attempts.
 */
function _scatter(n, W, H, minDist, pad) {
  const positions = [];
  for (let i = 0; i < n; i++) {
    let best = null, bestD = -1;
    for (let attempt = 0; attempt < 40; attempt++) {
      const x = pad + Math.random() * (W - pad * 2);
      const y = pad + Math.random() * (H - pad * 2);
      let minD = Infinity;
      for (const p of positions) {
        const d = Math.hypot(p.x - x, p.y - y);
        if (d < minD) minD = d;
      }
      if (positions.length === 0 || minD >= minDist) { best = { x, y }; break; }
      if (minD > bestD) { bestD = minD; best = { x, y }; }
    }
    positions.push(best || { x: pad + Math.random() * (W - pad * 2), y: pad + Math.random() * (H - pad * 2) });
  }
  return positions;
}

function _keyword(text) {
  const stop = new Set([
    'a','an','the','and','or','but','in','on','at','to','for','of','with','by',
    'from','into','onto','about','before','after','since','until','while','again',
    'i','you','he','she','it','we','they','me','him','her','us','them',
    'my','your','his','its','our','their','this','that','these','those',
    'what','how','why','when','where','who','which',
    'is','was','are','were','be','been','being',
    'do','does','did','have','has','had',
    'get','go','come','make','let','find','fall','give','take','keep',
    'feel','help','want','need','wish','hope','like','see','know','think',
    'say','try','look','stay','live','move','start','call','ask','seem',
    'finish','become','bring','show','leave','turn','mean','means',
    'will','would','could','should','may','might','shall','can','must',
    'not','no','if','so','as','up','out','just','also','very','more',
    'than','then','there','here','some','any','all','even','only','too',
    'please','really','much','still','back','am','im',
    'one','two','three','once','ever','never','always','every','each',
    'actually','something','anything','nothing','everything','already','maybe',
    'right','good','bad','big','little','long','own','new','old',
  ]);

  // Korean postpositions/suffixes — longest first to avoid partial match
  const koSfx = [
    '이에요','예요','들이랑','한테서','으로부터','로부터',
    '이랑','에서','에게','으로','까지','부터','하고',
    '이야','이다','이고','이며','들과','들을','들은','들이',
    '이라','라고','이서','라서','이는','이면','이나','한테',
    '어요','아요','여요','이요','네요','지요','고요',
    '랑','와','과','을','를','이','가','은','는',
    '로','의','도','만','야','아','에','들',
  ];

  function stripKo(w) {
    for (const s of koSfx) {
      if (w.endsWith(s) && w.length - s.length >= 2) return w.slice(0, w.length - s.length);
    }
    return w;
  }

  const words = (text || '').replace(/[^\w가-힣ㄱ-ㆎ\s]/g, ' ').split(/\s+/).filter(Boolean);
  let best = '', bestScore = -1;

  for (const raw of words) {
    const isEn = /^[a-zA-Z]+$/.test(raw);
    const isKo = /[가-힣]/.test(raw);
    let candidate = '', score = 0;

    if (isEn) {
      if (raw.length < 3 || stop.has(raw.toLowerCase())) continue;
      candidate = raw;
      score = raw.length >= 5 ? 2 : 1;
    } else if (isKo) {
      const root = stripKo(raw);
      if (root.length < 2) continue;
      candidate = root;
      // Prefer unstripped (bare nouns) and longer roots
      score = (root === raw ? 2 : 0) + (root.length >= 3 ? 1 : 0);
    } else {
      continue;
    }

    if (score > bestScore) { bestScore = score; best = candidate; }
  }

  return best.length > 12 ? best.slice(0, 12) + '…' : best;
}

function _escHtml(str) {
  return (str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function _top10Threshold(wishes) {
  if (!wishes.length) return Infinity;
  const sorted = wishes.map(w => w.likes).sort((a, b) => b - a);
  const cutoffIdx = Math.max(1, Math.ceil(sorted.length * 0.1)) - 1;
  const threshold = sorted[cutoffIdx];
  return threshold > 0 ? threshold : Infinity;
}

/**
 * "New" wishes: created within the last 24h AND within the newest 25% of all
 * wishes (the cap keeps new ones from dominating a freshly-seeded tree).
 * Returns a Set of wish ids.
 */
function _newWishIds(wishes) {
  const ids = new Set();
  if (!wishes.length) return ids;
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;
  const young = wishes
    .filter(w => w.created_at && _utcMillis(w.created_at) >= cutoff)
    .sort((a, b) => _utcMillis(b.created_at) - _utcMillis(a.created_at));
  const cap = Math.floor(wishes.length * 0.25);
  young.slice(0, cap).forEach(w => ids.add(w.id));
  return ids;
}

/** Parse a backend timestamp as UTC. created_at is naive UTC (no tz suffix),
 *  so append 'Z' unless an explicit timezone/Z is already present. */
function _utcMillis(ts) {
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(ts);
  return new Date(hasTz ? ts : ts + 'Z').getTime();
}
