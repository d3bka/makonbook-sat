
        const pageConfig = JSON.parse(document.getElementById('sat-test-config').textContent);
        const questions = JSON.parse(document.getElementById('sat-test-questions').textContent);

        let currentQuestionIndex = 0;
        let eliminate_options = false;
        let answers = Array(questions.length).fill(null);
        let eliminatedChoices = Array(questions.length).fill().map(() => []);
        let markedForReview = Array(questions.length).fill(false);
        const initialTimeRemaining = Math.max(Number(pageConfig.timeRemaining || 0), 1);
        let timeRemaining = initialTimeRemaining;
        let timeSpent = Array(questions.length).fill(0);

        const testName = pageConfig.testName;
        const moduleName = pageConfig.moduleName;
        const sectionName = pageConfig.sectionName;
        const isGuestMode = pageConfig.mode === 'guest';
        const classroomId = pageConfig.classroomId || null;
        const testType = pageConfig.testType || 'regular';
        const submitUrl = pageConfig.submitUrl || '';
        const nextUrl = pageConfig.nextUrl || '';
        const submitTimeoutMs = Number(pageConfig.submitTimeoutMs || 30000);

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
            // KaTeX is optional. Do not let blocked CDN/resources delay or break the test.
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

        function setQuestionModalOpen(open) {
            const modal = document.getElementById("questionModal");
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
            const modal = document.getElementById("questionModal");
            const isOpen = modal && (modal.classList.contains('is-open') || modal.style.display === 'block' || modal.style.display === 'flex');
            setQuestionModalOpen(!isOpen);
        }

        window.openQuestionModal = openQuestionModal;
        window.closeQuestionModal = closeQuestionModal;
        window.toggleQuestionModal = toggleQuestionModal;

        function updateQuestionProgress() {
            document.getElementById("currentQuestionIndex").textContent = currentQuestionIndex + 1;
            document.getElementById("totalQuestions").textContent = questions.length;
            updateNavigationButtons();
        }

        function updateNavigationButtons() {
            if (currentQuestionIndex == 0) {
                document.getElementById("backButton").style.display = "none";
                document.getElementById("finishButton").style.display = "none";
                document.getElementById("nextButton").style.display = "inline-block";
            } else if (currentQuestionIndex == questions.length - 1) {
                document.getElementById("backButton").style.display = "inline-block";
                document.getElementById("finishButton").style.display = "inline-block";
                document.getElementById("nextButton").style.display = "none";
            } else {
                document.getElementById("backButton").style.display = "inline-block";
                document.getElementById("nextButton").style.display = "inline-block";
                document.getElementById("finishButton").style.display = "none";
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
                console.warn('Ignoring broken saved test state:', error);
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

            timeSpent = parseSavedArray(savedTimeSpent, Array(questions.length).fill(0));
            answers = parseSavedArray(savedAnswers, Array(questions.length).fill(null));
            eliminatedChoices = parseSavedArray(savedEliminatedChoices, Array(questions.length).fill().map(() => []));
            markedForReview = parseSavedArray(savedReview, Array(questions.length).fill(false));
            currentQuestionIndex = clampQuestionIndex(savedIndex);

            const parsedTime = parseInt(savedTime, 10);
            if (Number.isFinite(parsedTime) && parsedTime > 0) {
                timeRemaining = parsedTime;
            } else {
                timeRemaining = initialTimeRemaining;
                localStorage.removeItem(`${key}_timeRemaining`);
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

        function syncCurrentAnswerFromDom() {
            const checkedInput = document.querySelector('#answers input[name="answer"]:checked');
            if (checkedInput && setCurrentAnswer(checkedInput.value)) {
                return true;
            }

            const selectedBox = document.querySelector('#answers .big-container.selected, #answers .choice-container.selected');
            const letter = selectedBox && normalizeChoice(selectedBox.dataset.choiceLetter || selectedBox.closest('.big-container')?.dataset.choiceLetter);
            if (letter) {
                return setCurrentAnswer(letter);
            }
            return false;
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

        window.SATAnswerDebug = function () {
            const checkedInput = document.querySelector('#answers input[name="answer"]:checked');
            return {
                currentQuestionIndex,
                currentQuestionNumber: questions[currentQuestionIndex] ? questions[currentQuestionIndex].number : null,
                currentAnswer: answers[currentQuestionIndex],
                checkedInDom: checkedInput ? checkedInput.value : null,
                answers: answers.slice(),
                storageKey: storageKey(),
                savedAnswers: localStorage.getItem(`${storageKey()}_answers`)
            };
        };
        window.setCurrentAnswer = setCurrentAnswer;
        window.syncCurrentAnswerFromDom = syncCurrentAnswerFromDom;


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
            const normalized = normalizeChoice(choice);
            if (!normalized) return;
            const box = document.querySelector(`#answers .big-container[data-choice-letter="${normalized}"]`);
            restartMotion(box, 'choice-picked', 430);
        }

        function animateElimination(choice, removed = false) {
            const normalized = normalizeChoice(choice);
            if (!normalized) return;
            const box = document.querySelector(`#answers .big-container[data-choice-letter="${normalized}"]`);
            restartMotion(box, removed ? 'choice-uneliminated' : 'choice-eliminated', 430);
        }

        function loadQuestion(index) {
            if (!questions.length) {
                const questionText = document.getElementById('question-text');
                if (questionText) questionText.textContent = 'Questions did not load. Reload this module or check the test data.';
                return;
            }
            const nextIndex = clampQuestionIndex(index);
            const previousQuestionIndex = currentQuestionIndex;
            const motionDirection = nextIndex < previousQuestionIndex ? 'prev' : 'next';

            if (nextIndex !== currentQuestionIndex) {
                syncCurrentAnswerFromDom();
            }

            currentQuestionIndex = nextIndex;
            const question = questions[currentQuestionIndex];
            updateQuestionProgress();
                
            // ✅ PASSAGE (без KaTeX, с переносами)
            document.getElementById('passage').innerHTML = fixLatex(question.passage);
                
            document.getElementsByClassName('question-number')[0].innerHTML = question.number;
                
            // ✅ QUESTION (с KaTeX можно)
            document.getElementById('question-text').innerHTML = fixLatex(question.question);
                
            const passageElem = document.getElementById('passage');
            const questionTextElem = document.getElementById('question-text');
            const graphContainer = document.querySelector('.just-div');
            const answersContainer = document.getElementById('answers');
                
            const buildChoice = (letter, content) => {
                const checked = answers[currentQuestionIndex] === letter ? 'checked' : '';
                const inputId = `choice-${currentQuestionIndex}-${letter}`;
                const isEliminated = eliminatedChoices[currentQuestionIndex].includes(letter) ? 'active' : '';
            
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
                        <label class="choice-container" for="${inputId}" data-choice-letter="${letter}">
                            <span class="mark" data-letter="${letter}"></span>
                            <span class="choice-content">${fixLatex(content)}</span>
                        </label>
                        <hr class="cross-line ${letter}zone ${isEliminated}">
                        <button
                            type="button"
                            class="crossing-zone ${eliminate_options ? 'active' : ''}"
                            data-letter="${letter}"
                            data-index="${currentQuestionIndex}"
                        >
                            <span class="cross-label">${letter}</span>
                            <span class="cross-btn-line"></span>
                        </button>
                    </div>
                `;
            };
        
            answersContainer.innerHTML = `
                ${buildChoice('A', question.a)}
                ${buildChoice('B', question.b)}
                ${buildChoice('C', question.c)}
                ${buildChoice('D', question.d)}
            `;
            bindAnswerChoiceEvents(answersContainer);
            paintCurrentAnswer();
        
            if (question.graph) {
                graphContainer.innerHTML = `<div class='graph'><img src="${question.graph}" style="width:100%"></div>`;
            } else {
                graphContainer.innerHTML = '';
            }
        
            updateAnsweredStatus();
        
            // ✅ KaTeX только там где надо
            renderMath(questionTextElem);
            renderMath(document.getElementById('answers'));
            paintCurrentAnswer();
            triggerQuestionMotion(motionDirection);
        }

        function show_eliminate() {
            eliminate_options = !eliminate_options;
            const button = document.querySelector('.crossing-options');
            if (button) {
                button.classList.toggle('active-options', eliminate_options);
                pulseElement(button);
            }
            document.body.classList.toggle('is-eliminate-mode', eliminate_options);
            document.querySelectorAll('.crossing-zone').forEach((element) => {
                element.classList.toggle('active', eliminate_options);
            });
        }

        function eliminate(choice, index) {
            const normalizedChoice = normalizeChoice(choice);
            const safeIndex = Number.isInteger(index) ? index : currentQuestionIndex;
            if (!normalizedChoice || safeIndex < 0 || safeIndex >= eliminatedChoices.length) return;

            const eliminated = eliminatedChoices[safeIndex] || [];
            const wasEliminated = eliminated.includes(normalizedChoice);

            if (wasEliminated) {
                eliminatedChoices[safeIndex] = eliminated.filter((item) => item !== normalizedChoice);
            } else {
                eliminatedChoices[safeIndex] = [...eliminated, normalizedChoice];
                if (normalizeChoice(answers[safeIndex]) === normalizedChoice) {
                    answers[safeIndex] = null;
                }
            }

            animateElimination(normalizedChoice, wasEliminated);
            refreshEliminationState(safeIndex);
            paintCurrentAnswer();
            updateAnsweredStatus();
            saveProgress();
        }

        function nextQuestion() {
            pulseElement(document.getElementById('nextButton'));
            if (currentQuestionIndex < questions.length - 1) {
                loadQuestion(currentQuestionIndex + 1);
            }
            saveProgress();
        }

        function prevQuestion() {
            pulseElement(document.getElementById('backButton'));
            if (currentQuestionIndex > 0) {
                loadQuestion(currentQuestionIndex - 1);
            }
            saveProgress();
        }

        function updateTimer() {
            if (timeRemaining > 0) {
                timeRemaining--;
                timeSpent[currentQuestionIndex] += 1;
                document.querySelector('.timer').innerText = formatTime(timeRemaining);
            } else {
                finishTest(true);
            }
        }

        function formatTime(seconds) {
            const minutes = Math.floor(seconds / 60);
            const secs = seconds % 60;
            saveProgress();
            return `${minutes}:${secs < 10 ? '0' : ''}${secs}`;
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

        async function finishTest(confirmation) {
            if (!confirmation) {
                confirmation = confirm('Are you sure you want to finish the test? Make sure you are ready.');
            }
            if (!confirmation) return;

            syncCurrentAnswerFromDom();

            const finishButton = document.getElementById('finishButton');
            const originalText = finishButton.textContent;
            finishButton.textContent = 'Submitting...';
            finishButton.disabled = true;

            try {
                const form = document.getElementById('quiz-form');
                const answerData = answers.map((answer, index) => ({
                    questionID: questions[index] ? questions[index].id : null,
                    answer,
                    time_spent: timeSpent[index]
                }));
                const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

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
                alert(`Failed to submit test: ${error.message}. Please try again or contact support.`);
            } finally {
                finishButton.textContent = originalText;
                finishButton.disabled = false;
            }
        }

        function markForReview() {
            markedForReview[currentQuestionIndex] = !markedForReview[currentQuestionIndex];
            pulseElement(document.querySelector('.bookmark'));
            updateAnsweredStatus();
            saveProgress();
        }

        document.addEventListener('contextmenu', event => event.preventDefault());
        document.addEventListener('selectstart', event => event.preventDefault());

        document.addEventListener('keydown', event => {
            if (event.ctrlKey && (event.key === 'u' || event.key === 's' || event.key === 'p' || event.key === 'c' || event.key === 'j' || event.key === 'i')) {
                event.preventDefault();
            }
            if (event.key === 'ArrowLeft') {
                event.preventDefault();
                prevQuestion();
            }
            if (event.key === 'ArrowRight') {
                event.preventDefault();
                nextQuestion();
            }
            if (event.key === 'F12') {
                event.preventDefault();
            }
        });

        function updateAnsweredStatus(n = -999) {
            let mark = document.querySelector('.bookmark');
            if (markedForReview[currentQuestionIndex]) {
                mark.classList.add('filledbook');
            } else {
                mark.classList.remove('filledbook');
            }
            const rectQuestions = document.querySelectorAll('.rect-question');
            rectQuestions.forEach((rect, index) => {
                if (index == currentQuestionIndex) {
                    rect.classList.add('here');
                } else {
                    rect.classList.remove('here');
                }
                if (markedForReview[index]) {
                    rect.classList.add('marked');
                } else {
                    rect.classList.remove('marked');
                }
                if (answers[index]) {
                    rect.classList.add('answered');
                } else {
                    rect.classList.remove('answered');
                }
            });
        }

        let testBooted = false;
        function bootTestWindow() {
            if (testBooted) return;
            const required = document.getElementById('answers') && document.getElementById('passage') && document.getElementById('question-text');
            if (!required) return;
            testBooted = true;
            document.body.classList.add('mk-test-window');

            // Make sure stale inline styles/classes cannot leave the question navigator stuck over the page.
            closeQuestionModal();

            loadProgress();
            loadQuestion(currentQuestionIndex);
            const timer = document.querySelector('.timer');
            if (timer) timer.innerText = formatTime(timeRemaining);
            renderMath(document.body);
            window.setInterval(updateTimer, 1000);

            const penButton = document.getElementById('pen-button');
            const clearButton = document.getElementById('clear-button');
            const canvas = document.getElementById('drawing-canvas');
            const body = document.body;

            if (canvas) {
                const ctx = canvas.getContext('2d');
                let isPenMode = false;
                let isDrawing = false;
                let lastX = 0;
                let lastY = 0;
                let canvasRect = canvas.getBoundingClientRect();

                function updateToolState() {
                    body.classList.toggle('pen-mode', isPenMode);
                    if (penButton) {
                        penButton.classList.toggle('active', isPenMode);
                        penButton.setAttribute('aria-pressed', isPenMode ? 'true' : 'false');
                        penButton.setAttribute('title', isPenMode ? 'Turn highlighter off' : 'Turn highlighter on');
                    }
                    canvas.style.pointerEvents = isPenMode ? 'auto' : 'none';
                }

                function togglePenMode(force) {
                    isPenMode = typeof force === 'boolean' ? force : !isPenMode;
                    if (!isPenMode) isDrawing = false;
                    updateToolState();
                }

                function resizeCanvas() {
                    const main = document.querySelector('main');
                    const rect = main ? main.getBoundingClientRect() : document.body.getBoundingClientRect();
                    const ratio = window.devicePixelRatio || 1;
                    canvas.style.left = `${Math.max(rect.left, 0)}px`;
                    canvas.style.top = `${Math.max(rect.top, 0)}px`;
                    canvas.style.width = `${Math.max(rect.width, 1)}px`;
                    canvas.style.height = `${Math.max(rect.height, 1)}px`;
                    canvas.width = Math.max(Math.floor(rect.width * ratio), 1);
                    canvas.height = Math.max(Math.floor(rect.height * ratio), 1);
                    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
                    ctx.lineWidth = 16;
                    ctx.lineCap = 'round';
                    ctx.lineJoin = 'round';
                    ctx.strokeStyle = 'rgba(250, 204, 21, 0.34)';
                    canvasRect = canvas.getBoundingClientRect();
                }

                function pointFromEvent(event) {
                    const point = event.touches && event.touches[0] ? event.touches[0] : event;
                    return { x: point.clientX - canvasRect.left, y: point.clientY - canvasRect.top };
                }

                function startDrawing(event) {
                    if (!isPenMode) return;
                    event.preventDefault();
                    canvasRect = canvas.getBoundingClientRect();
                    const point = pointFromEvent(event);
                    isDrawing = true;
                    lastX = point.x;
                    lastY = point.y;
                }

                function draw(event) {
                    if (!isDrawing || !isPenMode) return;
                    event.preventDefault();
                    const point = pointFromEvent(event);
                    ctx.beginPath();
                    ctx.moveTo(lastX, lastY);
                    ctx.lineTo(point.x, point.y);
                    ctx.stroke();
                    lastX = point.x;
                    lastY = point.y;
                }

                function stopDrawing() { isDrawing = false; }

                if (penButton) {
                    penButton.addEventListener('click', (e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        togglePenMode();
                    });
                }

                if (clearButton) {
                    clearButton.addEventListener('click', (e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        ctx.clearRect(0, 0, canvas.width, canvas.height);
                    });
                }

                document.addEventListener('keydown', (event) => {
                    if (event.key === 'Escape') {
                        if (isPenMode) togglePenMode(false);
                        closeQuestionModal();
                    }
                });

                const modal = document.getElementById('questionModal');
                if (modal) {
                    modal.addEventListener('click', (event) => {
                        if (event.target === modal) closeQuestionModal();
                    });
                }

                canvas.addEventListener('mousedown', startDrawing);
                canvas.addEventListener('mousemove', draw);
                window.addEventListener('mouseup', stopDrawing);
                canvas.addEventListener('mouseleave', stopDrawing);
                canvas.addEventListener('touchstart', startDrawing, { passive: false });
                canvas.addEventListener('touchmove', draw, { passive: false });
                window.addEventListener('touchend', stopDrawing);
                window.addEventListener('resize', resizeCanvas);
                window.addEventListener('scroll', resizeCanvas, { passive: true });

                resizeCanvas();
                updateToolState();
            }
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', bootTestWindow, { once: true });
        }
        bootTestWindow();
