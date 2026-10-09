(() => {
  const watching = document.querySelector('[data-watch-section]');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const reveal = (container) => {
    if (reducedMotion.matches) return;
    container.querySelectorAll('.taste-grid > .taste-card').forEach((card, i) => {
      card.animate([{ opacity: 0, transform: 'translateY(8px)' }, { opacity: 1, transform: 'translateY(0)' }], {
        duration: 240, delay: Math.min(i * 35, 210), easing: 'ease-out', fill: 'backwards',
      });
    });
  };
  if (watching) {
    const tabs = [...watching.querySelectorAll('[data-watch-tab]')];
    const panels = [...watching.querySelectorAll('[data-watch-panel]')];
    const activate = (tab, animate = true) => {
      tabs.forEach((item) => {
        const active = item === tab;
        item.setAttribute('aria-selected', String(active));
        item.tabIndex = active ? 0 : -1;
      });
      panels.forEach((panel) => {
        panel.hidden = panel.dataset.watchPanel !== tab.dataset.watchTab;
        if (!panel.hidden && animate) reveal(panel);
      });
    };
    if (tabs.length && panels.length) {
      panels.forEach((panel) => {
        panel.setAttribute('role', 'tabpanel');
        panel.setAttribute('aria-labelledby', `tab-${panel.dataset.watchPanel}`);
        panel.tabIndex = 0;
      });
      tabs.forEach((tab, index) => {
        tab.addEventListener('click', () => activate(tab));
        tab.addEventListener('keydown', (event) => {
          let next;
          if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
          else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
          else if (event.key === 'Home') next = 0;
          else if (event.key === 'End') next = tabs.length - 1;
          else return;
          event.preventDefault();
          activate(tabs[next]);
          tabs[next].focus();
        });
      });
      activate(tabs[0], false);
      watching.classList.add('watch-enhanced');
      watching.querySelector('.watch-switch').hidden = false;
    }
  }
  document.querySelectorAll('.taste-expand').forEach((details) => {
    details.addEventListener('toggle', () => { if (details.open) reveal(details); });
  });
})();
