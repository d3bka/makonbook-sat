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
    if (!canvas || !pen || !clear) return;
    const context = canvas.getContext('2d');
    let enabled = false;
    let drawing = false;

    const resize = () => {
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.floor(window.innerWidth * ratio);
      canvas.height = Math.floor(window.innerHeight * ratio);
      canvas.style.width = `${window.innerWidth}px`;
      canvas.style.height = `${window.innerHeight}px`;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.lineCap = 'round';
      context.lineJoin = 'round';
      context.lineWidth = 9;
      context.strokeStyle = 'rgba(250, 204, 21, .38)';
    };
    resize();
    window.addEventListener('resize', resize);

    const point = (event) => {
      const source = event.touches ? event.touches[0] : event;
      return { x: source.clientX, y: source.clientY };
    };
    const start = (event) => {
      if (!enabled) return;
      drawing = true;
      const p = point(event);
      context.beginPath();
      context.moveTo(p.x, p.y);
      event.preventDefault();
    };
    const move = (event) => {
      if (!enabled || !drawing) return;
      const p = point(event);
      context.lineTo(p.x, p.y);
      context.stroke();
      event.preventDefault();
    };
    const stop = () => { drawing = false; };
    canvas.addEventListener('pointerdown', start);
    canvas.addEventListener('pointermove', move);
    canvas.addEventListener('pointerup', stop);
    canvas.addEventListener('pointercancel', stop);

    pen.setAttribute('aria-pressed', 'false');
    pen.addEventListener('click', () => {
      enabled = !enabled;
      canvas.classList.toggle('active', enabled);
      document.body.classList.toggle('pen-mode', enabled);
      pen.classList.toggle('active', enabled);
      pen.setAttribute('aria-pressed', String(enabled));
      pen.title = enabled ? 'Turn off highlighter' : 'Turn on highlighter';
    });
    clear.addEventListener('click', () => {
      context.save();
      context.setTransform(1, 0, 0, 1, 0, 0);
      context.clearRect(0, 0, canvas.width, canvas.height);
      context.restore();
      clear.classList.add('is-cleared');
      window.setTimeout(() => clear.classList.remove('is-cleared'), 280);
    });
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
