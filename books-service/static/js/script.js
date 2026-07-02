document.addEventListener('DOMContentLoaded', () => {
    // Auto-dismiss flash messages after 5 seconds (skip suspension banners)
    document.querySelectorAll('.messages .alert').forEach(el => {
        setTimeout(() => {
            el.style.transition = 'opacity .4s';
            el.style.opacity = '0';
            setTimeout(() => el.remove(), 400);
        }, 5000);
    });
});
