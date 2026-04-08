(function () {
  'use strict';

  const PLACEHOLDER = '□';
  const INLINE_LEFT = '\\(';
  const INLINE_RIGHT = '\\)';
  const DISPLAY_LEFT = '\\[';
  const DISPLAY_RIGHT = '\\]';

  const SECTIONS = [
    {
      key: 'basic',
      label: 'Basic',
      items: [
        ['≤', '≤'], ['≥', '≥'], ['≠', '≠'], ['±', '±'], ['≈', '≈'], ['≅', '≡'],
        ['∞', '∞'], ['π', 'π'], ['°', '°'], ['′', '′'], ['″', '″'], ['√', '√'],
        ['∛', '∛'], ['∜', '∜'], ['×', '×'], ['÷', '÷'], ['·', '·'], ['…', '…'],
        ['→', '→'], ['←', '←'], ['↔', '↔'], ['↑', '↑'], ['↓', '↓'], ['↗', '↗'],
        ['↘', '↘'], ['∠', '∠'], ['△', '△'], ['⊥', '⊥'], ['∥', '∥'], ['°C', '°C'],
      ]
    },
    {
      key: 'ops',
      label: 'Operators',
      items: [
        ['=', '='], ['+', '+'], ['−', '−'], ['±', '±'], ['∓', '∓'], ['·', '·'],
        ['×', '×'], ['÷', '÷'], ['/', '/'], ['%', '%'], ['!', '!'], ['≠', '≠'],
        ['<', '<'], ['>', '>'], ['≤', '≤'], ['≥', '≥'], ['∝', '∝'], ['∼', '∼'],
        ['∈', '∈'], ['∉', '∉'], ['⊂', '⊂'], ['⊆', '⊆'], ['∪', '∪'], ['∩', '∩'],
        ['∅', '∅'], ['∴', '∴'], ['∵', '∵'], ['∀', '∀'], ['∃', '∃'], ['¬', '¬'],
      ]
    },
    {
      key: 'scripts',
      label: 'Super/Sub',
      items: [
        ['x²', '²'], ['x³', '³'], ['xⁿ', 'ⁿ'], ['xⁱ', 'ⁱ'], ['x⁺', '⁺'], ['x⁻', '⁻'],
        ['x⁼', '⁼'], ['x⁽', '⁽'], ['x⁾', '⁾'], ['⁰', '⁰'], ['¹', '¹'], ['²', '²'],
        ['³', '³'], ['⁴', '⁴'], ['⁵', '⁵'], ['⁶', '⁶'], ['⁷', '⁷'], ['⁸', '⁸'],
        ['⁹', '⁹'], ['ⁿ', 'ⁿ'], ['ⁱ', 'ⁱ'], ['⁺', '⁺'], ['⁻', '⁻'], ['⁼', '⁼'],
        ['₀', '₀'], ['₁', '₁'], ['₂', '₂'], ['₃', '₃'], ['₄', '₄'], ['₅', '₅'],
        ['₆', '₆'], ['₇', '₇'], ['₈', '₈'], ['₉', '₉'], ['ₙ', 'ₙ'], ['ᵢ', 'ᵢ'],
        ['₊', '₊'], ['₋', '₋'], ['₌', '₌'], ['₍', '₍'], ['₎', '₎'],
        ['x^□', 'x^{' + PLACEHOLDER + '}'], ['x_□', 'x_{' + PLACEHOLDER + '}'],
      ]
    },
    {
      key: 'greek',
      label: 'Greek',
      items: [
        ['α', 'α'], ['β', 'β'], ['γ', 'γ'], ['δ', 'δ'], ['Δ', 'Δ'], ['ε', 'ε'],
        ['θ', 'θ'], ['Θ', 'Θ'], ['λ', 'λ'], ['Λ', 'Λ'], ['μ', 'μ'], ['π', 'π'],
        ['Π', 'Π'], ['σ', 'σ'], ['Σ', 'Σ'], ['τ', 'τ'], ['φ', 'φ'], ['Φ', 'Φ'],
        ['ω', 'ω'], ['Ω', 'Ω'], ['η', 'η'], ['ρ', 'ρ'], ['κ', 'κ'], ['χ', 'χ'],
      ]
    },
    {
      key: 'templates',
      label: 'Templates',
      items: [
        ['Inline', INLINE_LEFT + PLACEHOLDER + INLINE_RIGHT],
        ['Display', DISPLAY_LEFT + PLACEHOLDER + DISPLAY_RIGHT],
        ['frac', '\\frac{' + PLACEHOLDER + '}{' + PLACEHOLDER + '}'],
        ['sqrt', '\\sqrt{' + PLACEHOLDER + '}'],
        ['nth√', '\\sqrt[' + PLACEHOLDER + ']{' + PLACEHOLDER + '}'],
        ['|x|', '\\left|' + PLACEHOLDER + '\\right|'],
        ['log', '\\log_{' + PLACEHOLDER + '}(' + PLACEHOLDER + ')'],
        ['ln', '\\ln(' + PLACEHOLDER + ')'],
        ['sin', '\\sin(' + PLACEHOLDER + ')'],
        ['cos', '\\cos(' + PLACEHOLDER + ')'],
        ['tan', '\\tan(' + PLACEHOLDER + ')'],
        ['lim', '\\lim_{' + PLACEHOLDER + ' \\to ' + PLACEHOLDER + '}'],
        ['vec', '\\vec{' + PLACEHOLDER + '}'],
        ['bar', '\\overline{' + PLACEHOLDER + '}'],
        ['hat', '\\hat{' + PLACEHOLDER + '}'],
        ['pmat', '\\begin{pmatrix}' + PLACEHOLDER + ' & ' + PLACEHOLDER + ' \\\\ ' + PLACEHOLDER + ' & ' + PLACEHOLDER + '\\end{pmatrix}'],
        ['bmat', '\\begin{bmatrix}' + PLACEHOLDER + ' & ' + PLACEHOLDER + ' \\\\ ' + PLACEHOLDER + ' & ' + PLACEHOLDER + '\\end{bmatrix}'],
        ['cases', '\\begin{cases}' + PLACEHOLDER + ' \\\\ ' + PLACEHOLDER + '\\end{cases}'],
      ]
    }
  ];

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function createButton(text, className, title, onClick) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = className;
    button.textContent = text;
    if (title) button.title = title;
    button.addEventListener('mousedown', function (event) {
      event.preventDefault();
    });
    button.addEventListener('click', onClick);
    return button;
  }

  function insertAtCursor(textarea, snippet) {
    const start = textarea.selectionStart || 0;
    const end = textarea.selectionEnd || 0;
    const before = textarea.value.slice(0, start);
    const after = textarea.value.slice(end);
    textarea.value = before + snippet + after;

    const firstPlaceholder = snippet.indexOf(PLACEHOLDER);
    if (firstPlaceholder !== -1) {
      const selectionStart = start + firstPlaceholder;
      textarea.focus();
      textarea.setSelectionRange(selectionStart, selectionStart + PLACEHOLDER.length);
    } else {
      const caret = start + snippet.length;
      textarea.focus();
      textarea.setSelectionRange(caret, caret);
    }

    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function replaceSelection(textarea, value) {
    const start = textarea.selectionStart || 0;
    const end = textarea.selectionEnd || 0;
    textarea.value = textarea.value.slice(0, start) + value + textarea.value.slice(end);
    const caret = start + value.length;
    textarea.focus();
    textarea.setSelectionRange(caret, caret);
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function moveToPlaceholder(textarea, backwards) {
    const value = textarea.value;
    const start = textarea.selectionStart || 0;
    const index = backwards
      ? value.lastIndexOf(PLACEHOLDER, Math.max(0, start - 1))
      : value.indexOf(PLACEHOLDER, start + (textarea.selectionEnd > start ? 0 : 1));

    if (index === -1) return false;

    textarea.focus();
    textarea.setSelectionRange(index, index + PLACEHOLDER.length);
    return true;
  }

  function currentSelection(textarea) {
    const start = textarea.selectionStart || 0;
    const end = textarea.selectionEnd || 0;
    return textarea.value.slice(start, end);
  }

  function wrapSelection(textarea, left, right) {
    const selected = currentSelection(textarea);
    if (!selected) {
      insertAtCursor(textarea, left + PLACEHOLDER + right);
      return;
    }
    replaceSelection(textarea, left + selected + right);
  }

  function renderPreview(textarea, previewBody) {
    const raw = textarea.value || '';
    if (!raw.trim()) {
      previewBody.innerHTML = '<span class="sat-editor-preview__empty">Nothing to preview yet.</span>';
      return;
    }

    previewBody.innerHTML = escapeHtml(raw).replace(/\n/g, '<br>');

    if (typeof window.renderMathInElement === 'function') {
      try {
        window.renderMathInElement(previewBody, {
          delimiters: [
            { left: '$$', right: '$$', display: true },
            { left: '\\(', right: '\\)', display: false },
            { left: '\\[', right: '\\]', display: true }
          ],
          throwOnError: false
        });
      } catch (error) {
        previewBody.insertAdjacentHTML(
          'beforeend',
          '<div class="sat-editor-preview__error">Preview render error. Check your LaTeX syntax.</div>'
        );
      }
    }
  }

  function renderSectionGrid(grid, section, textarea) {
    grid.innerHTML = '';
    section.items.forEach(function (item) {
      const label = item[0];
      const value = item[1];
      const button = createButton(label, 'sat-editor-key', 'Insert ' + label, function () {
        if (value === '__WRAP_INLINE__') {
          wrapSelection(textarea, INLINE_LEFT, INLINE_RIGHT);
          return;
        }
        if (value === '__WRAP_DISPLAY__') {
          wrapSelection(textarea, DISPLAY_LEFT, DISPLAY_RIGHT);
          return;
        }
        insertAtCursor(textarea, value);
      });
      grid.appendChild(button);
    });
  }

  function enhanceTextarea(textarea) {
    if (!textarea || textarea.dataset.satEnhanced === '1') return;
    textarea.dataset.satEnhanced = '1';

    const shell = document.createElement('div');
    shell.className = 'sat-editor-shell';

    const keyboard = document.createElement('div');
    keyboard.className = 'sat-editor-keyboard';

    const keyboardHeader = document.createElement('div');
    keyboardHeader.className = 'sat-editor-keyboard__header';

    const sectionLabel = document.createElement('div');
    sectionLabel.className = 'sat-editor-keyboard__label';

    const headerActions = document.createElement('div');
    headerActions.className = 'sat-editor-keyboard__actions';

    const wrapInlineBtn = createButton('Inline', 'sat-editor-header-btn', 'Wrap selection in inline math', function () {
      wrapSelection(textarea, INLINE_LEFT, INLINE_RIGHT);
    });

    const wrapDisplayBtn = createButton('Display', 'sat-editor-header-btn', 'Wrap selection in display math', function () {
      wrapSelection(textarea, DISPLAY_LEFT, DISPLAY_RIGHT);
    });

    const menuToggle = createButton('☰', 'sat-editor-menu-toggle', 'Keyboard sections', function () {
      keyboard.classList.toggle('is-menu-open');
    });

    headerActions.appendChild(wrapInlineBtn);
    headerActions.appendChild(wrapDisplayBtn);
    headerActions.appendChild(menuToggle);

    keyboardHeader.appendChild(sectionLabel);
    keyboardHeader.appendChild(headerActions);

    const menu = document.createElement('div');
    menu.className = 'sat-editor-sections';

    const grid = document.createElement('div');
    grid.className = 'sat-editor-grid';

    const hint = document.createElement('div');
    hint.className = 'sat-editor-hint';
    hint.innerHTML = 'Use the keyboard below for symbols. Use <code>Tab</code> to jump between placeholders ' + PLACEHOLDER + ' after inserting a template.';

    const preview = document.createElement('div');
    preview.className = 'sat-editor-preview';
    preview.innerHTML = [
      '<div class="sat-editor-preview__title">Live preview</div>',
      '<div class="sat-editor-preview__body"></div>'
    ].join('');
    const previewBody = preview.querySelector('.sat-editor-preview__body');

    let activeSection = SECTIONS[0];

    function setSection(section) {
      activeSection = section;
      sectionLabel.textContent = 'Keyboard: ' + section.label;
      menu.querySelectorAll('button[data-section-key]').forEach(function (button) {
        button.classList.toggle('is-active', button.getAttribute('data-section-key') === section.key);
      });
      renderSectionGrid(grid, section, textarea);
      keyboard.classList.remove('is-menu-open');
    }

    SECTIONS.forEach(function (section) {
      const button = createButton(section.label, 'sat-editor-section-btn', 'Open ' + section.label, function () {
        setSection(section);
      });
      button.setAttribute('data-section-key', section.key);
      menu.appendChild(button);
    });

    textarea.parentNode.insertBefore(shell, textarea);
    shell.appendChild(textarea);
    shell.appendChild(keyboard);
    keyboard.appendChild(keyboardHeader);
    keyboard.appendChild(menu);
    keyboard.appendChild(grid);
    shell.appendChild(hint);
    shell.appendChild(preview);

    setSection(activeSection);

    document.addEventListener('click', function (event) {
      if (!shell.contains(event.target)) {
        keyboard.classList.remove('is-menu-open');
      }
    });

    textarea.addEventListener('keydown', function (event) {
      if (event.key === 'Tab' && (textarea.value || '').includes(PLACEHOLDER)) {
        const moved = moveToPlaceholder(textarea, event.shiftKey);
        if (moved) {
          event.preventDefault();
        }
      }
    });

    let previewTimer = null;
    const queuePreview = function () {
      window.clearTimeout(previewTimer);
      previewTimer = window.setTimeout(function () {
        renderPreview(textarea, previewBody);
      }, 90);
    };

    textarea.addEventListener('input', queuePreview);
    textarea.addEventListener('change', queuePreview);
    renderPreview(textarea, previewBody);
  }

  function init() {
    document.querySelectorAll('textarea[data-sat-editor="1"]').forEach(enhanceTextarea);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
