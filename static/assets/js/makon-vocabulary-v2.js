(function(){
  function getCookie(name){
    const cookies = document.cookie ? document.cookie.split(';') : [];
    for(const cookie of cookies){
      const [key, ...rest] = cookie.trim().split('=');
      if(key === name) return decodeURIComponent(rest.join('='));
    }
    return '';
  }

  function initWordSearch(){
    const search = document.querySelector('[data-vocab-search]');
    if(!search) return;
    const units = Array.from(document.querySelectorAll('[data-vocab-unit]'));
    const status = document.querySelector('[data-vocab-search-status]');
    const run = () => {
      const query = search.value.trim().toLowerCase();
      let shownUnits = 0;
      units.forEach((unit) => {
        const rows = Array.from(unit.querySelectorAll('[data-vocab-word-row]'));
        let shownRows = 0;
        rows.forEach((row) => {
          const visible = !query || (row.dataset.search || '').includes(query);
          row.hidden = !visible;
          if(visible) shownRows += 1;
        });
        const unitVisible = !query || shownRows > 0 || (unit.dataset.search || '').includes(query);
        unit.hidden = !unitVisible;
        if(unitVisible){
          shownUnits += 1;
          if(query && unit.tagName === 'DETAILS') unit.open = true;
        }
      });
      if(status) status.textContent = query ? `${shownUnits} unit${shownUnits === 1 ? '' : 's'} matched.` : `${units.length} units available.`;
    };
    search.addEventListener('input', run);
    run();
  }

  function initFlashcards(){
    const deck = document.querySelector('[data-vocab-deck]');
    if(!deck) return;

    const cards = Array.from(deck.querySelectorAll('[data-flashcard]'));
    if(!cards.length) return;

    const counter = deck.querySelector('[data-deck-counter]');
    const progress = deck.querySelector('[data-deck-progress]');
    const status = deck.querySelector('[data-deck-status]');
    const feedback = deck.querySelector('[data-deck-feedback]');
    const saveState = deck.querySelector('[data-deck-save-state]');
    const markUrl = deck.dataset.markUrl;
    const embeddedCsrfToken = deck.dataset.csrfToken || '';
    const csrfToken = (embeddedCsrfToken && embeddedCsrfToken !== 'NOTPROVIDED')
      ? embeddedCsrfToken
      : (getCookie('makonbook_csrftoken_v35') || getCookie('csrftoken'));
    const controls = Array.from(deck.querySelectorAll('[data-outcome]'));
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const outcomeConfig = {
      again: { label:'Again', message:'Marked for immediate repetition.', className:'rating-again' },
      learning: { label:'Learning', message:'Kept in the learning queue.', className:'rating-learning' },
      known: { label:'Know it', message:'Strong recall recorded.', className:'rating-known' }
    };

    let index = 0;
    let transitionLocked = false;
    let pendingSaves = 0;
    let failedSaves = 0;
    const wordSaveChains = new Map();

    const setFeedback = (message, tone='neutral') => {
      if(!feedback) return;
      feedback.textContent = message;
      feedback.dataset.tone = tone;
    };

    const updateSaveState = () => {
      if(!saveState) return;
      saveState.classList.toggle('has-error', failedSaves > 0);
      saveState.classList.toggle('is-saving', pendingSaves > 0);
      if(failedSaves > 0){
        saveState.textContent = `${failedSaves} not saved`;
      }else if(pendingSaves > 0){
        saveState.textContent = pendingSaves === 1 ? 'Saving…' : `Saving ${pendingSaves}…`;
      }else{
        saveState.textContent = 'Saved';
      }
    };

    const setControlsEnabled = (enabled) => {
      controls.forEach((button) => {
        button.disabled = !enabled;
        button.setAttribute('aria-disabled', String(!enabled));
      });
      deck.classList.toggle('can-rate', enabled);
    };

    const activeCard = () => cards[index];

    const updateDeckMeta = () => {
      const active = activeCard();
      if(counter) counter.textContent = `${index + 1} / ${cards.length}`;
      if(progress) progress.style.width = `${((index + 1) / cards.length) * 100}%`;
      if(status) status.textContent = active.dataset.status || 'new';
      setControlsEnabled(active.classList.contains('flipped') && !transitionLocked);
    };

    const activateCard = (nextIndex, direction=1) => {
      index = (nextIndex + cards.length) % cards.length;
      cards.forEach((card, cardIndex) => {
        const isActive = cardIndex === index;
        card.classList.toggle('active', isActive);
        card.classList.remove('flipped', 'is-rating', 'rating-again', 'rating-learning', 'rating-known', 'is-entering-left', 'is-entering-right');
        card.setAttribute('aria-pressed', 'false');
        if(isActive){
          card.classList.add(direction < 0 ? 'is-entering-left' : 'is-entering-right');
          window.setTimeout(() => card.classList.remove('is-entering-left', 'is-entering-right'), prefersReducedMotion ? 0 : 260);
        }
      });
      deck.classList.remove('is-flipped');
      setFeedback('Flip the card, then rate your recall.');
      updateDeckMeta();
    };

    const flip = () => {
      if(transitionLocked) return;
      const active = activeCard();
      const willFlip = !active.classList.contains('flipped');
      active.classList.toggle('flipped', willFlip);
      active.setAttribute('aria-pressed', String(willFlip));
      deck.classList.toggle('is-flipped', willFlip);
      setFeedback(
        willFlip ? 'How well did you recall it? Choose 1, 2, or 3.' : 'Answer hidden. Recall it before flipping again.',
        willFlip ? 'ready' : 'neutral'
      );
      updateDeckMeta();
    };

    const move = (direction) => {
      if(transitionLocked) return;
      transitionLocked = true;
      setControlsEnabled(false);
      const current = activeCard();
      current.classList.add(direction < 0 ? 'is-leaving-right' : 'is-leaving-left');
      const delay = prefersReducedMotion ? 0 : 150;
      window.setTimeout(() => {
        current.classList.remove('is-leaving-left', 'is-leaving-right');
        activateCard(index + direction, direction);
        transitionLocked = false;
        updateDeckMeta();
      }, delay);
    };

    const postReview = async(wordId, outcome, attempt=0) => {
      if(!csrfToken){
        throw new Error('Secure session token is missing. Reload the page and try again.');
      }
      const response = await fetch(markUrl, {
        method:'POST',
        credentials:'same-origin',
        headers:{
          'Content-Type':'application/json',
          'X-CSRFToken':csrfToken,
          'X-Requested-With':'XMLHttpRequest'
        },
        body:JSON.stringify({word_id:wordId, outcome}),
        keepalive:true
      });
      let data = {};
      try{ data = await response.json(); }catch(error){ data = {}; }
      if(!response.ok || !data.ok){
        const error = new Error(data.error || 'Could not save progress.');
        error.status = response.status;
        throw error;
      }
      return data;
    };

    const queueSave = (card, outcome) => {
      const wordId = card.dataset.wordId;
      pendingSaves += 1;
      card.classList.add('is-saving');
      updateSaveState();

      const previous = wordSaveChains.get(wordId) || Promise.resolve();
      const task = previous
        .catch(() => undefined)
        .then(async() => {
          try{
            return await postReview(wordId, outcome);
          }catch(firstError){
            await new Promise((resolve) => window.setTimeout(resolve, 450));
            return postReview(wordId, outcome, 1);
          }
        })
        .then((data) => {
          card.dataset.status = data.status;
          if(card.classList.contains('save-failed')){
            failedSaves = Math.max(0, failedSaves - 1);
          }
          card.classList.remove('save-failed');
          const badge = card.querySelector('[data-card-status]');
          if(badge){
            badge.textContent = data.status;
            badge.className = `vocab-status vocab-status-${data.status}`;
            badge.setAttribute('data-card-status', '');
          }
          if(card === activeCard() && status) status.textContent = data.status;
          return data;
        })
        .catch((error) => {
          failedSaves += 1;
          card.classList.add('save-failed');
          setFeedback(error.message || 'Progress was not saved. Check your connection and rate this card again.', 'error');
          return null;
        })
        .finally(() => {
          pendingSaves = Math.max(0, pendingSaves - 1);
          card.classList.remove('is-saving');
          updateSaveState();
          if(wordSaveChains.get(wordId) === task) wordSaveChains.delete(wordId);
        });

      wordSaveChains.set(wordId, task);
    };

    const mark = (outcome, triggerButton=null) => {
      if(transitionLocked) return;
      const active = activeCard();
      if(!active.classList.contains('flipped')){
        setFeedback('Reveal the answer before rating your recall.', 'warning');
        active.classList.add('needs-flip');
        window.setTimeout(() => active.classList.remove('needs-flip'), 360);
        return;
      }

      const config = outcomeConfig[outcome];
      if(!config) return;

      transitionLocked = true;
      setControlsEnabled(false);
      active.classList.add('is-rating', config.className);
      triggerButton?.classList.add('is-pressed');
      setFeedback(config.message, outcome === 'known' ? 'success' : outcome === 'again' ? 'warning' : 'ready');
      queueSave(active, outcome);

      const delay = prefersReducedMotion ? 0 : 190;
      window.setTimeout(() => {
        triggerButton?.classList.remove('is-pressed');
        active.classList.remove('is-rating', config.className);
        activateCard(index + 1, 1);
        transitionLocked = false;
        updateDeckMeta();
      }, delay);
    };

    deck.querySelector('[data-deck-prev]')?.addEventListener('click', () => move(-1));
    deck.querySelector('[data-deck-next]')?.addEventListener('click', () => move(1));
    controls.forEach((button) => {
      button.addEventListener('click', () => mark(button.dataset.outcome, button));
    });

    cards.forEach((card) => {
      card.addEventListener('click', (event) => {
        if(event.target.closest('button,a')) return;
        flip();
      });
      card.addEventListener('keydown', (event) => {
        if(event.key === 'Enter'){
          event.preventDefault();
          flip();
        }
      });
    });

    document.addEventListener('keydown', (event) => {
      if(event.repeat) return;
      if(['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)) return;
      if(document.activeElement?.closest('button,a')) return;

      if(event.code === 'Space'){
        event.preventDefault();
        flip();
      }else if(event.key === 'ArrowLeft'){
        event.preventDefault();
        move(-1);
      }else if(event.key === 'ArrowRight'){
        event.preventDefault();
        move(1);
      }else if(event.key === '1'){
        event.preventDefault();
        mark('again', deck.querySelector('[data-mark-again]'));
      }else if(event.key === '2'){
        event.preventDefault();
        mark('learning', deck.querySelector('[data-mark-learning]'));
      }else if(event.key === '3'){
        event.preventDefault();
        mark('known', deck.querySelector('[data-mark-known]'));
      }
    });

    updateSaveState();
    activateCard(0, 1);
  }

  function initQuizBuilder(){
    const form = document.querySelector('[data-vocab-quiz-builder]');
    if(!form) return;
    const checkboxes = Array.from(form.querySelectorAll('input[name="units"]'));
    const countInput = form.querySelector('input[name="question_count"]');
    const selectedLabel = form.querySelector('[data-selected-units]');
    const availableLabel = form.querySelector('[data-available-words]');
    const submit = form.querySelector('button[type="submit"]');

    const update = () => {
      const selected = checkboxes.filter((box) => box.checked);
      const available = selected.reduce((sum, box) => sum + Number(box.dataset.wordCount || 0), 0);
      if(selectedLabel) selectedLabel.textContent = selected.length;
      if(availableLabel) availableLabel.textContent = available;
      if(countInput){
        countInput.max = Math.max(available, 1);
        if(available && Number(countInput.value) > available) countInput.value = available;
      }
      if(submit) submit.disabled = selected.length === 0 || available < 4;
    };

    checkboxes.forEach((box) => box.addEventListener('change', update));
    form.querySelector('[data-select-all]')?.addEventListener('click', () => {
      checkboxes.forEach((box) => { box.checked = true; });
      update();
    });
    form.querySelector('[data-clear-all]')?.addEventListener('click', () => {
      checkboxes.forEach((box) => { box.checked = false; });
      update();
    });
    form.addEventListener('submit', () => {
      if(submit){ submit.disabled = true; submit.textContent = 'Building quiz...'; }
    });
    update();
  }

  function initQuizTest(){
    const form = document.querySelector('[data-vocab-quiz-test]');
    if(!form) return;
    const groups = Array.from(form.querySelectorAll('[data-question-group]'));
    const answeredLabel = form.querySelector('[data-answered-count]');
    const meter = form.querySelector('[data-answer-meter]');
    const timer = form.querySelector('[data-quiz-timer]');
    const start = Date.now();

    const update = () => {
      let answered = 0;
      groups.forEach((group) => {
        const selected = group.querySelector('input[type="radio"]:checked');
        group.querySelectorAll('.vocab-choice').forEach((choice) => {
          choice.classList.toggle('selected', Boolean(choice.querySelector('input:checked')));
        });
        if(selected) answered += 1;
      });
      if(answeredLabel) answeredLabel.textContent = `${answered} / ${groups.length} answered`;
      if(meter) meter.style.width = `${groups.length ? (answered / groups.length) * 100 : 0}%`;
    };
    form.addEventListener('change', update);
    if(timer){
      window.setInterval(() => {
        const seconds = Math.floor((Date.now() - start) / 1000);
        const minutes = Math.floor(seconds / 60);
        timer.textContent = `${String(minutes).padStart(2,'0')}:${String(seconds % 60).padStart(2,'0')}`;
      },1000);
    }
    form.addEventListener('submit', (event) => {
      const unanswered = groups.filter((group) => !group.querySelector('input[type="radio"]:checked')).length;
      if(unanswered && !window.confirm(`${unanswered} questions are unanswered. Submit anyway?`)){
        event.preventDefault();
        return;
      }
      const button = form.querySelector('button[type="submit"]');
      if(button){ button.disabled = true; button.textContent = 'Checking answers...'; }
    });
    update();
  }

  initWordSearch();
  initFlashcards();
  initQuizBuilder();
  initQuizTest();
})();
