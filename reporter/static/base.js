/**
 * base.js — Shared UI utilities (theme, mobile menu, keyboard shortcuts).
 */
(function() {
  // ── Theme ────────────────────────────────────────────────────
  var themeBtn = document.getElementById('themeBtn');
  
  if (localStorage.getItem('theme') === 'dark') {
    document.documentElement.dataset.theme = 'dark';
    if (themeBtn) themeBtn.textContent = '\u2600';
  }
  
  window.toggleTheme = function() {
    var isDark = document.documentElement.dataset.theme === 'dark';
    if (isDark) {
      delete document.documentElement.dataset.theme;
      localStorage.setItem('theme', 'light');
      if (themeBtn) themeBtn.textContent = '\uD83C\uDF19';
    } else {
      document.documentElement.dataset.theme = 'dark';
      localStorage.setItem('theme', 'dark');
      if (themeBtn) themeBtn.textContent = '\u2600';
    }
  };
  
  // ── Mobile Menu ──────────────────────────────────────────────
  window.toggleMobileMenu = function() {
    var menu = document.getElementById('mobileMenu');
    if (menu) {
      menu.classList.toggle('open');
    }
  };
  
  // Close mobile menu on outside click
  document.addEventListener('click', function(e) {
    var menu = document.getElementById('mobileMenu');
    var btn = document.getElementById('hamburgerBtn');
    if (menu && menu.classList.contains('open') && btn && !btn.contains(e.target) && !menu.contains(e.target)) {
      menu.classList.remove('open');
    }
  });
  
  // ── Keyboard Shortcuts Bar ───────────────────────────────────
  var shortcutBar = document.getElementById('shortcutBar');
  if (shortcutBar) {
    setTimeout(function() {
      shortcutBar.style.display = 'flex';
    }, 500);
  }

  // ── PWA Service Worker ──────────────────────────────────────
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
      navigator.serviceWorker.register('/static/sw.js').catch(function() {});
    });
  }
})();
