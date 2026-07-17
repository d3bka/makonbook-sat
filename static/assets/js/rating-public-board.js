(function(){
  function init(){
    const input = document.querySelector('[data-rating-search]');
    if(!input) return;
    const rows = Array.from(document.querySelectorAll('[data-rating-row]'));
    const podiumCards = Array.from(document.querySelectorAll('[data-rating-podium-card]'));
    const emptyState = document.querySelector('[data-rating-empty-search]');
    const status = document.querySelector('[data-rating-search-status]');
    const podiumWrap = document.querySelector('[data-rating-podium]');

    const searchable = (el) => (el.getAttribute('data-search') || '').toLowerCase();
    const setVisible = (el, visible) => {
      el.hidden = !visible;
      el.style.display = visible ? '' : 'none';
    };

    const runFilter = () => {
      const query = input.value.trim().toLowerCase();
      let visibleCount = 0;

      rows.forEach((row) => {
        const visible = !query || searchable(row).includes(query);
        setVisible(row, visible);
        if(visible) visibleCount += 1;
      });

      podiumCards.forEach((card) => {
        const visible = !query || searchable(card).includes(query);
        setVisible(card, visible);
      });

      if(podiumWrap){
        const hasVisiblePodium = podiumCards.some((card) => !card.hidden);
        podiumWrap.hidden = query && !hasVisiblePodium;
        podiumWrap.style.display = query && !hasVisiblePodium ? 'none' : '';
      }

      if(emptyState){
        const showEmpty = visibleCount === 0;
        emptyState.hidden = !showEmpty;
        emptyState.style.display = showEmpty ? '' : 'none';
      }

      if(status){
        if(!query){
          status.textContent = `Showing all ${rows.length} ranked students.`;
        } else {
          status.textContent = visibleCount
            ? `Found ${visibleCount} student${visibleCount === 1 ? '' : 's'} for “${input.value.trim()}”.`
            : `No students match “${input.value.trim()}”.`;
        }
      }
    };

    input.addEventListener('input', runFilter);
    input.addEventListener('search', runFilter);
    runFilter();
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
