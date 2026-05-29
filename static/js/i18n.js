/**
 * i18n — minimal translation layer.
 * On first load, uses server-inlined translations (no fetch, no flash).
 * On language toggle, fetches the new locale and sets a cookie for the next server render.
 */
const i18n = (() => {
  let _lang = 'en';
  let _translations = {};

  function detectLang() {
    // Logged-in users: prefer server-side preference so it follows them across devices
    if (typeof TOW_USER_LANG !== 'undefined' && TOW_USER_LANG) return TOW_USER_LANG;
    const stored = localStorage.getItem('tow_lang');
    if (stored === 'en' || stored === 'ko') return stored;
    const browser = (navigator.language || '').toLowerCase();
    return browser.startsWith('ko') ? 'ko' : 'en';
  }

  async function load(lang) {
    const v = typeof TOW_SV !== 'undefined' ? `?v=${TOW_SV}` : '';
    const resp = await fetch(`/static/locales/${lang}.json${v}`);
    if (!resp.ok) throw new Error(`Failed to load locale ${lang}`);
    return resp.json();
  }

  async function init() {
    // Use server-inlined translations if available — no fetch, no flash
    if (window.TOW_TRANSLATIONS && window.TOW_LANG) {
      _lang = window.TOW_LANG;
      _translations = window.TOW_TRANSLATIONS;
    } else {
      _lang = detectLang();
      _translations = await load(_lang);
    }
    document.documentElement.lang = _lang;
    applyToDOM();
  }

  function applyToDOM() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      if (_translations[key] !== undefined) el.textContent = _translations[key];
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const key = el.getAttribute('data-i18n-placeholder');
      if (_translations[key] !== undefined) el.placeholder = _translations[key];
    });
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
      const key = el.getAttribute('data-i18n-title');
      if (_translations[key] !== undefined) el.title = _translations[key];
    });
  }

  function t(key, fallback) {
    return _translations[key] ?? fallback ?? key;
  }

  async function setLang(lang) {
    // Persist to cookie so the server inlines the correct locale on next page load
    document.cookie = `tow_lang=${lang}; path=/; max-age=31536000; SameSite=Lax`;
    localStorage.setItem('tow_lang', lang);
    _lang = lang;
    _translations = await load(lang);
    document.documentElement.lang = lang;
    applyToDOM();
    document.dispatchEvent(new CustomEvent('langchange', { detail: { lang } }));
  }

  function getLang() { return _lang; }

  return { init, t, setLang, getLang };
})();
