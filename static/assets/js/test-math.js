
        const pageConfig = JSON.parse(document.getElementById('sat-test-config').textContent);
        const testName = pageConfig.testName;
        const moduleName = pageConfig.moduleName;
        const sectionName = pageConfig.sectionName;
        const submitUrl = pageConfig.submitUrl || '';
        const nextUrl = pageConfig.nextUrl || '';
        const isGuestMode = pageConfig.mode === 'guest';
        const classroomId = pageConfig.classroomId || null;
        const testType = pageConfig.testType || 'regular';
        const submitTimeoutMs = Number(pageConfig.submitTimeoutMs || 30000);

        const questions = JSON.parse(document.getElementById('sat-test-questions').textContent);

        let currentQuestionIndex = 0;
        const DEFAULT_TIME_REMAINING = 35 * 60;
        const configuredTimeRemaining = Number(pageConfig.timeRemaining);
        const initialTimeRemaining = Number.isFinite(configuredTimeRemaining) && configuredTimeRemaining > 0
            ? configuredTimeRemaining
            : DEFAULT_TIME_REMAINING;
        let timeRemaining = initialTimeRemaining;

        let eliminateOptions = false;
        let answers = Array(questions.length).fill(null);
        let eliminatedChoices = Array.from({ length: questions.length }, () => []);
        let markedForReview = Array(questions.length).fill(false);
        let timeSpent = Array(questions.length).fill(0);

        const calculatorElement = document.getElementById('calculator');
        let calculator = null;
        let blankDesmosState = null;
        let desmosStates = Array(questions.length).fill(null);

        function cloneDesmosState(state) {
            if (!state) return null;
            try {
                return JSON.parse(JSON.stringify(state));
            } catch (error) {
                console.warn('Unable to clone Desmos state:', error);
                return null;
            }
        }

        function isCalculatorVisible() {
            const popup = document.getElementById('calculator-popup');
            return !!(popup && popup.style.display === 'block');
        }

        function ensureDesmosExpressionPanel() {
            if (!calculator || typeof calculator.updateSettings !== 'function') return;
            try {
                calculator.updateSettings({ expressions: true, keypad: true });
            } catch (error) {
                console.warn('Unable to restore Desmos expression panel:', error);
            }
        }

        function persistDesmosStates() {
            try {
                localStorage.setItem(`${storageKey()}_desmosStates_v2`, JSON.stringify(desmosStates));
            } catch (error) {
                console.warn('Unable to persist Desmos states:', error);
            }
        }

        function saveCurrentDesmosState() {
            if (!calculator || currentQuestionIndex < 0 || currentQuestionIndex >= questions.length) return;
            try {
                desmosStates[currentQuestionIndex] = cloneDesmosState(calculator.getState());
                persistDesmosStates();
            } catch (error) {
                console.warn('Unable to save Desmos state:', error);
            }
        }

        function loadDesmosStateForQuestion(index) {
            if (!calculator) return;
            try {
                const stateToLoad = cloneDesmosState(desmosStates[index] || blankDesmosState);
                if (stateToLoad) calculator.setState(stateToLoad);
                ensureDesmosExpressionPanel();
                requestDesmosResize();
            } catch (error) {
                console.warn('Unable to load Desmos state:', error);
                ensureDesmosExpressionPanel();
                requestDesmosResize();
            }
        }

        function fixLatex(text) {

            if (!text) return '';
            let cleaned = String(text);
            cleaned = cleaned.replace(/\\\$/g, '$');
            cleaned = cleaned.replace(/\\\\/g, '\\');
            cleaned = cleaned.replace(/\\\(\s*/g, '\\(');
            cleaned = cleaned.replace(/\s*\\\)/g, '\\)');
            cleaned = cleaned.replace(/\\\[\s*/g, '\\[');
            cleaned = cleaned.replace(/\s*\\\]/g, '\\]');
            // Convert escaped newlines and tabs to actual characters
            cleaned = cleaned.replace(/\\n/g, '\n');
            cleaned = cleaned.replace(/\\t/g, '\t');
            return cleaned;
        }

        function renderMath(root = document.body) {
            // KaTeX is optional. Blocked external scripts must not block the test.
            if (typeof window.renderMathInElement !== 'function') return;
            try {
                window.renderMathInElement(root, {
                    delimiters: [
                        { left: "\\(", right: "\\)", display: false },
                        { left: "\\[", right: "\\]", display: true }
                    ],
                    throwOnError: false
                });
            } catch (error) {
                console.error('KaTeX render failed:', error);
            }
        }





        function normalizeChoice(value) {
            const choice = String(value || '').trim().toUpperCase();
            return ['A', 'B', 'C', 'D'].includes(choice) ? choice : null;
        }

        function refreshEliminationState(index = currentQuestionIndex) {
            const activeChoices = new Set((eliminatedChoices[index] || []).map(normalizeChoice).filter(Boolean));
            document.querySelectorAll('#answers .big-container').forEach((box) => {
                const input = box.querySelector('input[name="answer"]');
                const letter = normalizeChoice(box.dataset.choiceLetter || (input && input.value));
                const isEliminated = Boolean(letter && activeChoices.has(letter));
                box.classList.toggle('is-eliminated', isEliminated);
                const line = box.querySelector('.cross-line');
                if (line) line.classList.toggle('active', isEliminated);
                if (input) input.disabled = false;
            });
        }

        function paintCurrentAnswer() {
            const selected = normalizeChoice(answers[currentQuestionIndex]);
            document.querySelectorAll('#answers .big-container').forEach((box) => {
                const input = box.querySelector('input[name="answer"]');
                const letter = normalizeChoice(box.dataset.choiceLetter || (input && input.value));
                const isSelected = Boolean(selected && letter === selected);
                box.classList.toggle('selected', isSelected);
                const label = box.querySelector('.choice-container');
                if (label) label.classList.toggle('selected', isSelected);
                if (input) input.checked = isSelected;
            });
            refreshEliminationState();
        }

        function setCurrentAnswer(value) {
            const choice = normalizeChoice(value);
            if (!choice) return false;

            const eliminated = eliminatedChoices[currentQuestionIndex] || [];
            if (eliminated.includes(choice)) {
                eliminatedChoices[currentQuestionIndex] = eliminated.filter((item) => item !== choice);
            }

            answers[currentQuestionIndex] = choice;
            paintCurrentAnswer();
            animateChoiceSelection(choice);
            updateAnsweredStatus();
            saveProgress();
            return true;
        }

        function choiceFromEvent(event) {
            if (!event || !event.target || !document.getElementById('answers')) return null;
            const target = event.target;
            if (!target.closest || !target.closest('#answers')) return null;
            if (target.closest('.crossing-zone')) return null;

            const input = target.closest('input[name="answer"]');
            if (input) return normalizeChoice(input.value);

            const box = target.closest('.big-container');
            if (box) return normalizeChoice(box.dataset.choiceLetter || box.querySelector('input[name="answer"]')?.value);

            const label = target.closest('.choice-container');
            if (label) return normalizeChoice(label.dataset.choiceLetter || label.closest('.big-container')?.dataset.choiceLetter);

            return null;
        }

        function captureChoiceEvent(event) {
            const choice = choiceFromEvent(event);
            if (!choice) return;
            setCurrentAnswer(choice);
        }

        function bindAnswerChoiceEvents(container) {
            if (!container) return;

            container.onchange = captureChoiceEvent;
            container.onclick = (event) => {
                const eliminateButton = event.target.closest('.crossing-zone');
                if (eliminateButton) {
                    event.preventDefault();
                    event.stopPropagation();
                    if (!eliminateOptions) return;
                    const letter = normalizeChoice(eliminateButton.dataset.letter);
                    const index = Number(eliminateButton.dataset.index);
                    if (letter && Number.isInteger(index)) {
                        eliminate(letter, index);
                    }
                    return;
                }
                captureChoiceEvent(event);
            };
        }

        function restartMotion(element, className, timeout = 520) {
            if (!element || !className) return;
            element.classList.remove(className);
            void element.offsetWidth;
            element.classList.add(className);
            window.setTimeout(() => element.classList.remove(className), timeout);
        }

        function pulseElement(element) {
            restartMotion(element, 'is-pulsing', 360);
        }

        function triggerQuestionMotion(direction = 'next') {
            const body = document.body;
            if (!body) return;
            body.classList.remove('question-enter-next', 'question-enter-prev');
            void body.offsetWidth;
            body.classList.add(direction === 'prev' ? 'question-enter-prev' : 'question-enter-next');
            document.querySelectorAll('#answers .big-container').forEach((box, index) => {
                box.style.setProperty('--choice-index', index);
            });
            window.setTimeout(() => body.classList.remove('question-enter-next', 'question-enter-prev'), 620);
        }

        function animateChoiceSelection(choice) {
            const normalized = String(choice || '').trim().toUpperCase();
            if (!['A','B','C','D'].includes(normalized)) return;
            const box = document.querySelector(`#answers .big-container[data-choice-letter="${normalized}"]`);
            restartMotion(box, 'choice-picked', 430);
        }

        function animateElimination(choice, removed = false) {
            const normalized = String(choice || '').trim().toUpperCase();
            if (!['A','B','C','D'].includes(normalized)) return;
            const box = document.querySelector(`#answers .big-container[data-choice-letter="${normalized}"]`);
            restartMotion(box, removed ? 'choice-uneliminated' : 'choice-eliminated', 430);
        }

        function renderQuestionMath() {
            ['passage', 'question-text', 'answers', 'graph-container'].forEach((id) => {
                const node = document.getElementById(id);
                if (node) renderMath(node);
            });
        }

        function getDesmosEditableFrom(target) {
            if (!calculatorElement || !target) return null;
            const selector = 'textarea:not([disabled]), input:not([disabled]), [contenteditable="true"], .dcg-mq-editable-field';

            let node = target.nodeType === Node.ELEMENT_NODE ? target : target.parentElement;
            while (node && node !== calculatorElement) {
                if (node.matches && node.matches(selector)) return node;
                if (node.querySelector) {
                    const found = node.querySelector(selector);
                    if (found) return found;
                }
                node = node.parentElement;
            }

            return calculatorElement.querySelector(selector);
        }

        let lastDesmosPointerTarget = null;

        function repairDesmosFocusIfLost(preferredTarget = null) {
            if (!calculator || !calculatorElement || !isCalculatorVisible()) return;
            const active = document.activeElement;

            if (active && active !== document.body && active !== document.documentElement && calculatorElement.contains(active)) {
                return;
            }

            ensureDesmosExpressionPanel();

            window.setTimeout(() => {
                const editable = getDesmosEditableFrom(preferredTarget || lastDesmosPointerTarget);
                if (editable && typeof editable.focus === 'function') {
                    try {
                        editable.focus({ preventScroll: true });
                    } catch (error) {
                        editable.focus();
                    }
                }
            }, 0);
        }

        function showCalculatorFallback() {
            const fallback = document.getElementById('calculator-fallback');
            if (fallback) fallback.style.display = 'block';
        }

        function hideCalculatorFallback() {
            const fallback = document.getElementById('calculator-fallback');
            if (fallback) fallback.style.display = 'none';
        }

        let desmosScriptPromise = null;
        function loadDesmosScript() {
            if (typeof window.Desmos !== 'undefined' && typeof window.Desmos.GraphingCalculator === 'function') {
                return Promise.resolve(true);
            }
            if (desmosScriptPromise) return desmosScriptPromise;

            desmosScriptPromise = new Promise((resolve) => {
                const script = document.createElement('script');
                script.src = 'https://www.desmos.com/api/v1.10/calculator.js?apiKey=dcb31709b452b1cf9dc26972add0fda6';
                script.async = true;
                script.onload = () => resolve(true);
                script.onerror = () => {
                    window.desmosLoadError = true;
                    resolve(false);
                };
                window.setTimeout(() => {
                    if (typeof window.Desmos === 'undefined') {
                        window.desmosLoadError = true;
                        resolve(false);
                    }
                }, 7000);
                document.head.appendChild(script);
            });
            return desmosScriptPromise;
        }

        function initDesmos() {
            if (window.desmosLoadError) {
                showCalculatorFallback();
                return;
            }

            if (calculatorElement && typeof Desmos !== 'undefined' && typeof Desmos.GraphingCalculator === 'function') {
                try {
                    calculator = Desmos.GraphingCalculator(calculatorElement, { expressions: true, keypad: true });
                    blankDesmosState = cloneDesmosState(calculator.getState());
                    loadDesmosStateForQuestion(currentQuestionIndex);
                    hideCalculatorFallback();
                } catch (error) {
                    console.error('Desmos init failed:', error);
                    showCalculatorFallback();
                }
            } else {
                showCalculatorFallback();
            }
        }

        function requestDesmosResize() {
            if (!calculator || typeof calculator.resize !== 'function') return;
            window.requestAnimationFrame(() => {
                try {
                    calculator.resize();
                } catch (error) {
                    console.warn('Desmos resize failed:', error);
                }
            });
        }

        function switchDesmosQuestionState(nextQuestionIndex) {
            if (nextQuestionIndex === currentQuestionIndex) return;
            saveCurrentDesmosState();
            loadDesmosStateForQuestion(nextQuestionIndex);
        }

        function dragElement(elmnt, header) {
            let pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;

            if (!header) return;
            header.onmousedown = dragMouseDown;

            function dragMouseDown(e) {
                e = e || window.event;
                e.preventDefault();
                pos3 = e.clientX;
                pos4 = e.clientY;
                document.onmouseup = closeDragElement;
                document.onmousemove = elementDrag;
            }

            function elementDrag(e) {
                e = e || window.event;
                e.preventDefault();
                pos1 = pos3 - e.clientX;
                pos2 = pos4 - e.clientY;
                pos3 = e.clientX;
                pos4 = e.clientY;
                elmnt.style.top = (elmnt.offsetTop - pos2) + 'px';
                elmnt.style.left = (elmnt.offsetLeft - pos1) + 'px';
            }

            function closeDragElement() {
                document.onmouseup = null;
                document.onmousemove = null;
            }
        }

        function storageKey() {
            return `${pageConfig.storageScope}_${moduleName}_${sectionName}`;
        }

        function saveProgress() {
            const key = storageKey();
            localStorage.setItem(`${key}_timeSpent`, JSON.stringify(timeSpent));
            localStorage.setItem(`${key}_answers`, JSON.stringify(answers));
            localStorage.setItem(`${key}_eliminatedChoices`, JSON.stringify(eliminatedChoices));
            localStorage.setItem(`${key}_currentQuestionIndex`, String(currentQuestionIndex));
            localStorage.setItem(`${key}_timeRemaining`, String(timeRemaining));
            localStorage.setItem(`${key}_markedForReview`, JSON.stringify(markedForReview));
        }

        function parseSavedArray(raw, fallback) {
            if (!raw) return fallback;
            try {
                const parsed = JSON.parse(raw);
                return Array.isArray(parsed) && parsed.length === questions.length ? parsed : fallback;
            } catch (error) {
                console.warn('Ignoring broken saved math state:', error);
                return fallback;
            }
        }

        function clampQuestionIndex(value) {
            const parsed = parseInt(value, 10);
            const maxIndex = Math.max(questions.length - 1, 0);
            if (!Number.isFinite(parsed)) return 0;
            return Math.min(Math.max(parsed, 0), maxIndex);
        }

        function loadProgress() {
            const key = storageKey();

            const savedAnswers = localStorage.getItem(`${key}_answers`);
            const savedEliminatedChoices = localStorage.getItem(`${key}_eliminatedChoices`);
            const savedIndex = localStorage.getItem(`${key}_currentQuestionIndex`);
            const savedTime = localStorage.getItem(`${key}_timeRemaining`);
            const savedReview = localStorage.getItem(`${key}_markedForReview`);
            const savedTimeSpent = localStorage.getItem(`${key}_timeSpent`);
            const savedDesmosStates = localStorage.getItem(`${key}_desmosStates_v2`);

            answers = parseSavedArray(savedAnswers, Array(questions.length).fill(null));
            eliminatedChoices = parseSavedArray(savedEliminatedChoices, Array.from({ length: questions.length }, () => []));
            markedForReview = parseSavedArray(savedReview, Array(questions.length).fill(false));
            timeSpent = parseSavedArray(savedTimeSpent, Array(questions.length).fill(0));
            currentQuestionIndex = clampQuestionIndex(savedIndex);

            const parsedTime = parseInt(savedTime, 10);
            if (Number.isFinite(parsedTime) && parsedTime > 0) {
                timeRemaining = parsedTime;
            } else {
                timeRemaining = initialTimeRemaining;
                localStorage.removeItem(`${key}_timeRemaining`);
            }

            if (savedDesmosStates) {
                try {
                    const parsedStates = JSON.parse(savedDesmosStates);
                    if (Array.isArray(parsedStates)) {
                        desmosStates = Array.from({ length: questions.length }, (_, i) => parsedStates[i] || null);
                    }
                } catch (error) {
                    console.warn('Unable to load saved Desmos states:', error);
                }
            }

            updateAnsweredStatus();
        }

        function clearProgress() {
            const key = storageKey();
            localStorage.removeItem(`${key}_timeSpent`);
            localStorage.removeItem(`${key}_answers`);
            localStorage.removeItem(`${key}_eliminatedChoices`);
            localStorage.removeItem(`${key}_currentQuestionIndex`);
            localStorage.removeItem(`${key}_timeRemaining`);
            localStorage.removeItem(`${key}_markedForReview`);
            localStorage.removeItem(`${key}_desmosStates_v2`);
            localStorage.removeItem(`${key}_desmosStates`);
        }

        function buildMultipleChoice(question, index) {
            return `
                ${buildChoice('A', question.a, index)}
                ${buildChoice('B', question.b, index)}
                ${buildChoice('C', question.c, index)}
                ${buildChoice('D', question.d, index)}
            `;
        }

        function buildChoice(letter, content, index) {
            const checked = answers[index] === letter ? 'checked' : '';
            const isEliminated = eliminatedChoices[index].includes(letter) ? 'active' : '';
            const inputId = `answer-${index}-${letter}`;

            let renderedContent = content || '';

            if (typeof renderedContent === 'string' && renderedContent.startsWith('IMAGE:')) {
                const imageUrl = renderedContent.slice(6);
                renderedContent = `<img class="choice-image" src="${imageUrl}" alt="Choice ${letter}">`;
            } else {
                renderedContent = fixLatex(renderedContent);
            }

            return `
                <div class="big-container ${isEliminated ? 'is-eliminated' : ''}" data-choice-letter="${letter}">
                    <input
                        class="choice-input"
                        type="radio"
                        id="${inputId}"
                        name="answer"
                        value="${letter}"
                        ${checked}
                    >

                    <label class="choice-container" for="${inputId}">
                        <span class="mark" data-letter="${letter}"></span>
                        <span class="choice-content">${renderedContent}</span>
                    </label>

                    <hr class="cross-line ${letter}zone ${isEliminated}">

                    <button
                        type="button"
                        class="crossing-zone ${eliminateOptions ? 'active' : ''}"
                        data-letter="${letter}"
                        data-index="${index}"
                        aria-label="Eliminate choice ${letter}"
                    >
                        <span class="cross-label">${letter}</span>
                        <span class="cross-btn-line"></span>
                    </button>
                </div>
            `;
        }

        function loadQuestion(index) {
            if (!questions.length) {
                const questionText = document.getElementById('question-text');
                if (questionText) questionText.textContent = 'Questions did not load. Reload this module or check the test data.';
                return;
            }
            const safeIndex = clampQuestionIndex(index);
            const previousQuestionIndex = currentQuestionIndex;
            const motionDirection = safeIndex < previousQuestionIndex ? 'prev' : 'next';
            switchDesmosQuestionState(safeIndex);
            currentQuestionIndex = safeIndex;
            const question = questions[safeIndex];

            document.getElementById('currentQuestionIndex').textContent = safeIndex + 1;
            document.getElementById('totalQuestions').textContent = questions.length;
            document.querySelector('.question-number').innerText = question.number;

            document.getElementById('passage').innerHTML = fixLatex(question.passage);
            document.getElementById('question-text').innerHTML = fixLatex(question.question);

            const graphContainer = document.getElementById('graph-container');
            graphContainer.innerHTML = question.graph
                ? `<div class="graph"><img src="${question.graph}" alt="Graph" style="width:100%;"></div>`
                : '';

            const answersContainer = document.getElementById('answers');

            if (question.type === 'True') {
                answersContainer.innerHTML = `
                    <input
                        type="text"
                        id="written-answer"
                        class="written-answer-input"
                        value="${answers[safeIndex] || ''}"
                        maxlength="6"
                        inputmode="text"
                        autocomplete="off"
                        spellcheck="false"
                    >
                `;

                const writtenInput = document.getElementById('written-answer');
                if (writtenInput) {
                    writtenInput.addEventListener('input', function () {
                        let value = this.value;
                        if (value.length > 6) {
                            value = value.slice(0, 6);
                        }
                        this.value = value;
                        updateWrittenAnswer(value);
                    });

                    writtenInput.addEventListener('keydown', function (event) {
                        if (event.key === 'Enter') {
                            event.preventDefault();
                            updateWrittenAnswer(this.value);
                            nextQuestion();
                        }
                    });
                }
            } else {
                answersContainer.innerHTML = buildMultipleChoice(question, safeIndex);
                bindAnswerChoiceEvents(answersContainer);
                paintCurrentAnswer();
            }

            renderQuestionMath();
            updateNavigationButtons();
            updateAnsweredStatus();
            saveProgress();
            triggerQuestionMotion(motionDirection);
        }

        function updateNavigationButtons() {
            const backButton = document.getElementById('backButton');
            const nextButton = document.getElementById('nextButton');
            const finishButton = document.getElementById('finishButton');

            if (questions.length <= 1) {
                backButton.style.display = 'none';
                nextButton.style.display = 'none';
                finishButton.style.display = 'inline-block';
                return;
            }

            if (currentQuestionIndex === 0) {
                backButton.style.display = 'none';
                nextButton.style.display = 'inline-block';
                finishButton.style.display = 'none';
            } else if (currentQuestionIndex === questions.length - 1) {
                backButton.style.display = 'inline-block';
                nextButton.style.display = 'none';
                finishButton.style.display = 'inline-block';
            } else {
                backButton.style.display = 'inline-block';
                nextButton.style.display = 'inline-block';
                finishButton.style.display = 'none';
            }
        }

        function updateWrittenAnswer(value) {
            answers[currentQuestionIndex] = value;
            saveProgress();
            updateAnsweredStatus();
        }

        function toggleEliminateMode() {
            eliminateOptions = !eliminateOptions;
            const button = document.querySelector('.crossing-options');
            if (button) {
                button.classList.toggle('active-options', eliminateOptions);
                pulseElement(button);
            }

            document.body.classList.toggle('is-eliminate-mode', eliminateOptions);
            document.querySelectorAll('.crossing-zone').forEach(el => {
                el.classList.toggle('active', eliminateOptions);
            });
        }

        function eliminate(choice, index) {
            const safeIndex = clampQuestionIndex(index);
            const normalized = normalizeChoice(choice);
            if (!normalized) return;

            const wasEliminated = eliminatedChoices[safeIndex].includes(normalized);
            if (wasEliminated) {
                eliminatedChoices[safeIndex] = eliminatedChoices[safeIndex].filter(c => c !== normalized);
            } else {
                eliminatedChoices[safeIndex].push(normalized);
                if (answers[safeIndex] === normalized) {
                    answers[safeIndex] = null;
                }
            }

            animateElimination(normalized, wasEliminated);
            if (safeIndex === currentQuestionIndex) {
                paintCurrentAnswer();
            }
            updateAnsweredStatus();
            saveProgress();
        }

        function nextQuestion() {
            pulseElement(document.getElementById('nextButton'));
            if (currentQuestionIndex < questions.length - 1) {
                loadQuestion(currentQuestionIndex + 1);
            }
        }

        function prevQuestion() {
            pulseElement(document.getElementById('backButton'));
            if (currentQuestionIndex > 0) {
                loadQuestion(currentQuestionIndex - 1);
            }
        }

        function markForReview() {
            markedForReview[currentQuestionIndex] = !markedForReview[currentQuestionIndex];
            pulseElement(document.querySelector('.bookmark'));
            updateAnsweredStatus();
            saveProgress();
        }

        function updateAnsweredStatus() {
            const mark = document.querySelector('.bookmark');
            if (mark) {
                mark.classList.toggle('filledbook', markedForReview[currentQuestionIndex]);
            }

            const rectQuestions = document.querySelectorAll('.rect-question');
            rectQuestions.forEach((rect, index) => {
                rect.classList.toggle('here', index === currentQuestionIndex);
                rect.classList.toggle('marked', markedForReview[index]);
                rect.classList.toggle('answered', !!answers[index]);
            });
        }

        function setQuestionModalOpen(open) {
            const modal = document.getElementById('questionModal');
            if (!modal) return;
            modal.classList.toggle('is-open', Boolean(open));
            modal.style.display = open ? 'flex' : 'none';
            modal.setAttribute('aria-hidden', open ? 'false' : 'true');
            document.body.classList.toggle('question-modal-open', Boolean(open));
        }

        function openQuestionModal() {
            setQuestionModalOpen(true);
        }

        function closeQuestionModal() {
            setQuestionModalOpen(false);
        }

        function toggleQuestionModal() {
            const modal = document.getElementById('questionModal');
            const isOpen = modal && (modal.classList.contains('is-open') || modal.style.display === 'block' || modal.style.display === 'flex');
            setQuestionModalOpen(!isOpen);
        }

        window.openQuestionModal = openQuestionModal;
        window.closeQuestionModal = closeQuestionModal;
        window.toggleQuestionModal = toggleQuestionModal;

        function closeCalculator() {
            saveCurrentDesmosState();
            document.getElementById('calculator-popup').style.display = 'none';
        }

        function openReference() {
            document.getElementById('reference-overlay').classList.add('active');
        }

        function closeReference() {
            document.getElementById('reference-overlay').classList.remove('active');
        }

        function openCalculator() {
            document.getElementById('calculator-popup').style.display = 'block';
            if (!calculator) {
                loadDesmosScript().then((loaded) => {
                    if (!loaded) {
                        showCalculatorFallback();
                        return;
                    }
                    initDesmos();
                    ensureDesmosExpressionPanel();
                    requestDesmosResize();
                    repairDesmosFocusIfLost(calculatorElement);
                });
            } else {
                loadDesmosStateForQuestion(currentQuestionIndex);
                ensureDesmosExpressionPanel();
                requestDesmosResize();
                repairDesmosFocusIfLost(calculatorElement);
            }
        }

        function isDesmosFocused() {
            if (!isCalculatorVisible()) return false;
            const active = document.activeElement;
            if (!active) return false;
            return !!(
                active.closest('#calculator-popup') ||
                active.closest('.dcg-container') ||
                active.closest('[class*="dcg-"]') ||
                active === document.body ||
                active === document.documentElement
            );
        }

        function formatTime(seconds) {
            const safeSeconds = Math.max(0, Math.floor(Number(seconds) || 0));
            const minutes = Math.floor(safeSeconds / 60);
            const secs = safeSeconds % 60;
            return `${minutes}:${secs < 10 ? '0' : ''}${secs}`;
        }

        function updateTimer() {
            const timerElement = document.getElementById('timer');
            if (timerElement) timerElement.innerText = formatTime(timeRemaining);

            if (timeRemaining <= 0) {
                finishTest(true);
                return;
            }

            if (!Number.isFinite(Number(timeSpent[currentQuestionIndex]))) {
                timeSpent[currentQuestionIndex] = 0;
            }
            timeSpent[currentQuestionIndex] += 1;
            timeRemaining -= 1;
            saveProgress();
        }

        function createTimeoutSignal(timeoutMs) {
            if (typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function') {
                return AbortSignal.timeout(timeoutMs);
            }

            if (typeof AbortController === 'undefined') {
                return undefined;
            }

            const controller = new AbortController();
            setTimeout(() => controller.abort(), timeoutMs);
            return controller.signal;
        }

        async function finishTest(force = false) {
            if (window.__mathSubmitInProgress) return;
            window.__mathSubmitInProgress = true;
            saveCurrentDesmosState();
            const confirmed = force || confirm('Are you sure you want to finish the test? Make sure you are ready.');
            if (!confirmed) return;

            const finishButton = document.getElementById('finishButton');
            const originalText = finishButton.textContent;
            finishButton.textContent = 'Submitting...';
            finishButton.disabled = true;

            try {
                const form = document.getElementById('math-quiz-form');
                const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
                const answerData = answers.map((answer, index) => ({
                    questionID: questions[index] ? questions[index].id : null,
                    answer,
                    time_spent: timeSpent[index]
                }));

                if (isGuestMode) {
                    const saveResp = await fetch(form.action, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': csrfToken
                        },
                        body: JSON.stringify({
                            answers: answerData,
                            section: sectionName,
                            test: testName,
                            module: moduleName,
                            classroom_id: classroomId,
                            test_type: testType
                        })
                    });

                    if (!saveResp.ok) {
                        const errorData = await saveResp.json().catch(() => ({}));
                        throw new Error(errorData.error || `Server error: ${saveResp.status}`);
                    }

                    const submitResp = await fetch(submitUrl, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': csrfToken
                        },
                        body: JSON.stringify({
                            section: sectionName,
                            module: moduleName
                        })
                    });

                    const submitData = await submitResp.json().catch(() => ({}));
                    if (!submitResp.ok || !submitData.redirect_url) {
                        throw new Error(submitData.error || 'Failed to continue test.');
                    }

                    clearProgress();
                    window.location.href = submitData.redirect_url;
                    return;
                }

                let attempts = 0;
                const maxAttempts = 3;
                while (attempts < maxAttempts) {
                    try {
                        const response = await fetch(form.action, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRFToken': csrfToken
                            },
                            body: JSON.stringify({
                                answers: answerData,
                                section: sectionName,
                                test: testName,
                                module: moduleName,
                                classroom_id: classroomId,
                                test_type: testType
                            }),
                            signal: createTimeoutSignal(submitTimeoutMs)
                        });

                        if (response.ok) {
                            clearProgress();
                            window.location.href = nextUrl;
                            return;
                        }

                        const errorData = await response.json().catch(() => ({}));
                        throw new Error(errorData.error || `Server error: ${response.status}`);
                    } catch (error) {
                        attempts += 1;
                        if (attempts >= maxAttempts) {
                            throw error;
                        }
                        const delay = Math.pow(2, attempts - 1) * 1000;
                        await new Promise(resolve => setTimeout(resolve, delay));
                    }
                }
            } catch (error) {
                console.error('Finish test error:', error);
                const message = error && error.message ? error.message : 'Unknown error';
                if (/Invalid module order/i.test(message) && nextUrl) {
                    clearProgress();
                    window.location.href = nextUrl;
                    return;
                }
                alert(`Failed to submit test: ${message}. Please try again or contact support.`);
            } finally {
                finishButton.textContent = originalText;
                window.__mathSubmitInProgress = false;
                finishButton.disabled = false;
            }
        }

        document.getElementById('open-reference').addEventListener('click', openReference);
        document.getElementById('open-calculator').addEventListener('click', openCalculator);

        document.getElementById('reference-overlay').addEventListener('click', function (e) {
            if (e.target.id === 'reference-overlay') {
                closeReference();
            }
        });

        document.addEventListener('contextmenu', event => {
            if (isDesmosFocused()) return;
            event.preventDefault();
        });
        document.addEventListener('selectstart', event => {
            if (isDesmosFocused()) return;
            event.preventDefault();
        });

        document.addEventListener('keydown', event => {
            const target = event.target;

            // Allow Escape to always close overlays, even from Desmos
            if (event.key === 'Escape') {
                closeReference();
                closeCalculator();
                closeQuestionModal();
                return;
            }

            // Let Desmos handle ALL its own keystrokes — must be before any preventDefault
            if (isDesmosFocused()) {
                return;
            }

            const isRadioChoice =
                target &&
                target.classList &&
                target.classList.contains('choice-input');
                
            const isTypingField =
                target &&
                (
                    target.tagName === 'TEXTAREA' ||
                    target.isContentEditable ||
                    (
                        target.tagName === 'INPUT' &&
                        !target.classList.contains('choice-input')
                    )
                );
        
            if (
                event.key === 'Enter' &&
                target &&
                target.classList &&
                target.classList.contains('written-answer-input')
            ) {
                event.preventDefault();
                updateWrittenAnswer(target.value);
                nextQuestion();
                return;
            }
        
            if (event.ctrlKey && ['u', 's', 'p', 'j', 'i'].includes(event.key.toLowerCase())) {
                event.preventDefault();
                return;
            }
        
            if (event.key === 'F12') {
                event.preventDefault();
                return;
            }
        
            if (isRadioChoice) {
                if (['ArrowLeft', 'ArrowUp'].includes(event.key)) {
                    event.preventDefault();
                    prevQuestion();
                    return;
                }
            
                if (['ArrowRight', 'ArrowDown'].includes(event.key)) {
                    event.preventDefault();
                    nextQuestion();
                    return;
                }
            }
        
            if (isTypingField) {
                return;
            }
        
            if (['ArrowLeft', 'ArrowUp'].includes(event.key)) {
                event.preventDefault();
                prevQuestion();
                return;
            }
        
            if (['ArrowRight', 'ArrowDown'].includes(event.key)) {
                event.preventDefault();
                nextQuestion();
                return;
            }
        });

        window.addEventListener('beforeunload', saveCurrentDesmosState);

        const calculatorPopup = document.getElementById('calculator-popup');
        if (calculatorPopup) {
            calculatorPopup.addEventListener('click', () => {
                window.setTimeout(() => {
                    ensureDesmosExpressionPanel();
                    repairDesmosFocusIfLost(lastDesmosPointerTarget);
                }, 0);
            });
        }

        if (calculatorElement) {
            calculatorElement.addEventListener('pointerdown', (event) => {
                lastDesmosPointerTarget = event.target;
            }, true);

            calculatorElement.addEventListener('pointerup', (event) => {
                lastDesmosPointerTarget = event.target;
                window.setTimeout(() => repairDesmosFocusIfLost(event.target), 0);
            }, true);
        }

        dragElement(
            document.getElementById('calculator-popup'),
            document.getElementById('calculator-header')
        );

        if ('ResizeObserver' in window) {
            const popup = document.getElementById('calculator-popup');
            if (popup) {
                const observer = new ResizeObserver(() => requestDesmosResize());
                observer.observe(popup);
            }
        }

        closeQuestionModal();
        const modal = document.getElementById('questionModal');
        if (modal) {
            modal.addEventListener('click', (event) => {
                if (event.target === modal) closeQuestionModal();
            });
        }

        loadProgress();
        loadQuestion(currentQuestionIndex);
        const timer = document.querySelector('.timer');
        if (timer) timer.innerText = formatTime(timeRemaining);
        setInterval(updateTimer, 1000);
    