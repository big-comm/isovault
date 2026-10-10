lucide.createIcons();

// Search: hide cards that don't match and sections left empty
const searchInput = document.getElementById('searchInput');
if (searchInput) {
    searchInput.addEventListener('input', function () {
        const term = this.value.trim().toLowerCase();
        document.querySelectorAll('.de-section').forEach(section => {
            let visible = 0;
            section.querySelectorAll('.file-card').forEach(card => {
                const match = (card.dataset.filename || '').toLowerCase().includes(term);
                card.hidden = !match;
                if (match) visible++;
            });
            section.hidden = visible === 0;
        });
    });
}

// Copy MD5 (hash comes from a data attribute, never from inline JS)
let toastTimer;
document.querySelectorAll('.md5-copy-btn').forEach(btn => {
    btn.addEventListener('click', event => {
        event.stopPropagation();
        navigator.clipboard.writeText(btn.dataset.md5).then(() => {
            const toast = document.getElementById('toast');
            toast.classList.add('show');
            clearTimeout(toastTimer);
            toastTimer = setTimeout(() => toast.classList.remove('show'), 2000);
        });
    });
});
