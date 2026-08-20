(() => {
  'use strict';

  // Standalone reviewer preview does not extend template.html, so keep its
  // theme state in sync even if an older cached preview template is loaded.
  (function ensurePreviewTheme() {
    const root = document.documentElement;
    if (root.dataset.theme === 'light' || root.dataset.theme === 'dark') return;
    try {
      const saved = localStorage.getItem('sat-makon-theme');
      const mode = ['light', 'dark', 'system'].includes(saved) ? saved : 'system';
      const prefersLight = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches;
      const resolved = mode === 'system' ? (prefersLight ? 'light' : 'dark') : mode;
      root.dataset.themeMode = mode;
      root.dataset.theme = resolved;
      root.style.colorScheme = resolved;
    } catch (_) {
      root.dataset.themeMode = 'system';
      root.dataset.theme = 'light';
      root.style.colorScheme = 'light';
    }
  })();

  const app = document.querySelector('[data-preview-app]');
  if (!app) return;

  const questionsNode = document.getElementById('test-import-preview-questions');
  const sourcesNode = document.getElementById('test-import-preview-sources');
  let questions = [];
  let sourceUrls = {};
  try { questions = JSON.parse(questionsNode?.textContent || '[]'); } catch (_) {}
  try { sourceUrls = JSON.parse(sourcesNode?.textContent || '{}'); } catch (_) {}
  if (!questions.length) return;

  const els = {
    sectionTitle: document.querySelector('[data-preview-section-title]'),
    moduleLabel: document.querySelector('[data-preview-module-label]'),
    moduleSelect: document.querySelector('[data-module-select]'),
    questionNumber: document.querySelector('[data-question-number]'),
    status: document.querySelector('[data-question-status]'),
    passage: document.querySelector('[data-preview-passage]'),
    graph: document.querySelector('[data-preview-graph]'),
    question: document.querySelector('[data-preview-question]'),
    answers: document.querySelector('[data-preview-answers]'),
    currentIndex: document.querySelector('[data-current-index]'),
    total: document.querySelector('[data-total-questions]'),
    prev: document.querySelector('[data-prev]'),
    next: document.querySelector('[data-next]'),
    validation: document.querySelector('[data-validation-banner]'),
    validationTitle: document.querySelector('[data-validation-title]'),
    validationText: document.querySelector('[data-validation-text]'),
    sourcePanel: document.querySelector('[data-source-panel]'),
    sourceFrame: document.querySelector('[data-source-frame]'),
    sourceTitle: document.querySelector('[data-source-title]'),
    sourcePage: document.querySelector('[data-source-page]'),
    sourceOpen: document.querySelector('[data-source-open]'),
    sourceToggle: document.querySelector('[data-source-toggle]'),
    sourceClose: document.querySelector('[data-source-close]'),
    sourceResizer: document.querySelector('[data-source-resizer]'),
    overview: document.querySelector('[data-overview]'),
    overviewModules: document.querySelector('[data-overview-modules]'),
    answerKey: document.querySelector('[data-answer-key]'),
    answerKeyValue: document.querySelector('[data-answer-key-value]'),
    answerKeyToggle: document.querySelector('[data-answer-key-toggle]'),
    editQuestion: document.querySelector('[data-edit-question]'),
  };

  const moduleRank = {
    'english:module_1': 0,
    'english:module_2': 1,
    'math:module_1': 2,
    'math:module_2': 3,
  };
  const moduleKeys = [...new Set(questions.map(q => `${q.section}:${q.module}`))]
    .sort((a, b) => (moduleRank[a] ?? 99) - (moduleRank[b] ?? 99));

  const SOURCE_WIDTH_KEY = 'makonbook-review-preview-source-width-v2';
  const DEFAULT_SOURCE_RATIO = 0.38;

  const state = {
    moduleKey: els.moduleSelect?.value || moduleKeys[0],
    index: 0,
    selected: new Map(),
    sourceVisible: window.matchMedia('(min-width: 981px)').matches,
    answerKeyVisible: false,
    sourceWidth: null,
  };

  function questionsInModule(key = state.moduleKey) {
    const [section, module] = key.split(':');
    return questions.filter(q => q.section === section && q.module === module);
  }

  function currentList() { return questionsInModule(); }
  function currentQuestion() { return currentList()[state.index] || currentList()[0] || questions[0]; }
  function moduleNumber(module) { return module === 'module_2' ? '2' : '1'; }
  function sectionLabel(section) { return section === 'math' ? 'Section 2: Mathematics' : 'Section 1: Reading and Writing'; }
  function sourceLabel(section) { return section === 'math' ? 'Math source PDF' : 'EBRW source PDF'; }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function formatStructuredText(value) {
    return escapeHtml(value || '')
      .replace(/\[\[\s*U\s*\]\]/gi, '<u class="sat-source-underline">')
      .replace(/\[\[\s*\/\s*U\s*\]\]/gi, '</u>')
      .replace(/\[\[\s*EM\s*\]\]/gi, '<em class="sat-source-emphasis">')
      .replace(/\[\[\s*\/\s*EM\s*\]\]/gi, '</em>')
      .replace(/\[\[\s*BLANK\s*\]\]/gi, '<span class="sat-inline-blank" aria-label="blank"></span>');
  }

  function renderMath(target) {
    if (!target || typeof window.renderMathInElement !== 'function') return;
    try {
      window.renderMathInElement(target, {
        delimiters: [
          {left: '$$', right: '$$', display: true},
          {left: '\\[', right: '\\]', display: true},
          {left: '\\(', right: '\\)', display: false},
          {left: '$', right: '$', display: false},
        ],
        throwOnError: false,
      });
    } catch (_) {}
  }

  function renderRichText(target, text) {
    if (!target) return;
    target.innerHTML = formatStructuredText(text);
    target.style.whiteSpace = 'pre-wrap';
    renderMath(target);
  }

  function sizeVisual(img) {
    const apply = () => {
      const width = Number(img.naturalWidth || 0);
      const height = Number(img.naturalHeight || 0);
      if (!width || !height) return;
      const ratio = width / height;
      img.dataset.visualShape = ratio >= 4.2 ? 'ultrawide' : ratio >= 1.55 ? 'wide' : 'compact';
    };
    if (img.complete) apply();
    else img.addEventListener('load', apply, {once: true});
  }

  function imageElement(url, alt) {
    const img = document.createElement('img');
    img.src = url;
    img.alt = alt || 'Question visual';
    img.loading = 'eager';
    sizeVisual(img);
    return img;
  }

  function renderAnswers(q) {
    els.answers.innerHTML = '';
    const openResponse = q.response_type === 'open_text' || q.written;

    if (openResponse) {
      const card = document.createElement('div');
      card.className = 'sentence-answer-card';

      const label = document.createElement('label');
      label.setAttribute('for', `preview-answer-${q.id}`);
      label.textContent = 'Write your answer';
      card.appendChild(label);

      const input = document.createElement('textarea');
      input.id = `preview-answer-${q.id}`;
      input.className = 'sentence-answer-input tic-preview-open-input';
      input.rows = 5;
      input.maxLength = 4000;
      input.placeholder = 'Type your answer here…';
      input.autocomplete = 'off';
      input.spellcheck = false;
      input.value = state.selected.get(q.id) || '';
      input.addEventListener('input', () => state.selected.set(q.id, input.value));
      card.appendChild(input);

      const hint = document.createElement('div');
      hint.className = 'sentence-answer-hint';
      hint.textContent = 'Reviewer preview only. This response is not saved.';
      card.appendChild(hint);
      els.answers.appendChild(card);
      return;
    }

    const choiceImages = { A: q.image_a, B: q.image_b, C: q.image_c, D: q.image_d };
    ['A', 'B', 'C', 'D'].forEach(letter => {
      const key = letter.toLowerCase();
      const selected = state.selected.get(q.id) === letter;

      const box = document.createElement('div');
      box.className = `big-container${selected ? ' selected' : ''}`;
      box.dataset.choiceLetter = letter;

      const input = document.createElement('input');
      input.className = 'choice-input';
      input.type = 'radio';
      input.id = `preview-choice-${q.id}-${letter}`;
      input.name = `preview-answer-${q.id}`;
      input.value = letter;
      input.checked = selected;
      box.appendChild(input);

      const choice = document.createElement('label');
      choice.className = `choice-container${selected ? ' selected' : ''}`;
      choice.htmlFor = input.id;

      const mark = document.createElement('span');
      mark.className = 'mark';
      mark.setAttribute('aria-hidden', 'true');
      mark.textContent = letter;
      choice.appendChild(mark);

      const content = document.createElement('span');
      content.className = 'choice-content';
      if (choiceImages[letter]) {
        content.appendChild(imageElement(choiceImages[letter], `Choice ${letter}`));
      } else {
        renderRichText(content, q[key] || '');
      }
      choice.appendChild(content);
      box.appendChild(choice);

      const selectChoice = event => {
        if (event) event.preventDefault();
        state.selected.set(q.id, letter);
        renderAnswers(q);
      };
      box.addEventListener('click', selectChoice);
      input.addEventListener('change', selectChoice);
      els.answers.appendChild(box);
    });
  }

  function renderValidation(q) {
    const status = q.validation_status || 'ok';
    app.dataset.questionStatus = status;
    const issues = Array.isArray(q.validation_errors) ? q.validation_errors.filter(Boolean) : [];
    els.status.textContent = status === 'error' ? 'Error' : status === 'warning' ? 'Warning' : 'OK';
    els.status.className = `tic-preview-status-pill ${status}`;

    if (status === 'ok' && !issues.length) {
      els.validation.hidden = true;
      return;
    }

    els.validation.hidden = false;
    els.validation.dataset.status = status;
    els.validationTitle.textContent = status === 'error' ? 'Blocking validation error' : 'Reviewer warning';
    els.validationText.textContent = issues.join(' · ') || (
      status === 'error'
        ? 'This question has a blocking validation issue.'
        : 'Compare this question with the source PDF before approval.'
    );
  }

  let lastSourceKey = '';
  function renderSource(q, force = false) {
    const base = sourceUrls[q.section] || '';
    const page = Math.max(1, Number(q.source_page) || 1);
    els.sourcePage.textContent = String(page);
    els.sourceTitle.textContent = sourceLabel(q.section);

    if (!base) {
      els.sourceOpen.removeAttribute('href');
      if (force || lastSourceKey !== 'none') els.sourceFrame.src = 'about:blank';
      lastSourceKey = 'none';
      return;
    }

    const full = `${base}#page=${page}&zoom=page-width`;
    els.sourceOpen.href = `${base}#page=${page}`;
    const sourceKey = `${q.section}:${page}`;
    if (force || sourceKey !== lastSourceKey) {
      els.sourceFrame.src = full;
      lastSourceKey = sourceKey;
    }
  }

  function renderOverview() {
    els.overviewModules.innerHTML = '';
    moduleKeys.forEach(key => {
      const list = questionsInModule(key);
      if (!list.length) return;
      const [section, module] = key.split(':');
      const sectionEl = document.createElement('section');
      sectionEl.className = 'tic-overview-module';

      const head = document.createElement('div');
      head.className = 'tic-overview-module-head';
      head.innerHTML = `<strong>${section === 'math' ? 'Math' : 'Reading & Writing'} · Module ${moduleNumber(module)}</strong><span>${list.length} questions</span>`;
      sectionEl.appendChild(head);

      const grid = document.createElement('div');
      grid.className = 'tic-overview-grid';
      list.forEach((q, idx) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `tic-overview-q ${q.validation_status || 'ok'}`;
        if (key === state.moduleKey && idx === state.index) btn.classList.add('current');
        btn.textContent = q.number;
        btn.title = `${q.validation_status || 'ok'}${q.validation_errors?.length ? ': ' + q.validation_errors.join(' · ') : ''}`;
        btn.addEventListener('click', () => {
          state.moduleKey = key;
          state.index = idx;
          if (els.moduleSelect) els.moduleSelect.value = key;
          closeOverview();
          render();
        });
        grid.appendChild(btn);
      });
      sectionEl.appendChild(grid);
      els.overviewModules.appendChild(sectionEl);
    });
  }

  function render() {
    let list = currentList();
    if (!list.length) {
      state.moduleKey = moduleKeys[0];
      state.index = 0;
      list = currentList();
    }
    if (!list.length) return;

    state.index = Math.max(0, Math.min(state.index, list.length - 1));
    const q = list[state.index];

    document.body.classList.toggle('github-test-math', q.section === 'math');
    document.body.classList.toggle('github-test-english', q.section !== 'math');
    els.sectionTitle.textContent = sectionLabel(q.section);
    els.moduleLabel.textContent = `Module ${moduleNumber(q.module)}`;
    els.questionNumber.textContent = q.number;
    els.currentIndex.textContent = state.index + 1;
    els.total.textContent = list.length;
    els.prev.disabled = state.index <= 0;
    els.next.disabled = state.index >= list.length - 1;

    renderRichText(els.passage, q.passage || '');
    renderRichText(els.question, q.question || '');

    els.graph.innerHTML = '';
    if (q.graph) {
      const graphWrap = document.createElement('div');
      graphWrap.className = 'graph';
      graphWrap.appendChild(imageElement(q.graph, `Question ${q.number} visual`));
      els.graph.appendChild(graphWrap);
    }

    renderAnswers(q);
    renderValidation(q);
    renderSource(q);

    els.answerKey.hidden = !state.answerKeyVisible;
    els.answerKeyValue.textContent = q.answer || '—';
    if (els.editQuestion && window.TEST_IMPORT_PREVIEW?.editUrlTemplate) {
      els.editQuestion.href = window.TEST_IMPORT_PREVIEW.editUrlTemplate.replace('__QUESTION_ID__', String(q.id));
    }

    renderOverview();
  }

  function openOverview() {
    els.overview.classList.add('is-open');
    els.overview.setAttribute('aria-hidden', 'false');
  }

  function closeOverview() {
    els.overview.classList.remove('is-open');
    els.overview.setAttribute('aria-hidden', 'true');
  }

  function setSourceVisible(visible) {
    state.sourceVisible = !!visible;
    app.classList.toggle('source-hidden', !state.sourceVisible);
    els.sourceToggle?.setAttribute('aria-pressed', state.sourceVisible ? 'true' : 'false');
    if (state.sourceVisible) {
      applyStoredSourceWidth();
      renderSource(currentQuestion(), true);
    }
  }

  function sourceBounds() {
    const rect = app.getBoundingClientRect();
    const minSource = 320;
    const minTest = Math.min(760, Math.max(520, rect.width * 0.46));
    return {
      rect,
      minSource,
      maxSource: Math.max(minSource, rect.width - minTest - 12),
    };
  }

  function setSourceWidth(width, { persist = true } = {}) {
    if (window.innerWidth <= 980) return;
    const { rect, minSource, maxSource } = sourceBounds();
    const next = Math.round(Math.min(maxSource, Math.max(minSource, Number(width) || rect.width * DEFAULT_SOURCE_RATIO)));
    state.sourceWidth = next;
    app.style.setProperty('--tic-source-width', `${next}px`);
    if (els.sourceResizer) {
      const pct = Math.round((next / Math.max(1, rect.width)) * 100);
      els.sourceResizer.setAttribute('aria-valuenow', String(pct));
    }
    if (persist) {
      try { localStorage.setItem(SOURCE_WIDTH_KEY, String(next)); } catch (_) {}
    }
  }

  function applyStoredSourceWidth() {
    if (window.innerWidth <= 980) return;
    let stored = null;
    try { stored = Number(localStorage.getItem(SOURCE_WIDTH_KEY)); } catch (_) {}
    if (!Number.isFinite(stored) || stored <= 0) {
      stored = app.getBoundingClientRect().width * DEFAULT_SOURCE_RATIO;
    }
    setSourceWidth(stored, { persist: false });
  }

  function resetSourceWidth() {
    const width = app.getBoundingClientRect().width * DEFAULT_SOURCE_RATIO;
    setSourceWidth(width);
  }

  function initResizer() {
    if (!els.sourceResizer) return;
    let activePointer = null;

    els.sourceResizer.addEventListener('pointerdown', event => {
      if (window.innerWidth <= 980 || !state.sourceVisible) return;
      activePointer = event.pointerId;
      els.sourceResizer.setPointerCapture?.(event.pointerId);
      document.body.classList.add('tic-is-resizing');
      event.preventDefault();
    });

    els.sourceResizer.addEventListener('pointermove', event => {
      if (activePointer !== event.pointerId) return;
      const rect = app.getBoundingClientRect();
      setSourceWidth(rect.right - event.clientX);
    });

    const stopResize = event => {
      if (activePointer === null) return;
      if (event && activePointer !== event.pointerId) return;
      try { els.sourceResizer.releasePointerCapture?.(activePointer); } catch (_) {}
      activePointer = null;
      document.body.classList.remove('tic-is-resizing');
    };
    els.sourceResizer.addEventListener('pointerup', stopResize);
    els.sourceResizer.addEventListener('pointercancel', stopResize);
    els.sourceResizer.addEventListener('dblclick', resetSourceWidth);
    els.sourceResizer.addEventListener('keydown', event => {
      if (window.innerWidth <= 980) return;
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      event.preventDefault();
      const step = event.shiftKey ? 80 : 24;
      const current = state.sourceWidth || app.getBoundingClientRect().width * DEFAULT_SOURCE_RATIO;
      setSourceWidth(current + (event.key === 'ArrowLeft' ? step : -step));
    });
  }

  els.moduleSelect?.addEventListener('change', event => {
    state.moduleKey = event.target.value;
    state.index = 0;
    render();
  });
  els.prev?.addEventListener('click', () => {
    if (state.index > 0) {
      state.index -= 1;
      render();
    }
  });
  els.next?.addEventListener('click', () => {
    if (state.index < currentList().length - 1) {
      state.index += 1;
      render();
    }
  });
  els.sourceToggle?.addEventListener('click', () => setSourceVisible(!state.sourceVisible));
  els.sourceClose?.addEventListener('click', () => setSourceVisible(false));
  document.querySelectorAll('[data-overview-toggle]').forEach(el => el.addEventListener('click', openOverview));
  document.querySelectorAll('[data-overview-close]').forEach(el => el.addEventListener('click', closeOverview));
  els.answerKeyToggle?.addEventListener('click', () => {
    state.answerKeyVisible = !state.answerKeyVisible;
    render();
  });

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      if (els.overview.classList.contains('is-open')) closeOverview();
      else if (window.innerWidth <= 980 && state.sourceVisible) setSourceVisible(false);
    }
    if ((event.altKey || event.metaKey) && event.key === 'ArrowLeft' && state.index > 0) {
      state.index -= 1;
      render();
    }
    if ((event.altKey || event.metaKey) && event.key === 'ArrowRight' && state.index < currentList().length - 1) {
      state.index += 1;
      render();
    }
  });

  window.addEventListener('resize', () => {
    if (window.innerWidth <= 980) return;
    if (state.sourceVisible) setSourceWidth(state.sourceWidth || undefined, { persist: false });
  });

  initResizer();
  applyStoredSourceWidth();
  setSourceVisible(state.sourceVisible);
  render();
})();
