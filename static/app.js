/* ── THEME ───────────────────────────────────────────────────── */
(function () {
  var key  = 'listojo-theme';
  var root = document.documentElement;
  if (localStorage.getItem(key) === 'dark') root.classList.add('dark');

  document.addEventListener('click', function(e) {
    var btn = e.target.closest('[data-theme-toggle]');
    if (!btn) return;
    root.classList.toggle('dark');
    localStorage.setItem(key, root.classList.contains('dark') ? 'dark' : 'light');
  });
})();

/* ── BACK TO TOP — show/hide only; navigation handled by href="#page-top" ── */
(function () {
  var btn = document.getElementById('back-to-top');
  if (!btn) return;

  function onScroll() {
    var y = window.pageYOffset || document.documentElement.scrollTop || document.body.scrollTop || 0;
    if (y > 380) {
      btn.classList.add('visible');
    } else {
      btn.classList.remove('visible');
    }
  }
  window.addEventListener('scroll', onScroll, { passive: true });
})();

/* ── CARD IMAGE SLIDER ───────────────────────────────────────── */
document.addEventListener('click', function (e) {
  var btn = e.target.closest('.thumb-nav');
  if (!btn) return;
  e.preventDefault();
  e.stopPropagation();

  var wrap  = btn.closest('.listing-thumb-wrap');
  var track = wrap.querySelector('.listing-thumb-track');
  var dots  = wrap.querySelectorAll('.thumb-dot');
  var total = track.children.length;
  var cur   = parseInt(track.dataset.cur || '0', 10);

  if (btn.classList.contains('thumb-nav-prev')) {
    cur = (cur - 1 + total) % total;
  } else {
    cur = (cur + 1) % total;
  }

  track.dataset.cur = cur;
  track.style.transform = 'translateX(-' + (cur * 100) + '%)';

  dots.forEach(function (d, i) { d.classList.toggle('active', i === cur); });
});

/* ── REST OF UI ──────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', function () {

  /* Active nav link */
  try {
    var path = window.location.pathname;
    document.querySelectorAll('.primary-links a, .nav-links a').forEach(function(a) {
      var href = a.getAttribute('href');
      if (href && href !== '/' && path.startsWith(href)) a.classList.add('nav-active');
      else if (href === '/' && path === '/') a.classList.add('nav-active');
    });
  } catch(e) {}

  /* KPI counter animation */
  try {
    var kpiObserver = new IntersectionObserver(function(entries) {
      entries.forEach(function(entry) {
        if (!entry.isIntersecting) return;
        var el     = entry.target;
        var target = parseInt(el.textContent.replace(/\D/g, ''), 10);
        if (isNaN(target) || target === 0) return;
        kpiObserver.unobserve(el);
        var startTime = null;
        var duration  = 1100;
        el.textContent = '0';
        function tick(ts) {
          if (!startTime) startTime = ts;
          var p    = Math.min((ts - startTime) / duration, 1);
          var ease = 1 - Math.pow(1 - p, 3);
          el.textContent = Math.floor(ease * target);
          if (p < 1) requestAnimationFrame(tick);
          else el.textContent = target;
        }
        requestAnimationFrame(tick);
      });
    }, { threshold: 0.5 });
    document.querySelectorAll('.kpi').forEach(function(el) { kpiObserver.observe(el); });
  } catch(e) {}

  /* Scroll reveal for listing cards */
  try {
    var cards = document.querySelectorAll('.listing-card');
    cards.forEach(function(el) { el.classList.add('js-reveal'); });

    var STAGGER = 0.055; /* seconds per column — same for every row */

    var revealObserver = new IntersectionObserver(function(entries) {
      /* Collect only newly-intersecting cards this tick */
      var incoming = entries
        .filter(function(e) { return e.isIntersecting; })
        .map(function(e) { return e.target; });
      if (!incoming.length) return;

      /* Sort left-to-right so col 0 always animates first */
      incoming.sort(function(a, b) {
        return a.getBoundingClientRect().left - b.getBoundingClientRect().left;
      });

      incoming.forEach(function(el, i) {
        el.style.transitionDelay = (i * STAGGER) + 's';
        el.classList.add('visible');
        revealObserver.unobserve(el);
      });
    }, { threshold: 0.05, rootMargin: '0px 0px 60px 0px' });

    cards.forEach(function(el) { revealObserver.observe(el); });
  } catch(e) {}


});
