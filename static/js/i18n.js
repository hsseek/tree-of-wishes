/**
 * i18n — minimal translation layer.
 * Translations are fetched once from /static/locales/{lang}.json and cached.
 */
const i18n = (() => {
  let _lang = 'en';
  let _translations = {};

  function detectLang() {
    const stored = localStorage.getItem('tow_lang');
    if (stored === 'en' || stored === 'ko') return stored;
    const browser = (navigator.language || '').toLowerCase();
    return browser.startsWith('ko') ? 'ko' : 'en';
  }

  async function load(lang) {
    const resp = await fetch(`/static/locales/${lang}.json`);
    if (!resp.ok) throw new Error(`Failed to load locale ${lang}`);
    return resp.json();
  }

  async function init() {
    _lang = detectLang();
    _translations = await load(_lang);
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
