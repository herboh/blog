// All content is rendered by Hugo; this only switches between saved views.
(() => {
  const preferences = new URLSearchParams(window.location.search);
  document.querySelectorAll('[data-interest-section]').forEach(section => {
    const select = section.querySelector('[data-period-select]');
    const periods = [...section.querySelectorAll('[data-period]')];
    if (!select || !periods.length) return;
    const requested = preferences.get(section.id);
    if (periods.some(panel => panel.dataset.period === requested)) select.value = requested;
    const show = () => {
      periods.forEach(panel => { panel.hidden = panel.dataset.period !== select.value; });
    };
    section.querySelector('.interest-period-control').hidden = false;
    show();
    select.addEventListener('change', () => {
      show();
      const url = new URL(window.location.href);
      url.searchParams.set(section.id, select.value);
      window.history.replaceState(null, '', url);
    });
  });
  document.querySelectorAll('[data-sync-time]').forEach(element => {
    const date = new Date(element.dateTime);
    if (Number.isNaN(date.getTime())) return;
    const age = Date.now() - date.getTime();
    element.title = date.toLocaleString();
    // Keep the calendar date visible; don't imply a live connection.
    element.textContent = date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    if (age > 3 * 86400000) {
      const label = element.previousElementSibling;
      if (label) label.textContent = 'Showing saved history';
      const dot = element.closest('[data-interest-section]').querySelector('.source-dot');
      if (dot) { dot.classList.remove('source-dot--current'); dot.classList.add('source-dot--saved'); }
    }
  });
  document.querySelectorAll('.interest-art img').forEach(image => {
    const unavailable = () => { image.hidden = true; image.parentElement.classList.add('interest-art--empty'); };
    image.addEventListener('error', unavailable);
    if (image.complete && !image.naturalWidth) unavailable();
  });
})();
