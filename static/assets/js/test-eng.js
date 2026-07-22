(function () {
  'use strict';

  function fixContent(value) {
    return String(value == null ? '' : value)
      .replace(/\\\$/g, '$')
      .replace(/\\\\/g, '\\')
      .replace(/\\n/g, '\n')
      .replace(/\\t/g, '\t');
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function renderMath(root) {
    if (!root || typeof window.renderMathInElement !== 'function') return;
    try {
      window.renderMathInElement(root, {
        delimiters: [
          { left: '\\(', right: '\\)', display: false },
          { left: '\\[', right: '\\]', display: true },
        ],
        throwOnError: false,
      });
    } catch (error) {
      console.warn('Math rendering failed:', error);
    }
  }

  function isOpenText(core) {
    const question = core.questions[core.currentQuestionIndex] || {};
    return question.response_type === 'open_text';
  }

  function syncEliminateControls(core) {
    const enabled = document.body.classList.contains('is-eliminate-mode');
    const toggle = document.querySelector('.crossing-options');
    if (toggle) {
      toggle.classList.toggle('active-options', enabled);
      toggle.setAttribute('aria-pressed', String(enabled));
    }
    const eliminated = new Set(core.eliminatedChoices[core.currentQuestionIndex] || []);
    document.querySelectorAll('#answers [data-eliminate-choice]').forEach((button) => {
      const visible = enabled || eliminated.has(button.dataset.eliminateChoice);
      button.classList.toggle('active', visible);
      button.hidden = !visible;
    });
  }

  function choiceMarkup(core, letter, content) {
    const index = core.currentQuestionIndex;
    const selected = SATTestUtils.normalizeChoice(core.answers[index]) === letter;
    const eliminated = (core.eliminatedChoices[index] || []).includes(letter);
    const inputId = `eng-choice-${index}-${letter}`;
    return `
      <div class="big-container${selected ? ' selected' : ''}${eliminated ? ' is-eliminated' : ''}" data-choice-letter="${letter}">
        <input class="choice-input" type="radio" id="${inputId}" name="answer" value="${letter}" ${selected ? 'checked' : ''}>
        <label class="choice-container${selected ? ' selected' : ''}" for="${inputId}">
          <span class="mark" aria-hidden="true">${letter}</span>
          <span class="choice-content">${fixContent(content)}</span>
        </label>
        <button type="button" class="crossing-zone" data-eliminate-choice="${letter}" aria-label="${eliminated ? 'Restore' : 'Eliminate'} option ${letter}">
          <span aria-hidden="true">${eliminated ? '↩' : '×'}</span>
        </button>
      </div>`;
  }

  function paintAnswer(core) {
    if (isOpenText(core)) {
      const input = document.querySelector('.sentence-answer-input');
      if (input && input.value !== String(core.answers[core.currentQuestionIndex] || '')) {
        input.value = String(core.answers[core.currentQuestionIndex] || '');
      }
      return;
    }
    const selected = SATTestUtils.normalizeChoice(core.answers[core.currentQuestionIndex]);
    const eliminated = new Set(core.eliminatedChoices[core.currentQuestionIndex] || []);
    document.querySelectorAll('#answers .big-container').forEach((box) => {
      const letter = box.dataset.choiceLetter;
      const isSelected = selected === letter;
      const isEliminated = eliminated.has(letter);
      box.classList.toggle('selected', isSelected);
      box.classList.toggle('is-eliminated', isEliminated);
      box.querySelector('.choice-container')?.classList.toggle('selected', isSelected);
      const radio = box.querySelector('.choice-input');
      if (radio) radio.checked = isSelected;
      const eliminateButton = box.querySelector('[data-eliminate-choice]');
      if (eliminateButton) {
        eliminateButton.setAttribute('aria-label', `${isEliminated ? 'Restore' : 'Eliminate'} option ${letter}`);
        eliminateButton.firstElementChild.textContent = isEliminated ? '↩' : '×';
      }
    });
    syncEliminateControls(core);
  }

  function renderQuestion(core, question, direction) {
    document.body.classList.remove('question-enter-next', 'question-enter-prev');
    void document.body.offsetWidth;
    document.body.classList.add(direction === 'prev' ? 'question-enter-prev' : 'question-enter-next');

    const passage = document.getElementById('passage');
    const questionText = document.getElementById('question-text');
    const number = document.querySelector('.question-number');
    const graph = document.querySelector('.just-div');
    const answers = document.getElementById('answers');
    const crossing = document.querySelector('.crossing-options');

    if (passage) passage.innerHTML = fixContent(question.passage);
    if (questionText) questionText.innerHTML = fixContent(question.question);
    if (number) number.textContent = question.number || core.currentQuestionIndex + 1;
    if (graph) {
      graph.innerHTML = question.graph
        ? `<div class="graph"><img src="${escapeHtml(question.graph)}" alt="Question graph or table"></div>`
        : '';
    }

    if (isOpenText(core)) {
      if (crossing) crossing.hidden = true;
      answers.innerHTML = `
        <div class="sentence-answer-card">
          <label for="sentence-answer-${core.currentQuestionIndex}">Write your answer</label>
          <textarea id="sentence-answer-${core.currentQuestionIndex}" class="sentence-answer-input" maxlength="4000" rows="6" spellcheck="false" autocorrect="off" autocomplete="off" autocapitalize="off" placeholder="Type your answer here…">${escapeHtml(core.answers[core.currentQuestionIndex] || '')}</textarea>
          <div class="sentence-answer-hint">Your response is saved automatically. It is checked only after the module is submitted.</div>
        </div>`;
      answers.querySelector('.sentence-answer-input')?.addEventListener('input', (event) => {
        core.setTextAnswer(event.target.value);
      });
    } else {
      if (crossing) crossing.hidden = false;
      answers.innerHTML = ['A', 'B', 'C', 'D']
        .map((letter) => choiceMarkup(core, letter, question[letter.toLowerCase()]))
        .join('');
      answers.querySelectorAll('.choice-input').forEach((input) => {
        input.addEventListener('change', () => core.selectChoice(input.value));
      });
      answers.querySelectorAll('.big-container').forEach((box) => {
        box.addEventListener('click', (event) => {
          if (event.target.closest('[data-eliminate-choice]')) return;
          core.selectChoice(box.dataset.choiceLetter);
        });
      });
      answers.querySelectorAll('[data-eliminate-choice]').forEach((button) => {
        button.addEventListener('click', (event) => {
          event.preventDefault();
          event.stopPropagation();
          core.toggleEliminated(button.dataset.eliminateChoice);
        });
      });
      paintAnswer(core);
    }
    syncEliminateControls(core);

    renderMath(passage);
    renderMath(questionText);
    renderMath(answers);
    window.setTimeout(() => document.body.classList.remove('question-enter-next', 'question-enter-prev'), 420);
  }

  function initDrawingTools() {
    const canvas = document.getElementById('drawing-canvas');
    const pen = document.getElementById('pen-button');
    const clear = document.getElementById('clear-button');
    const drawSurface = document.querySelector('#quiz-form main') || document.querySelector('main');
    if (!canvas || !pen || !clear || !drawSurface) return;

    const context = canvas.getContext('2d');
    const committedCanvas = document.createElement('canvas');
    const committedContext = committedCanvas.getContext('2d');
    const strokeCanvas = document.createElement('canvas');
    const strokeContext = strokeCanvas.getContext('2d');
    const HIGHLIGHT_ALPHA = 0.18;

    let enabled = false;
    let drawing = false;
    let moved = false;
    let activePointerId = null;
    let ratio = window.devicePixelRatio || 1;

    const clearPhysicalCanvas = (targetContext, targetCanvas) => {
      targetContext.save();
      targetContext.setTransform(1, 0, 0, 1, 0, 0);
      targetContext.clearRect(0, 0, targetCanvas.width, targetCanvas.height);
      targetContext.restore();
    };

    const render = () => {
      context.save();
      context.setTransform(1, 0, 0, 1, 0, 0);
      context.clearRect(0, 0, canvas.width, canvas.height);
      context.globalAlpha = 1;
      context.drawImage(committedCanvas, 0, 0);
      if (drawing) {
        // The current gesture is composited once at a fixed alpha. The path can
        // contain many pointer samples without becoming darker in sections.
        context.globalAlpha = HIGHLIGHT_ALPHA;
        context.drawImage(strokeCanvas, 0, 0);
      }
      context.restore();
    };

    const commitCurrentStroke = () => {
      committedContext.save();
      committedContext.setTransform(1, 0, 0, 1, 0, 0);
      committedContext.globalAlpha = HIGHLIGHT_ALPHA;
      committedContext.drawImage(strokeCanvas, 0, 0);
      committedContext.restore();
      clearPhysicalCanvas(strokeContext, strokeCanvas);
      render();
    };

    const setEnabled = (nextEnabled) => {
      enabled = Boolean(nextEnabled);
      if (drawing) {
        commitCurrentStroke();
      }
      drawing = false;
      moved = false;
      activePointerId = null;
      canvas.classList.toggle('active', enabled);
      document.body.classList.toggle('pen-mode', enabled);
      pen.classList.toggle('active', enabled);
      pen.setAttribute('aria-pressed', String(enabled));
      pen.setAttribute('aria-label', enabled ? 'Turn off highlighter' : 'Turn on highlighter');
      pen.title = enabled ? 'Turn off highlighter' : 'Turn on highlighter';
    };

    const configureStrokeContext = () => {
      strokeContext.setTransform(ratio, 0, 0, ratio, 0, 0);
      strokeContext.globalAlpha = 1;
      strokeContext.globalCompositeOperation = 'source-over';
      strokeContext.lineCap = 'round';
      strokeContext.lineJoin = 'round';
      strokeContext.lineWidth = 11;
      // Draw the gesture opaquely in its private buffer. Transparency is
      // applied only once when the complete gesture is composited.
      strokeContext.strokeStyle = '#facc15';
      strokeContext.fillStyle = '#facc15';
    };

    const resize = () => {
      const oldCommitted = document.createElement('canvas');
      oldCommitted.width = committedCanvas.width;
      oldCommitted.height = committedCanvas.height;
      if (committedCanvas.width && committedCanvas.height) {
        oldCommitted.getContext('2d').drawImage(committedCanvas, 0, 0);
      }

      ratio = window.devicePixelRatio || 1;
      const width = Math.floor(window.innerWidth * ratio);
      const height = Math.floor(window.innerHeight * ratio);

      canvas.width = width;
      canvas.height = height;
      canvas.style.width = `${window.innerWidth}px`;
      canvas.style.height = `${window.innerHeight}px`;
      committedCanvas.width = width;
      committedCanvas.height = height;
      strokeCanvas.width = width;
      strokeCanvas.height = height;

      configureStrokeContext();

      if (oldCommitted.width && oldCommitted.height) {
        committedContext.save();
        committedContext.setTransform(1, 0, 0, 1, 0, 0);
        committedContext.drawImage(oldCommitted, 0, 0, width, height);
        committedContext.restore();
      }
      render();
    };
    resize();
    window.addEventListener('resize', resize);

    const point = (event) => ({ x: event.clientX, y: event.clientY });
    const isDrawableTarget = (target) => Boolean(
      target && target.closest && target.closest('.question-container, .answers-container')
    );

    const start = (event) => {
      if (!enabled || event.button !== 0 || !isDrawableTarget(event.target)) return;
      drawing = true;
      moved = false;
      activePointerId = event.pointerId;
      clearPhysicalCanvas(strokeContext, strokeCanvas);
      configureStrokeContext();
      const p = point(event);
      strokeContext.beginPath();
      strokeContext.moveTo(p.x, p.y);
      render();
      event.preventDefault();
      event.stopPropagation();
    };

    const move = (event) => {
      if (!enabled || !drawing || event.pointerId !== activePointerId) return;
      const p = point(event);
      moved = true;
      strokeContext.lineTo(p.x, p.y);
      strokeContext.stroke();
      render();
      event.preventDefault();
      event.stopPropagation();
    };

    const stop = (event) => {
      if (!drawing || (activePointerId !== null && event.pointerId !== activePointerId)) return;
      if (!moved) {
        const p = point(event);
        strokeContext.beginPath();
        strokeContext.arc(p.x, p.y, 5.5, 0, Math.PI * 2);
        strokeContext.fill();
      }
      commitCurrentStroke();
      drawing = false;
      moved = false;
      activePointerId = null;
      if (enabled) {
        event.preventDefault();
        event.stopPropagation();
      }
    };

    drawSurface.addEventListener('pointerdown', start, { capture: true, passive: false });
    document.addEventListener('pointermove', move, { capture: true, passive: false });
    document.addEventListener('pointerup', stop, { capture: true, passive: false });
    document.addEventListener('pointercancel', stop, { capture: true, passive: false });
    drawSurface.addEventListener('click', (event) => {
      if (!enabled || !isDrawableTarget(event.target)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
    }, true);

    setEnabled(false);
    pen.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      setEnabled(!enabled);
    });

    clear.addEventListener('click', (event) => {
      event.preventDefault();
      clearPhysicalCanvas(committedContext, committedCanvas);
      clearPhysicalCanvas(strokeContext, strokeCanvas);
      drawing = false;
      moved = false;
      activePointerId = null;
      render();
      clear.classList.add('is-cleared');
      window.setTimeout(() => clear.classList.remove('is-cleared'), 280);
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && enabled) {
        event.preventDefault();
        setEnabled(false);
        pen.focus({ preventScroll: true });
      }
    });

    window.SATHighlighter = {
      disable: () => setEnabled(false),
      enable: () => setEnabled(true),
      toggle: () => setEnabled(!enabled),
      isEnabled: () => enabled,
    };
  }

  document.addEventListener('DOMContentLoaded', () => {
    const core = new SATTestCore({
      formId: 'quiz-form',
      renderQuestion,
      paintAnswer,
      isWrittenQuestion: isOpenText,
      afterBoot: initDrawingTools,
    });
    window.show_eliminate = () => {
      document.body.classList.toggle('is-eliminate-mode');
      syncEliminateControls(core);
    };
    window.eliminate = (choice) => core.toggleEliminated(choice);
    window.SATTest = core;
    core.boot();
  });
})();
