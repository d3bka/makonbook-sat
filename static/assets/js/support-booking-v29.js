(function () {
  'use strict';

  function qs(selector, root) {
    return (root || document).querySelector(selector);
  }

  function qsa(selector, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(selector));
  }

  function activateDateTab(button) {
    var target = button.getAttribute('data-support-date-target');
    qsa('[data-support-date-target]').forEach(function (item) {
      item.classList.toggle('is-active', item === button);
      item.setAttribute('aria-selected', item === button ? 'true' : 'false');
    });
    qsa('[data-support-date-panel]').forEach(function (panel) {
      panel.classList.toggle('is-active', panel.getAttribute('data-support-date-panel') === target);
    });
  }

  function activateTab(button) {
    var group = button.closest('[data-support-tabs]');
    if (!group) return;
    var target = button.getAttribute('data-support-tab-target');
    qsa('[data-support-tab-target]', group).forEach(function (item) {
      item.classList.toggle('is-active', item === button);
    });
    var panelsRoot = group.parentElement;
    qsa('[data-support-tab-panel]', panelsRoot).forEach(function (panel) {
      panel.classList.toggle('is-active', panel.getAttribute('data-support-tab-panel') === target);
    });
  }

  function openModal(modal) {
    if (!modal) return;
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    document.documentElement.style.overflow = 'hidden';
    var focusTarget = qs('textarea, input, button', modal);
    if (focusTarget) window.setTimeout(function () { focusTarget.focus(); }, 20);
  }

  function closeModal(modal) {
    if (!modal) return;
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    document.documentElement.style.overflow = '';
  }

  function selectedSlotSummary(form) {
    var checked = qs('input[name="slot"]:checked', form);
    if (!checked) return null;
    return {
      date: checked.getAttribute('data-slot-date') || '',
      time: checked.getAttribute('data-slot-time') || ''
    };
  }

  function bindBookingConfirmation() {
    qsa('[data-support-booking-form]').forEach(function (form) {
      form.addEventListener('submit', function (event) {
        if (form.getAttribute('data-confirmed') === '1') return;
        var summary = selectedSlotSummary(form);
        if (!summary) {
          event.preventDefault();
          var firstTab = qs('[data-support-date-target]', form);
          if (firstTab) firstTab.scrollIntoView({ behavior: 'smooth', block: 'center' });
          window.alert('Choose an available lesson time first.');
          return;
        }

        var modal = qs('#supportBookingConfirmModal');
        if (!modal) return;
        event.preventDefault();
        var dateNode = qs('[data-confirm-date]', modal);
        var timeNode = qs('[data-confirm-time]', modal);
        var topic = qs('[name="topic"]', form);
        var topicNode = qs('[data-confirm-topic]', modal);
        if (dateNode) dateNode.textContent = summary.date;
        if (timeNode) timeNode.textContent = summary.time;
        if (topicNode && topic) topicNode.textContent = topic.options[topic.selectedIndex].text;
        modal._supportForm = form;
        openModal(modal);
      });
    });

    var confirmButton = qs('[data-confirm-booking]');
    if (confirmButton) {
      confirmButton.addEventListener('click', function () {
        var modal = confirmButton.closest('.support-modal');
        var form = modal && modal._supportForm;
        if (!form) return;
        confirmButton.disabled = true;
        confirmButton.textContent = 'Booking…';
        form.setAttribute('data-confirmed', '1');
        form.submit();
      });
    }
  }

  function bindCancellationModals() {
    qsa('[data-open-cancel-modal]').forEach(function (button) {
      button.addEventListener('click', function () {
        var modal = qs('#supportCancelModal');
        if (!modal) return;
        var form = qs('form', modal);
        if (form) form.action = button.getAttribute('data-cancel-url');
        var teacher = qs('[data-cancel-teacher]', modal);
        var time = qs('[data-cancel-time]', modal);
        if (teacher) teacher.textContent = button.getAttribute('data-cancel-teacher') || '';
        if (time) time.textContent = button.getAttribute('data-cancel-time') || '';
        openModal(modal);
      });
    });
  }

  function bindModalControls() {
    qsa('[data-close-support-modal]').forEach(function (button) {
      button.addEventListener('click', function () {
        closeModal(button.closest('.support-modal'));
      });
    });
    qsa('.support-modal').forEach(function (modal) {
      modal.addEventListener('click', function (event) {
        if (event.target === modal) closeModal(modal);
      });
    });
    document.addEventListener('keydown', function (event) {
      if (event.key !== 'Escape') return;
      qsa('.support-modal.is-open').forEach(closeModal);
    });
  }

  function bindSubmitLocks() {
    qsa('form[data-support-lock-submit]').forEach(function (form) {
      form.addEventListener('submit', function () {
        var button = qs('button[type="submit"]', form);
        if (!button || button.disabled) return;
        button.disabled = true;
        button.setAttribute('aria-busy', 'true');
        var label = button.getAttribute('data-loading-label');
        if (label) button.textContent = label;
      });
    });
  }

  function updateCountdowns() {
    qsa('[data-support-countdown]').forEach(function (node) {
      var value = node.getAttribute('data-support-countdown');
      var target = new Date(value);
      if (Number.isNaN(target.getTime())) return;
      var diff = target.getTime() - Date.now();
      if (diff <= 0) {
        node.textContent = 'Starting now';
        return;
      }
      var minutes = Math.floor(diff / 60000);
      var days = Math.floor(minutes / 1440);
      var hours = Math.floor((minutes % 1440) / 60);
      var mins = minutes % 60;
      if (days > 0) node.textContent = days + 'd ' + hours + 'h remaining';
      else if (hours > 0) node.textContent = hours + 'h ' + mins + 'm remaining';
      else node.textContent = mins + 'm remaining';
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    qsa('[data-support-date-target]').forEach(function (button) {
      button.addEventListener('click', function () { activateDateTab(button); });
    });
    qsa('[data-support-tab-target]').forEach(function (button) {
      button.addEventListener('click', function () { activateTab(button); });
    });
    bindBookingConfirmation();
    bindCancellationModals();
    bindModalControls();
    bindSubmitLocks();
    updateCountdowns();
    window.setInterval(updateCountdowns, 60000);
  });
})();
