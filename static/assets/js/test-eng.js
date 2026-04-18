
        const pageConfig = JSON.parse(document.getElementById('sat-test-config').textContent);
        const questions = JSON.parse(document.getElementById('sat-test-questions').textContent);

        let currentQuestionIndex = 0;
        let eliminate_options = false;
        let answers = Array(questions.length).fill(null);
        let eliminatedChoices = Array(questions.length).fill().map(() => []);
        let markedForReview = Array(questions.length).fill(false);
        let timeRemaining = Number(pageConfig.timeRemaining || 0);
        let timeSpent = Array(questions.length).fill(0);

        const testName = pageConfig.testName;
        const moduleName = pageConfig.moduleName;
        const sectionName = pageConfig.sectionName;
        const isGuestMode = pageConfig.mode === 'guest';
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
            if (typeof renderMathInElement !== 'function') return;
            try {
                renderMathInElement(root, {
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

        function toggleQuestionModal() {
            var modal = document.getElementById("questionModal");
            if (modal.style.display === "block") {
                modal.style.display = "none";
            } else {
                modal.style.display = "block";
            }
        }

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

        function loadProgress() {
            const key = storageKey();
            const savedAnswers = localStorage.getItem(`${key}_answers`);
            const savedEliminatedChoices = localStorage.getItem(`${key}_eliminatedChoices`);
            const savedIndex = localStorage.getItem(`${key}_currentQuestionIndex`);
            const savedTime = localStorage.getItem(`${key}_timeRemaining`);
            const savedReview = localStorage.getItem(`${key}_markedForReview`);
            const savedTimeSpent = localStorage.getItem(`${key}_timeSpent`);

            if (savedTimeSpent) {
                timeSpent = JSON.parse(savedTimeSpent);
            }
            if (savedAnswers) {
                answers = JSON.parse(savedAnswers);
            }
            if (savedEliminatedChoices) {
                eliminatedChoices = JSON.parse(savedEliminatedChoices);
            }
            if (savedReview) {
                markedForReview = JSON.parse(savedReview);
            }
            if (savedIndex) {
                currentQuestionIndex = parseInt(savedIndex, 10);
            } else {
                currentQuestionIndex = 0;
            }
            if (savedTime) {
                timeRemaining = parseInt(savedTime, 10);
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
        }

        function setCurrentAnswer(value) {
            const choice = normalizeChoice(value);
            if (!choice) return false;

            answers[currentQuestionIndex] = choice;
            paintCurrentAnswer();
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

        function loadQuestion(index) {
            const nextIndex = Number(index);
            if (!Number.isInteger(nextIndex) || nextIndex < 0 || nextIndex >= questions.length) return;

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
                    <div class="big-container" data-choice-letter="${letter}">
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
        }

        function show_eliminate() {
            eliminate_options = !eliminate_options;
            let button = document.querySelector('.crossing-options');
            button.classList.toggle("active-options");
            let btns = document.querySelectorAll('.crossing-zone');
            btns.forEach(element => {
                element.classList.toggle('active');
            });
        }

        function eliminate(choice, index) {
            let line = document.querySelector(`.${choice}zone`);
            line.classList.toggle('active');
            if (eliminatedChoices[index].includes(choice)) {
                const choiceIndex = eliminatedChoices[index].indexOf(choice);
                eliminatedChoices[index].splice(choiceIndex, 1);
            } else {
                eliminatedChoices[index].push(choice);
            }
            saveProgress();
        }

        function nextQuestion() {
            if (currentQuestionIndex < questions.length - 1) {
                loadQuestion(currentQuestionIndex + 1);
            }
            saveProgress();
        }

        function prevQuestion() {
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

        function markForReview() {
            markedForReview[currentQuestionIndex] = !markedForReview[currentQuestionIndex];
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

        document.addEventListener('DOMContentLoaded', () => {
            loadProgress();
            loadQuestion(currentQuestionIndex);
            renderMath(document.body);
            setInterval(updateTimer, 1000);

            // Highlighter Logic
            const penButton = document.getElementById('pen-button');
            const canvas = document.getElementById('drawing-canvas');
            const ctx = canvas.getContext('2d');
            const body = document.body;

            let isPenMode = false;
            let isDrawing = false;
            let lastX = 0;
            let lastY = 0;

            function togglePenMode() {
                isPenMode = !isPenMode;
                console.log('Pen Mode:', isPenMode);
                body.classList.toggle('pen-mode', isPenMode);
                penButton.classList.toggle('active', isPenMode);
                canvas.style.pointerEvents = isPenMode ? 'auto' : 'none';
            }

            if (penButton) {
                penButton.addEventListener('click', (e) => {
                    e.preventDefault();
                    togglePenMode();
                });
            } else {
                console.error('Pen button not found');
            }

            function resizeCanvas() {
                canvas.width = window.innerWidth;
                canvas.height = window.innerHeight;
            }
            resizeCanvas();
            window.addEventListener('resize', resizeCanvas);

            ctx.lineWidth = 10;
            ctx.lineCap = 'round';
            ctx.strokeStyle = 'rgba(255, 255, 0, 0.05)';

            canvas.addEventListener('mousedown', (e) => {
                if (!isPenMode) return;
                isDrawing = true;
                [lastX, lastY] = [e.clientX, e.clientY];
                console.log('Drawing started at:', lastX, lastY);
            });

            canvas.addEventListener('mousemove', (e) => {
                if (!isDrawing || !isPenMode) return;
                ctx.beginPath();
                ctx.moveTo(lastX, lastY);
                ctx.lineTo(e.clientX, e.clientY);
                ctx.stroke();
                [lastX, lastY] = [e.clientX, e.clientY];
            });

            canvas.addEventListener('mouseup', () => {
                isDrawing = false;
            });

            canvas.addEventListener('mouseleave', () => {
                isDrawing = false;
            });

            const clearButton = document.getElementById('clear-button');
            if (clearButton) {
                clearButton.addEventListener('click', (e) => {
                    e.preventDefault();
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                    console.log('Canvas cleared');
                });
            } else {
                console.error('Clear button not found');
            }
        });
    