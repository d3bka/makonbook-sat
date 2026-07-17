(function () {
  'use strict';

  const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
  const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));

  function parseJsonScript(id, fallback) {
    const node = document.getElementById(id);
    if (!node) return fallback;
    try {
      return JSON.parse(node.textContent || '');
    } catch (error) {
      console.error(`Could not parse ${id}:`, error);
      return fallback;
    }
  }

  function csrfToken() {
    const input = document.querySelector('[name="csrfmiddlewaretoken"]');
    return input ? input.value : '';
  }

  function timeoutSignal(ms) {
    if (typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function') {
      return AbortSignal.timeout(ms);
    }
    if (typeof AbortController === 'undefined') return undefined;
    const controller = new AbortController();
    window.setTimeout(() => controller.abort(), ms);
    return controller.signal;
  }

  function normalizeChoice(value) {
    const choice = String(value == null ? '' : value).trim().toUpperCase();
    return ['A', 'B', 'C', 'D'].includes(choice) ? choice : null;
  }

  function normalizeArray(value, length, factory) {
    const output = Array.isArray(value) ? value.slice(0, length) : [];
    while (output.length < length) output.push(factory(output.length));
    return output;
  }

  class SATTestCore {
    constructor(options) {
      this.options = options || {};
      this.config = parseJsonScript('sat-test-config', {});
      this.questions = parseJsonScript('sat-test-questions', []);
      this.serverState = parseJsonScript('sat-test-session-state', {});
      this.form = document.getElementById(this.options.formId);
      this.isGuest = this.config.mode === 'guest';
      this.isMakeup = this.config.testType === 'makeup';
      this.questionCount = this.questions.length;
      this.submitInProgress = false;
      this.autosaveInProgress = false;
      this.autosaveQueued = false;
      this.autosaveTimer = null;
      this.timerHandle = null;
      this.lastTickAt = Date.now();
      this.activeMs = 0;
      this.pageWasVisible = document.visibilityState !== 'hidden';
      this.nextForcedSubmitAt = 0;
      this.lastSavedAt = 0;
      this.booted = false;
      this.navigatingAway = false;
      this.tabBlocked = false;
      this.tabId = (window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`).toString();

      this.storageKey = [
        'sat-flow-v13',
        this.config.storageScope || 'unknown',
        this.config.attemptId || 'attempt',
        this.config.classroomId || 'regular',
        this.config.sectionName || 'section',
        this.config.moduleName || 'module',
      ].join(':');
      this.tabLockKey = `${this.storageKey}:active-tab`;

      this.state = this.loadInitialState();
      this.deadlineAt = this.resolveDeadline();
      this.currentQuestionIndex = clamp(
        Number(this.state.currentQuestionIndex) || 0,
        0,
        Math.max(this.questionCount - 1, 0),
      );
      this.answers = normalizeArray(this.state.answers, this.questionCount, () => null);
      this.timeSpent = normalizeArray(this.state.timeSpent, this.questionCount, () => 0)
        .map((value) => Math.max(Number(value) || 0, 0));
      this.eliminatedChoices = normalizeArray(
        this.state.eliminatedChoices,
        this.questionCount,
        () => [],
      ).map((row) => Array.isArray(row) ? row.map(normalizeChoice).filter(Boolean) : []);
      this.markedForReview = normalizeArray(
        this.state.markedForReview,
        this.questionCount,
        () => false,
      ).map(Boolean);

      this.bindPublicApi();
    }

    resolveDeadline() {
      const serverDeadline = Number(this.serverState.deadlineAt || this.config.deadlineAt || 0);
      if (Number.isFinite(serverDeadline) && serverDeadline > 0) return serverDeadline;
      const restoredDeadline = Number(this.state?.deadlineAt || 0);
      if (Number.isFinite(restoredDeadline) && restoredDeadline > Date.now()) return restoredDeadline;
      const seconds = Math.max(Number(this.config.timeRemaining || 0), 0);
      return Date.now() + (seconds * 1000);
    }

    readLocalState() {
      try {
        const raw = localStorage.getItem(this.storageKey);
        return raw ? JSON.parse(raw) : {};
      } catch (error) {
        console.warn('Local test state could not be read:', error);
        return {};
      }
    }

    loadInitialState() {
      const local = this.readLocalState();
      const server = this.serverState && typeof this.serverState === 'object' ? this.serverState : {};
      const localUpdated = Number(local.updatedAt || 0);
      const serverUpdated = Number(server.updatedAt || 0);
      const primary = localUpdated > serverUpdated ? local : server;
      const fallback = primary === local ? server : local;
      const mergedAnswers = normalizeArray(primary.answers, this.questionCount, () => null)
        .map((answer, index) => {
          if (answer !== null && answer !== undefined && String(answer) !== '') return answer;
          const other = Array.isArray(fallback.answers) ? fallback.answers[index] : null;
          return other === undefined ? null : other;
        });
      const primaryTimes = normalizeArray(primary.timeSpent, this.questionCount, () => 0);
      const fallbackTimes = normalizeArray(fallback.timeSpent, this.questionCount, () => 0);
      return {
        answers: mergedAnswers,
        timeSpent: primaryTimes.map((value, index) => Math.max(Number(value) || 0, Number(fallbackTimes[index]) || 0)),
        eliminatedChoices: primary.eliminatedChoices || fallback.eliminatedChoices || [],
        markedForReview: primary.markedForReview || fallback.markedForReview || [],
        currentQuestionIndex: primary.currentQuestionIndex ?? fallback.currentQuestionIndex ?? 0,
        deadlineAt: server.deadlineAt || local.deadlineAt || 0,
        updatedAt: Math.max(localUpdated, serverUpdated),
      };
    }

    snapshot() {
      this.flushActiveTime();
      return {
        answers: this.answers.slice(),
        timeSpent: this.timeSpent.slice(),
        eliminatedChoices: this.eliminatedChoices.map((row) => row.slice()),
        markedForReview: this.markedForReview.slice(),
        currentQuestionIndex: this.currentQuestionIndex,
        deadlineAt: this.deadlineAt,
        updatedAt: Date.now(),
      };
    }

    saveLocal() {
      try {
        localStorage.setItem(this.storageKey, JSON.stringify(this.snapshot()));
      } catch (error) {
        console.warn('Local test state could not be saved:', error);
      }
    }

    clearLocal() {
      try {
        localStorage.removeItem(this.storageKey);
      } catch (error) {
        console.warn('Local test state could not be cleared:', error);
      }
    }

    answerPayload() {
      this.flushActiveTime();
      return this.questions.map((question, index) => ({
        questionID: question.id,
        answer: this.answers[index],
        time_spent: Math.max(Math.round(Number(this.timeSpent[index]) || 0), 0),
      }));
    }

    fullStatePayload() {
      return {
        answers: this.answerPayload(),
        section: this.config.sectionName,
        module: this.config.moduleName,
        test: this.config.testName,
        classroom_id: this.config.classroomId || null,
        test_type: this.config.testType || 'regular',
        attempt_id: this.config.attemptId || null,
        current_question_index: this.currentQuestionIndex,
        eliminated_choices: this.eliminatedChoices,
        marked_for_review: this.markedForReview,
      };
    }

    setSaveState(state, message) {
      const indicator = document.querySelector('[data-test-save-status]');
      if (!indicator) return;
      indicator.dataset.state = state;
      const label = indicator.querySelector('[data-test-save-label]');
      if (label) label.textContent = message;
    }

    scheduleAutosave(delay = 900) {
      this.saveLocal();
      if (this.submitInProgress) return;
      window.clearTimeout(this.autosaveTimer);
      this.autosaveTimer = window.setTimeout(() => this.autosave(), delay);
    }

    async autosave(force = false) {
      if (this.submitInProgress || this.tabBlocked) return true;
      if (this.autosaveInProgress) {
        this.autosaveQueued = true;
        return false;
      }
      const url = this.isGuest ? this.form?.action : this.config.draftSaveUrl;
      if (!url) return true;

      this.autosaveInProgress = true;
      this.autosaveQueued = false;
      this.setSaveState('saving', 'Saving…');
      try {
        const response = await fetch(url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken(),
            'X-Requested-With': 'XMLHttpRequest',
          },
          body: JSON.stringify(this.fullStatePayload()),
          signal: timeoutSignal(force ? 15000 : 9000),
          keepalive: Boolean(force),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.ok) {
          if (data.redirect_url) {
            this.navigatingAway = true;
            window.location.assign(data.redirect_url);
            return false;
          }
          if (data.time_over) {
            await this.submitModule(true);
            return false;
          }
          throw new Error(data.error || `Save failed (${response.status})`);
        }
        if (Number(data.deadline_at) > 0) this.deadlineAt = Number(data.deadline_at);
        this.lastSavedAt = Number(data.saved_at || Date.now());
        this.setSaveState('saved', 'Saved');
        this.saveLocal();
        return true;
      } catch (error) {
        if (error && error.name === 'AbortError') {
          this.setSaveState('offline', 'Save delayed');
        } else {
          console.warn('Autosave failed:', error);
          this.setSaveState('offline', 'Not saved');
        }
        return false;
      } finally {
        this.autosaveInProgress = false;
        if (this.autosaveQueued && !this.submitInProgress) {
          this.autosaveQueued = false;
          window.setTimeout(() => this.autosave(), 250);
        }
      }
    }

    flushActiveTime() {
      const now = Date.now();
      const delta = Math.max(now - this.lastTickAt, 0);
      this.lastTickAt = now;
      if (this.pageWasVisible) this.activeMs += delta;
      if (this.activeMs >= 1000 && this.questionCount) {
        const seconds = Math.floor(this.activeMs / 1000);
        this.activeMs -= seconds * 1000;
        this.timeSpent[this.currentQuestionIndex] =
          Math.max(Number(this.timeSpent[this.currentQuestionIndex]) || 0, 0) + seconds;
      }
    }

    remainingSeconds() {
      return Math.max(Math.ceil((this.deadlineAt - Date.now()) / 1000), 0);
    }

    formatTime(seconds) {
      const safe = Math.max(Math.floor(Number(seconds) || 0), 0);
      const minutes = Math.floor(safe / 60);
      const secs = safe % 60;
      return `${minutes}:${String(secs).padStart(2, '0')}`;
    }

    updateTimer() {
      this.flushActiveTime();
      const remaining = this.remainingSeconds();
      const timer = document.getElementById('timer');
      if (timer) {
        timer.textContent = this.formatTime(remaining);
        timer.classList.toggle('is-warning', remaining <= 300 && remaining > 60);
        timer.classList.toggle('is-critical', remaining <= 60);
      }
      if (remaining <= 0 && !this.submitInProgress && Date.now() >= this.nextForcedSubmitAt) {
        this.nextForcedSubmitAt = Date.now() + 15000;
        this.submitModule(true);
      }
    }

    setAnswer(value) {
      this.answers[this.currentQuestionIndex] = value;
      this.updateNavigator();
      this.options.paintAnswer?.(this);
      this.scheduleAutosave();
    }

    selectChoice(value) {
      const choice = normalizeChoice(value);
      if (!choice) return;
      const eliminated = this.eliminatedChoices[this.currentQuestionIndex] || [];
      this.eliminatedChoices[this.currentQuestionIndex] = eliminated.filter((item) => item !== choice);
      this.setAnswer(choice);
    }

    setTextAnswer(value) {
      this.setAnswer(String(value == null ? '' : value).slice(0, 4000));
    }

    toggleEliminated(choice) {
      const normalized = normalizeChoice(choice);
      if (!normalized) return;
      const row = this.eliminatedChoices[this.currentQuestionIndex] || [];
      if (row.includes(normalized)) {
        this.eliminatedChoices[this.currentQuestionIndex] = row.filter((item) => item !== normalized);
      } else {
        this.eliminatedChoices[this.currentQuestionIndex] = row.concat(normalized);
        if (normalizeChoice(this.answers[this.currentQuestionIndex]) === normalized) {
          this.answers[this.currentQuestionIndex] = null;
        }
      }
      this.options.paintAnswer?.(this);
      this.updateNavigator();
      this.scheduleAutosave();
    }

    toggleMarked() {
      this.markedForReview[this.currentQuestionIndex] = !this.markedForReview[this.currentQuestionIndex];
      this.updateNavigator();
      this.scheduleAutosave();
    }

    goTo(index, direction) {
      if (!this.questionCount || this.submitInProgress || this.tabBlocked) return;
      this.flushActiveTime();
      this.options.beforeQuestionChange?.(this);
      const next = clamp(Number(index) || 0, 0, this.questionCount - 1);
      const movement = direction || (next < this.currentQuestionIndex ? 'prev' : 'next');
      this.currentQuestionIndex = next;
      this.options.renderQuestion?.(this, this.questions[next], movement);
      this.updateNavigator();
      this.options.afterQuestionChange?.(this);
      this.scheduleAutosave(1300);
    }

    next() {
      if (this.currentQuestionIndex < this.questionCount - 1) this.goTo(this.currentQuestionIndex + 1, 'next');
    }

    previous() {
      if (this.currentQuestionIndex > 0) this.goTo(this.currentQuestionIndex - 1, 'prev');
    }

    isAnswered(index) {
      const value = this.answers[index];
      return value !== null && value !== undefined && String(value).trim() !== '';
    }

    counts() {
      let answered = 0;
      let marked = 0;
      this.questions.forEach((_, index) => {
        if (this.isAnswered(index)) answered += 1;
        if (this.markedForReview[index]) marked += 1;
      });
      return { answered, unanswered: this.questionCount - answered, marked };
    }

    updateNavigator() {
      const current = document.getElementById('currentQuestionIndex');
      const total = document.getElementById('totalQuestions');
      if (current) current.textContent = String(this.currentQuestionIndex + 1);
      if (total) total.textContent = String(this.questionCount);

      const back = document.getElementById('backButton');
      const next = document.getElementById('nextButton');
      const finish = document.getElementById('finishButton');
      if (back) back.disabled = this.currentQuestionIndex <= 0;
      if (next) next.hidden = this.currentQuestionIndex >= this.questionCount - 1;
      if (finish) finish.hidden = this.currentQuestionIndex < this.questionCount - 1;

      document.querySelectorAll('.rect-question').forEach((button, index) => {
        button.classList.toggle('here', index === this.currentQuestionIndex);
        button.classList.toggle('answered', this.isAnswered(index));
        button.classList.toggle('marked', Boolean(this.markedForReview[index]));
        button.setAttribute('aria-current', index === this.currentQuestionIndex ? 'true' : 'false');
        const status = [
          this.isAnswered(index) ? 'answered' : 'unanswered',
          this.markedForReview[index] ? 'marked for review' : '',
        ].filter(Boolean).join(', ');
        button.setAttribute('aria-label', `Question ${index + 1}, ${status}`);
      });

      const bookmark = document.querySelector('.bookmark');
      if (bookmark) {
        const marked = Boolean(this.markedForReview[this.currentQuestionIndex]);
        bookmark.classList.toggle('filledbook', marked);
        bookmark.setAttribute('aria-pressed', String(marked));
      }

      const counts = this.counts();
      document.querySelectorAll('[data-test-answered-count]').forEach((node) => {
        node.textContent = String(counts.answered);
      });
      document.querySelectorAll('[data-test-unanswered-count]').forEach((node) => {
        node.textContent = String(counts.unanswered);
      });
      document.querySelectorAll('[data-test-marked-count]').forEach((node) => {
        node.textContent = String(counts.marked);
      });
    }

    openQuestionModal() {
      const modal = document.getElementById('questionModal');
      if (!modal) return;
      modal.hidden = false;
      modal.classList.add('is-open');
      modal.setAttribute('aria-hidden', 'false');
      document.body.classList.add('question-modal-open');
      const currentButton = modal.querySelector('.rect-question.here');
      currentButton?.scrollIntoView({ block: 'center', inline: 'center', behavior: 'smooth' });
      window.setTimeout(() => currentButton?.focus(), 120);
    }

    closeQuestionModal() {
      const modal = document.getElementById('questionModal');
      if (!modal) return;
      modal.classList.remove('is-open');
      modal.setAttribute('aria-hidden', 'true');
      modal.hidden = true;
      document.body.classList.remove('question-modal-open');
    }

    toggleQuestionModal() {
      const modal = document.getElementById('questionModal');
      if (modal?.classList.contains('is-open')) this.closeQuestionModal();
      else this.openQuestionModal();
    }

    showFinishSummary() {
      const modal = document.getElementById('finishSummaryModal');
      if (!modal) {
        this.submitModule(false);
        return;
      }
      const counts = this.counts();
      const completion = this.questionCount ? Math.round((counts.answered / this.questionCount) * 100) : 0;
      modal.querySelector('[data-summary-answered]').textContent = String(counts.answered);
      modal.querySelector('[data-summary-unanswered]').textContent = String(counts.unanswered);
      modal.querySelector('[data-summary-marked]').textContent = String(counts.marked);

      const progressLabel = modal.querySelector('[data-summary-progress-label]');
      const progressBar = modal.querySelector('[data-summary-progress-bar]');
      if (progressLabel) progressLabel.textContent = `${completion}% complete`;
      if (progressBar) progressBar.style.width = `${completion}%`;

      const warning = modal.querySelector('[data-summary-warning]');
      const ready = modal.querySelector('[data-summary-ready]');
      const reviewSection = modal.querySelector('[data-summary-review-section]');
      const reviewList = modal.querySelector('[data-summary-review-list]');
      const reviewIndexes = [];
      this.questions.forEach((question, index) => {
        if (!this.isAnswered(index) || this.markedForReview[index]) reviewIndexes.push(index);
      });

      const needsReview = reviewIndexes.length > 0;
      if (warning) warning.hidden = !needsReview;
      if (ready) ready.hidden = needsReview;
      if (reviewSection) reviewSection.hidden = !needsReview;
      if (reviewList) {
        reviewList.innerHTML = reviewIndexes.map((index) => {
          const labels = [];
          if (!this.isAnswered(index)) labels.push('Unanswered');
          if (this.markedForReview[index]) labels.push('Marked');
          const number = this.questions[index]?.number || index + 1;
          return `<button type="button" class="finish-review-chip" data-review-question="${index}"><strong>${number}</strong><span>${labels.join(' · ')}</span></button>`;
        }).join('');
        reviewList.querySelectorAll('[data-review-question]').forEach((button) => {
          button.addEventListener('click', () => {
            const index = Number(button.dataset.reviewQuestion);
            this.closeFinishSummary();
            this.goTo(index);
          });
        });
      }

      modal.hidden = false;
      modal.classList.add('is-open');
      modal.setAttribute('aria-hidden', 'false');
      modal.querySelector('[data-confirm-submit]')?.focus();
    }

    closeFinishSummary() {
      const modal = document.getElementById('finishSummaryModal');
      if (!modal) return;
      modal.classList.remove('is-open');
      modal.setAttribute('aria-hidden', 'true');
      modal.hidden = true;
    }

    setSubmitProgress(open) {
      const overlay = document.getElementById('submitProgressOverlay');
      if (overlay) {
        overlay.hidden = !open;
        overlay.classList.toggle('is-open', open);
        overlay.setAttribute('aria-hidden', String(!open));
      }
      const label = document.querySelector('[data-submit-button-label]');
      if (label) label.textContent = open ? 'Submitting…' : 'Submit module';
    }

    async fetchWithRetry(url, payload, attempts = 3) {
      let lastError;
      for (let index = 0; index < attempts; index += 1) {
        try {
          const response = await fetch(url, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': csrfToken(),
              'X-Requested-With': 'XMLHttpRequest',
            },
            body: JSON.stringify(payload),
            signal: timeoutSignal(Number(this.config.submitTimeoutMs || 30000)),
          });
          const data = await response.json().catch(() => ({}));
          if (!response.ok || data.ok === false) {
            const error = new Error(data.error || `Server error (${response.status})`);
            error.data = data;
            throw error;
          }
          return data;
        } catch (error) {
          lastError = error;
          if (error?.data?.redirect_url) throw error;
          if (index < attempts - 1) await sleep(700 * Math.pow(2, index));
        }
      }
      throw lastError || new Error('The module could not be submitted.');
    }

    async submitModule(force = false) {
      if (this.submitInProgress || this.tabBlocked) return;
      if (!force) {
        this.showFinishSummary();
        return;
      }

      this.closeFinishSummary();
      this.submitInProgress = true;
      this.flushActiveTime();
      this.setSaveState('saving', 'Submitting…');
      document.body.classList.add('is-submitting-test');
      this.setSubmitProgress(true);
      document.querySelectorAll('#finishButton, [data-confirm-submit]').forEach((button) => {
        button.disabled = true;
      });

      try {
        const payload = this.fullStatePayload();
        let redirectUrl = this.config.nextUrl || '';

        if (this.isGuest) {
          // Guest submission is one atomic request. The old two-request flow could
          // save successfully and then fail before marking the module complete (or
          // complete a module after the final save failed).
          const result = await this.fetchWithRetry(this.config.submitUrl, payload, 3);
          if (result.deadline_at) this.deadlineAt = Number(result.deadline_at);
          redirectUrl = result.redirect_url || redirectUrl;
        } else {
          const result = await this.fetchWithRetry(this.form.action, payload, 3);
          redirectUrl = result.redirect_url || redirectUrl;
        }

        if (!redirectUrl) throw new Error('The server did not provide the next test page.');
        this.clearLocal();
        this.navigatingAway = true;
        window.location.assign(redirectUrl);
      } catch (error) {
        console.error('Module submit failed:', error);
        if (error?.data?.redirect_url) {
          this.clearLocal();
          this.navigatingAway = true;
          window.location.assign(error.data.redirect_url);
          return;
        }
        this.nextForcedSubmitAt = Date.now() + 15000;
        this.showToast(error?.message || 'The module was not submitted. Your answers remain saved.', 'error');
        this.setSaveState('offline', navigator.onLine ? 'Submit failed' : 'Offline · submit pending');
      } finally {
        if (!this.navigatingAway) {
          this.submitInProgress = false;
          document.body.classList.remove('is-submitting-test');
          this.setSubmitProgress(false);
          document.querySelectorAll('#finishButton, [data-confirm-submit]').forEach((button) => {
            button.disabled = false;
          });
        }
      }
    }

    showToast(message, type = 'info') {
      const toast = document.querySelector('[data-test-toast]');
      if (!toast) {
        window.alert(message);
        return;
      }
      toast.textContent = message;
      toast.dataset.type = type;
      toast.classList.add('is-visible');
      window.clearTimeout(this.toastTimer);
      this.toastTimer = window.setTimeout(() => toast.classList.remove('is-visible'), 6000);
    }

    writeTabLease() {
      try {
        localStorage.setItem(this.tabLockKey, JSON.stringify({
          tabId: this.tabId,
          timestamp: Date.now(),
        }));
      } catch (error) {
        console.warn('Test tab lease could not be written:', error);
      }
    }

    releaseTabLease() {
      try {
        const current = JSON.parse(localStorage.getItem(this.tabLockKey) || '{}');
        if (current.tabId === this.tabId) localStorage.removeItem(this.tabLockKey);
      } catch (error) {
        // A malformed or unavailable localStorage entry should not block exit.
      }
    }

    blockForAnotherTab() {
      if (this.tabBlocked || this.navigatingAway) return;
      this.tabBlocked = true;
      window.clearTimeout(this.autosaveTimer);
      window.clearInterval(this.autosaveInterval);
      window.clearInterval(this.timerHandle);
      window.clearInterval(this.tabLeaseInterval);
      document.body.classList.add('test-tab-conflict');

      let overlay = document.getElementById('testTabConflict');
      if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'testTabConflict';
        overlay.className = 'test-tab-conflict-overlay';
        overlay.innerHTML = `
          <section class="test-tab-conflict-card" role="alertdialog" aria-modal="true" aria-labelledby="test-tab-conflict-title">
            <span>Attempt protection</span>
            <h2 id="test-tab-conflict-title">This module is open in another tab</h2>
            <p>The newer tab now controls autosave. Keeping two active tabs can overwrite answers.</p>
            <button type="button" data-take-over-tab>Use this tab instead</button>
          </section>`;
        document.body.appendChild(overlay);
        overlay.querySelector('[data-take-over-tab]')?.addEventListener('click', () => {
          this.tabBlocked = false;
          this.writeTabLease();
          window.location.reload();
        });
      }
    }

    activateTabLease() {
      this.writeTabLease();
      this.tabLeaseInterval = window.setInterval(() => {
        if (!this.tabBlocked) this.writeTabLease();
      }, 3000);

      window.addEventListener('storage', (event) => {
        if (event.key !== this.tabLockKey || !event.newValue) return;
        try {
          const lease = JSON.parse(event.newValue);
          if (lease.tabId && lease.tabId !== this.tabId && Date.now() - Number(lease.timestamp || 0) < 10000) {
            this.blockForAnotherTab();
          }
        } catch (error) {
          console.warn('Invalid test tab lease:', error);
        }
      });
      window.addEventListener('pagehide', () => this.releaseTabLease());
    }

    bindEvents() {
      document.querySelectorAll('.rect-question').forEach((button, index) => {
        button.addEventListener('click', () => {
          this.goTo(index);
          this.closeQuestionModal();
        });
      });
      document.querySelector('[data-confirm-submit]')?.addEventListener('click', () => this.submitModule(true));
      document.querySelectorAll('[data-cancel-submit]').forEach((button) => {
        button.addEventListener('click', () => this.closeFinishSummary());
      });
      document.getElementById('finishSummaryModal')?.addEventListener('click', (event) => {
        if (event.target.id === 'finishSummaryModal') this.closeFinishSummary();
      });
      document.getElementById('questionModal')?.addEventListener('click', (event) => {
        if (event.target.id === 'questionModal') this.closeQuestionModal();
      });

      document.querySelectorAll('[data-test-exit]').forEach((link) => {
        link.addEventListener('click', async (event) => {
          if (this.submitInProgress) {
            event.preventDefault();
            return;
          }
          if (!window.confirm('Leave this module? Your latest answers will be saved, but the timer will keep running.')) {
            event.preventDefault();
            return;
          }
          event.preventDefault();
          await this.autosave(true);
          this.navigatingAway = true;
          window.location.assign(link.href);
        });
      });

      document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
          this.closeQuestionModal();
          this.closeFinishSummary();
          this.options.onEscape?.(this);
          return;
        }
        const openModal = document.querySelector('.test-flow-modal.is-open');
        if (openModal) return;
        if (this.options.isToolFocused?.()) return;
        const target = event.target;
        const typing = target && (
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable ||
          (target.tagName === 'INPUT' && target.type !== 'radio')
        );
        if (typing) return;
        if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
          event.preventDefault();
          this.previous();
        } else if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
          event.preventDefault();
          this.next();
        } else if (/^[a-d]$/i.test(event.key) && !this.options.isWrittenQuestion?.(this)) {
          event.preventDefault();
          this.selectChoice(event.key.toUpperCase());
        } else if (event.key.toLowerCase() === 'm') {
          event.preventDefault();
          this.toggleMarked();
        }
      });

      window.addEventListener('beforeunload', (event) => {
        this.saveLocal();
        this.options.beforeUnload?.(this);
        if (!this.navigatingAway && !this.submitInProgress) {
          event.preventDefault();
          event.returnValue = '';
        }
      });
      document.addEventListener('visibilitychange', () => {
        this.flushActiveTime();
        this.pageWasVisible = document.visibilityState !== 'hidden';
        this.lastTickAt = Date.now();
        this.updateTimer();
        if (!this.pageWasVisible) {
          this.saveLocal();
          this.autosave(true);
        }
      });
      window.addEventListener('offline', () => this.setSaveState('offline', 'Offline · saved on device'));
      window.addEventListener('online', () => {
        this.setSaveState('saving', 'Reconnecting…');
        this.autosave(true);
      });
    }

    bindPublicApi() {
      window.loadQuestion = (index) => this.goTo(index);
      window.nextQuestion = () => this.next();
      window.prevQuestion = () => this.previous();
      window.markForReview = () => this.toggleMarked();
      window.finishTest = (force) => this.submitModule(Boolean(force));
      window.toggleQuestionModal = () => this.toggleQuestionModal();
      window.closeQuestionModal = () => this.closeQuestionModal();
      window.openQuestionModal = () => this.openQuestionModal();
      window.getMakonIssueContext = () => {
        const question = this.questions[this.currentQuestionIndex] || {};
        return {
          surface: 'test',
          test: this.config.testName,
          section: this.config.sectionName,
          module: this.config.moduleName,
          attempt_id: this.config.attemptId || null,
          classroom_id: this.config.classroomId || null,
          question_id: question.id || null,
          question_number: question.number || this.currentQuestionIndex + 1,
          selected_answer: this.answers[this.currentQuestionIndex] == null
            ? ''
            : String(this.answers[this.currentQuestionIndex]).slice(0, 2000),
        };
      };
    }

    boot() {
      if (this.booted) return;
      this.booted = true;
      if (!this.questionCount) {
        const questionText = document.getElementById('question-text');
        if (questionText) questionText.textContent = 'No questions were found for this module.';
        return;
      }
      this.closeFinishSummary();
      this.closeQuestionModal();
      this.activateTabLease();
      this.bindEvents();
      this.goTo(this.currentQuestionIndex, 'next');
      this.updateTimer();
      this.timerHandle = window.setInterval(() => this.updateTimer(), 500);
      this.autosaveInterval = window.setInterval(() => this.autosave(), 20000);
      this.setSaveState(navigator.onLine ? 'saved' : 'offline', navigator.onLine ? (this.lastSavedAt ? 'Saved' : 'Ready') : 'Offline · saved on device');
      document.body.classList.add('test-flow-ready');
      this.options.afterBoot?.(this);
    }
  }

  window.SATTestCore = SATTestCore;
  window.SATTestUtils = { normalizeChoice, parseJsonScript };
})();
