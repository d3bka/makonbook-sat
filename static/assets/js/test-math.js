
        const pageConfig = JSON.parse(document.getElementById('sat-test-config').textContent);
        const testName = pageConfig.testName;
        const moduleName = pageConfig.moduleName;
        const sectionName = pageConfig.sectionName;
        const submitUrl = pageConfig.submitUrl || '';
        const nextUrl = pageConfig.nextUrl || '';
        const isGuestMode = pageConfig.mode === 'guest';
        const submitTimeoutMs = Number(pageConfig.submitTimeoutMs || 30000);

        const questions = JSON.parse(document.getElementById('sat-test-questions').textContent);

        let currentQuestionIndex = 0;
        let timeRemaining = Number(pageConfig.timeRemaining || 0);

        let eliminateOptions = false;
        let answers = Array(questions.length).fill(null);
        let eliminatedChoices = Array.from({ length: questions.length }, () => []);
        let markedForReview = Array(questions.length).fill(false);
        let timeSpent = Array(questions.length).fill(0);

        const calculatorElement = document.getElementById('calculator');
        let calculator = null;

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
            try {
                renderMathInElement(root, {
                    delimiters: [
                        { left: "\\(", right: "\\)", display: false },
                        { left: "\\[", right: "\\]", display: true }
                    ],
                    ignoredClasses: ['katex', 'dcg-container', 'dcg-exppanel', 'dcg-grapher']
                });
            } catch (error) {
                console.error('KaTeX render failed:', error);
            }
        }

        function renderQuestionMath() {
            [
                document.getElementById('passage'),
                document.getElementById('question-text'),
                document.getElementById('answers'),
                document.getElementById('questionModal'),
                document.getElementById('reference-overlay')
            ].filter(Boolean).forEach((element) => renderMath(element));
        }

        function showCalculatorFallback() {
            const fallback = document.getElementById('calculator-fallback');
            if (fallback) fallback.style.display = 'block';
        }

        function hideCalculatorFallback() {
            const fallback = document.getElementById('calculator-fallback');
            if (fallback) fallback.style.display = 'none';
        }

        function initDesmos() {
            if (window.desmosLoadError) {
                showCalculatorFallback();
                return;
            }

            if (calculatorElement && typeof Desmos !== 'undefined' && typeof Desmos.GraphingCalculator === 'function') {
                try {
                    calculator = Desmos.GraphingCalculator(calculatorElement);
                    hideCalculatorFallback();
                } catch (error) {
                    console.error('Desmos init failed:', error);
                    showCalculatorFallback();
                }
            } else {
                showCalculatorFallback();
            }
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

        function loadProgress() {
            const key = storageKey();

            const savedAnswers = localStorage.getItem(`${key}_answers`);
            const savedEliminatedChoices = localStorage.getItem(`${key}_eliminatedChoices`);
            const savedIndex = localStorage.getItem(`${key}_currentQuestionIndex`);
            const savedTime = localStorage.getItem(`${key}_timeRemaining`);
            const savedReview = localStorage.getItem(`${key}_markedForReview`);
            const savedTimeSpent = localStorage.getItem(`${key}_timeSpent`);

            if (savedAnswers) answers = JSON.parse(savedAnswers);
            if (savedEliminatedChoices) eliminatedChoices = JSON.parse(savedEliminatedChoices);
            if (savedReview) markedForReview = JSON.parse(savedReview);
            if (savedTimeSpent) timeSpent = JSON.parse(savedTimeSpent);
            if (savedIndex) currentQuestionIndex = parseInt(savedIndex, 10);
            if (savedTime) timeRemaining = parseInt(savedTime, 10);

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
                <div class="big-container">
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
            currentQuestionIndex = index;
            const question = questions[index];

            document.getElementById('currentQuestionIndex').textContent = index + 1;
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
                        value="${answers[index] || ''}"
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
                answersContainer.innerHTML = buildMultipleChoice(question, index);

                answersContainer.querySelectorAll('.choice-input').forEach((input) => {
                    input.addEventListener('change', (event) => {
                        answers[currentQuestionIndex] = event.target.value;
                        saveProgress();
                        updateAnsweredStatus();
                    });
                });

                answersContainer.querySelectorAll('.crossing-zone').forEach((button) => {
                    button.addEventListener('click', (event) => {
                        event.preventDefault();
                        event.stopPropagation();

                        if (!eliminateOptions) return;

                        const letter = button.dataset.letter;
                        eliminate(letter, currentQuestionIndex);
                    });
                });
            }

            renderQuestionMath();
            updateNavigationButtons();

            if (isCalculatorOpen()) {
                requestAnimationFrame(() => {
                    restoreDesmosInputFocus();
                });
            }

            updateAnsweredStatus();
            saveProgress();
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
            button.classList.toggle('active-options');

            document.querySelectorAll('.crossing-zone').forEach(el => {
                el.classList.toggle('active');
            });
        }

        function eliminate(choice, index) {
            const line = document.querySelector(`.${choice}zone`);
            if (line) line.classList.toggle('active');

            if (eliminatedChoices[index].includes(choice)) {
                eliminatedChoices[index] = eliminatedChoices[index].filter(c => c !== choice);
            } else {
                eliminatedChoices[index].push(choice);
            }

            saveProgress();
        }

        function nextQuestion() {
            if (currentQuestionIndex < questions.length - 1) {
                loadQuestion(currentQuestionIndex + 1);
            }
        }

        function prevQuestion() {
            if (currentQuestionIndex > 0) {
                loadQuestion(currentQuestionIndex - 1);
            }
        }

        function markForReview() {
            markedForReview[currentQuestionIndex] = !markedForReview[currentQuestionIndex];
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

        function toggleQuestionModal() {
            const modal = document.getElementById('questionModal');
            modal.style.display = modal.style.display === 'block' ? 'none' : 'block';
        }

        function closeCalculator() {
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
                initDesmos();
            }
            requestAnimationFrame(() => {
                restoreDesmosInputFocus();
            });
        }

        function isCalculatorOpen() {
            const popup = document.getElementById('calculator-popup');
            return !!(popup && popup.style.display === 'block');
        }

        function restoreDesmosInputFocus() {
            if (!isCalculatorOpen()) return false;

            try {
                if (calculator && typeof calculator.focusFirstExpression === 'function') {
                    calculator.focusFirstExpression();
                }
            } catch (error) {
                console.warn('Desmos focus recovery via API failed:', error);
            }

            const editable = document.querySelector(
                '#calculator-popup .dcg-mq-root-block, ' +
                '#calculator-popup .dcg-mathquill-root-block, ' +
                '#calculator-popup .dcg-mq-textarea textarea, ' +
                '#calculator-popup textarea, ' +
                '#calculator-popup [contenteditable="true"]'
            );

            if (editable && typeof editable.focus === 'function') {
                editable.focus();
                if (typeof editable.click === 'function') {
                    editable.click();
                }
                return true;
            }

            return false;
        }

        function isDesmosFocused() {
            if (!isCalculatorOpen()) return false;
            const active = document.activeElement;
            if (!active) return false;

            if (active === document.body || active === document.documentElement) {
                return true;
            }

            return !!(
                active.closest('#calculator-popup') ||
                active.closest('.dcg-container')
            );
        }

        function updateTimer() {
            const minutes = Math.floor(timeRemaining / 60);
            const seconds = timeRemaining % 60;
            document.getElementById('timer').innerText = `${minutes}:${seconds < 10 ? '0' : ''}${seconds}`;

            timeSpent[currentQuestionIndex] += 1;
            saveProgress();

            if (timeRemaining <= 0) {
                finishTest(true);
            } else {
                timeRemaining--;
            }
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
                            module: moduleName
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
                                module: moduleName
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
                alert(`Failed to submit test: ${error.message}. Please try again or contact support.`);
            } finally {
                finishButton.textContent = originalText;
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
                return;
            }

            // If the calculator is open, keep keyboard control inside Desmos.
            if (isCalculatorOpen() && isDesmosFocused()) {
                restoreDesmosInputFocus();
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

        dragElement(
            document.getElementById('calculator-popup'),
            document.getElementById('calculator-header')
        );

        loadProgress();
        loadQuestion(currentQuestionIndex);
        setInterval(updateTimer, 1000);
    