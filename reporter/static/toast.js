/**
 * toast.js — Shared toast notification system.
 * Usage: showToast('message', 'success'|'error'|'warning'|'info', duration_ms)
 */
(function() {
  window.showToast = function(msg, type, duration) {
    type = type || 'info';
    duration = duration || 3000;
    
    const toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.textContent = msg;
    document.body.appendChild(toast);
    
    setTimeout(function() {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(12px) scale(0.96)';
      toast.style.transition = 'all 200ms ease';
      setTimeout(function() { toast.remove(); }, 200);
    }, duration);
  };
})();
