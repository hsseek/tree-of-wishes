document.addEventListener('DOMContentLoaded', async () => {
  await i18n.init();

  const select = document.getElementById('lang-select');
  if (select) {
    select.value = i18n.getLang();
    select.addEventListener('change', async () => {
      await i18n.setLang(select.value);
      document.getElementById('save-status').textContent = i18n.t('settings.saved');
      document.getElementById('save-status').style.display = '';
    });
  }

  document.getElementById('lang-toggle')?.addEventListener('click', async () => {
    const next = i18n.getLang() === 'en' ? 'ko' : 'en';
    await i18n.setLang(next);
    if (select) select.value = next;
    document.getElementById('lang-toggle').textContent = next === 'en' ? '한국어' : 'English';
  });
});
