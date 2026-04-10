(function () {
  const key = 'listojo-theme';
  const root = document.documentElement;
  const saved = localStorage.getItem(key);
  if (saved === 'dark') root.classList.add('dark');

  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-theme-toggle]');
    if (!btn) return;
    root.classList.toggle('dark');
    localStorage.setItem(key, root.classList.contains('dark') ? 'dark' : 'light');
  });
})();
