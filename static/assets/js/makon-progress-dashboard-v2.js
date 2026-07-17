(function(){
  const root = document.querySelector('[data-progress-dashboard]');
  if(!root) return;
  const search = root.querySelector('[data-progress-search]');
  const state = root.querySelector('[data-progress-state]');
  const sort = root.querySelector('[data-progress-sort]');
  const cards = Array.from(root.querySelectorAll('[data-progress-student]'));
  const empty = root.querySelector('[data-progress-empty-filter]');

  const run = () => {
    const query = (search?.value || '').trim().toLowerCase();
    const filter = state?.value || 'all';
    const sortBy = sort?.value || 'name';
    const visible = [];

    cards.forEach((card) => {
      const matchesText = !query || (card.dataset.search || '').includes(query);
      const matchesState = filter === 'all' || card.dataset.state === filter;
      const show = matchesText && matchesState;
      card.hidden = !show;
      if(show) visible.push(card);
    });

    visible.sort((a,b) => {
      if(sortBy === 'overall') return Number(b.dataset.overall || 0) - Number(a.dataset.overall || 0);
      if(sortBy === 'vocabulary') return Number(b.dataset.vocabulary || 0) - Number(a.dataset.vocabulary || 0);
      if(sortBy === 'recent') return Number(b.dataset.last || 0) - Number(a.dataset.last || 0);
      return (a.dataset.search || '').localeCompare(b.dataset.search || '');
    });
    visible.forEach((card) => card.parentElement.appendChild(card));
    empty?.classList.toggle('visible', visible.length === 0);
  };

  search?.addEventListener('input', run);
  state?.addEventListener('change', run);
  sort?.addEventListener('change', run);
  run();
})();
