(function () {
  'use strict';

  function fixContent(value) {
    let raw = String(value == null ? '' : value)
      .replace(/\\\$/g, '$')
      .replace(/\\n/g, '\n')
      .replace(/\\t/g, '\t');

    // Do not collapse literal double backslashes here. KaTeX uses `\\`
    // as a semantic row break inside aligned/system expressions. JSON/escapejs
    // already decodes transport escaping before this function receives text.

    const hasStructuredMarkup = /\[\[\s*(?:\/?\s*(?:U|EM)|BLANK)\s*\]\]/i.test(raw);
    if (!hasStructuredMarkup) return raw;

    // Structured-PDF inline formatting is deliberately tiny and allowlisted.
    // Escape everything first so uploaded content cannot inject arbitrary HTML,
    // then restore only the markers MakonBook itself understands.
    raw = escapeHtml(raw);
    return raw
      .replace(/\[\[\s*U\s*\]\]/gi, '<u class="sat-source-underline">')
      .replace(/\[\[\s*\/\s*U\s*\]\]/gi, '</u>')
      .replace(/\[\[\s*EM\s*\]\]/gi, '<em class="sat-source-emphasis">')
      .replace(/\[\[\s*\/\s*EM\s*\]\]/gi, '</em>')
      .replace(/\[\[\s*BLANK\s*\]\]/gi, '<span class="sat-inline-blank" aria-label="blank"></span>');
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

  function sizeQuestionVisual(img) {
    if (!img) return;
    const apply = () => {
      const width = Number(img.naturalWidth || 0);
      const height = Number(img.naturalHeight || 0);
      if (!width || !height) return;
      const ratio = width / height;
      img.dataset.visualShape = ratio >= 4.2 ? 'ultrawide' : ratio >= 1.55 ? 'wide' : 'compact';
    };
    if (img.complete) apply();
    else img.addEventListener('load', apply, { once: true });
  }

  function isWritten(core) {
    const question = core.questions[core.currentQuestionIndex] || {};
    return question.type === true || question.type === 'True' || question.written === true;
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

  function choiceContent(content) {
    const value = String(content == null ? '' : content);
    if (value.startsWith('IMAGE:')) {
      return `<img class="choice-image" src="${escapeHtml(value.slice(6))}" alt="Answer choice image">`;
    }
    return fixContent(value);
  }

  function choiceMarkup(core, letter, content) {
    const index = core.currentQuestionIndex;
    const selected = SATTestUtils.normalizeChoice(core.answers[index]) === letter;
    const eliminated = (core.eliminatedChoices[index] || []).includes(letter);
    const inputId = `math-choice-${index}-${letter}`;
    return `
      <div class="big-container${selected ? ' selected' : ''}${eliminated ? ' is-eliminated' : ''}" data-choice-letter="${letter}">
        <input class="choice-input" type="radio" id="${inputId}" name="answer" value="${letter}" ${selected ? 'checked' : ''}>
        <label class="choice-container${selected ? ' selected' : ''}" for="${inputId}">
          <span class="mark" aria-hidden="true">${letter}</span>
          <span class="choice-content">${choiceContent(content)}</span>
        </label>
        <button type="button" class="crossing-zone" data-eliminate-choice="${letter}" aria-label="${eliminated ? 'Restore' : 'Eliminate'} option ${letter}">
          <span aria-hidden="true">${eliminated ? '↩' : '×'}</span>
        </button>
      </div>`;
  }

  function paintAnswer(core) {
    if (isWritten(core)) {
      const input = document.querySelector('.written-answer-input');
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
    const graph = document.getElementById('graph-container');
    const answers = document.getElementById('answers');
    const crossing = document.querySelector('.crossing-options');

    if (passage) passage.innerHTML = fixContent(question.passage);
    if (questionText) questionText.innerHTML = fixContent(question.question);
    if (number) number.textContent = question.number || core.currentQuestionIndex + 1;
    if (graph) {
      graph.innerHTML = question.graph
        ? `<div class="graph"><img src="${escapeHtml(question.graph)}" alt="Question graph or table"></div>`
        : '';
      sizeQuestionVisual(graph.querySelector('img'));
    }

    if (isWritten(core)) {
      if (crossing) crossing.hidden = true;
      answers.innerHTML = `
        <div class="written-answer-card">
          <label for="written-answer-${core.currentQuestionIndex}">Enter your answer</label>
          <input id="written-answer-${core.currentQuestionIndex}" class="written-answer-input" type="text" inputmode="decimal" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" maxlength="120" value="${escapeHtml(core.answers[core.currentQuestionIndex] || '')}" placeholder="Examples: 3, -2.5, 1/4">
          <p>Equivalent decimals and fractions are accepted when the answer key allows them. Your response is saved automatically.</p>
        </div>`;
      answers.querySelector('.written-answer-input')?.addEventListener('input', (event) => {
        core.setTextAnswer(event.target.value);
      });
    } else {
      if (crossing) crossing.hidden = false;
      answers.innerHTML = ['A', 'B', 'C', 'D']
        .map((letter) => choiceMarkup(core, letter, question[letter.toLowerCase()]))
        .join('');
      answers.querySelectorAll('.choice-image').forEach(sizeQuestionVisual);
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

  document.addEventListener('DOMContentLoaded', () => {
    const core = new SATTestCore({
      formId: 'math-quiz-form',
      renderQuestion,
      paintAnswer,
      isWrittenQuestion: isWritten,
      beforeQuestionChange(instance) {
        window.SATMathTools?.saveState(instance.currentQuestionIndex);
      },
      afterQuestionChange(instance) {
        window.SATMathTools?.loadState(instance.currentQuestionIndex);
      },
      isToolFocused() {
        return Boolean(window.SATMathTools?.isToolFocused());
      },
      onEscape() {
        window.SATMathTools?.closeAll();
      },
      beforeUnload(instance) {
        window.SATMathTools?.saveState(instance.currentQuestionIndex);
      },
    });
    window.toggleEliminateMode = () => {
      document.body.classList.toggle('is-eliminate-mode');
      syncEliminateControls(core);
    };
    window.eliminate = (choice) => core.toggleEliminated(choice);
    window.SATTest = core;
    core.boot();
  });
})();
