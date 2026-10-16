(() => {
  const navLinks = document.querySelectorAll('.side-link');
  navLinks.forEach(link => {
    link.addEventListener('click', event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.button !== 0) return;
      const href = link.href;
      event.preventDefault();
      const paw = document.createElement('span');
      paw.className = 'click-paw';
      paw.textContent = '🐾';
      link.appendChild(paw);
      link.classList.add('paw-clicked');
      window.setTimeout(() => { window.location.href = href; }, 210);
    });
  });
  document.querySelectorAll('.metric-link, .quick-action, .welcome-action').forEach(el => {
    el.addEventListener('pointerdown', () => el.classList.add('pressed'));
    ['pointerup','pointerleave','pointercancel'].forEach(name => el.addEventListener(name, () => el.classList.remove('pressed')));
  });
})();
