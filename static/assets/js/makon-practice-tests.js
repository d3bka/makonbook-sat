(function(){
  'use strict';

  function initPracticePage(){
    const page = document.querySelector('[data-practice-page]');
    if(!page) return;

    const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const pageKey = page.dataset.pageKey || 'global';

    // Content is visible by default. JS only adds enhancement animations, so a
    // missing/cached/broken script can never leave the page blank again.
    const revealItems = Array.from(page.querySelectorAll('[data-practice-reveal]'));
    if(!reduceMotion){
      revealItems.forEach((item, index) => {
        item.style.setProperty('--practice-reveal-delay', `${Math.min(index, 5) * 70}ms`);
        item.classList.add('practice-reveal-run');
      });
    }

    function directTabContainer(group){
      return Array.from(group.children).find(child => child.classList && child.classList.contains('practice-tabs')) || null;
    }

    function directPanelsContainer(group){
      return Array.from(group.children).find(child => child.classList && child.classList.contains('practice-panels')) || null;
    }

    function getTabs(group){
      const container = directTabContainer(group);
      return container ? Array.from(container.querySelectorAll('[data-practice-tab]')) : [];
    }

    function getPanels(group){
      const container = directPanelsContainer(group);
      return container ? Array.from(container.children).filter(child => child.hasAttribute('data-practice-panel')) : [];
    }

    function activateTab(group, targetName, persist){
      const tabs = getTabs(group);
      const panels = getPanels(group);
      const next = panels.find(panel => panel.dataset.practicePanel === targetName);
      if(!next) return;

      tabs.forEach(tab => {
        const active = tab.dataset.practiceTab === targetName;
        tab.classList.toggle('is-active', active);
        tab.setAttribute('aria-selected', String(active));
        tab.tabIndex = active ? 0 : -1;
      });

      panels.forEach(panel => {
        const active = panel === next;
        panel.hidden = !active;
        panel.classList.toggle('is-active', active);
      });

      if(persist && group.dataset.practiceGroup === 'tests'){
        try{
          sessionStorage.setItem(`makonbook:practice-tab:${pageKey}`, targetName);
        }catch(_error){
          // Storage can be unavailable in strict/incognito environments.
        }
      }
    }

    page.querySelectorAll('[data-practice-group]').forEach(group => {
      const tabs = getTabs(group);
      if(!tabs.length) return;

      tabs.forEach((tab, index) => {
        tab.addEventListener('click', () => activateTab(group, tab.dataset.practiceTab, true));
        tab.addEventListener('keydown', event => {
          if(event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
          event.preventDefault();
          const step = event.key === 'ArrowRight' ? 1 : -1;
          const nextIndex = (index + step + tabs.length) % tabs.length;
          tabs[nextIndex].focus();
          activateTab(group, tabs[nextIndex].dataset.practiceTab, true);
        });
      });

      let initial = tabs.find(tab => tab.classList.contains('is-active'))?.dataset.practiceTab || tabs[0].dataset.practiceTab;
      if(group.dataset.practiceGroup === 'tests'){
        try{
          const saved = sessionStorage.getItem(`makonbook:practice-tab:${pageKey}`);
          if(saved && tabs.some(tab => tab.dataset.practiceTab === saved)) initial = saved;
        }catch(_error){
          // Keep server-rendered active tab.
        }
      }
      activateTab(group, initial, false);
    });

    const testsGroup = page.querySelector('[data-practice-group="tests"]');
    const searchInput = testsGroup ? testsGroup.querySelector('[data-practice-search]') : null;
    const clearButton = testsGroup ? testsGroup.querySelector('[data-practice-search-clear]') : null;

    function filterTests(){
      if(!testsGroup || !searchInput) return;
      const query = searchInput.value.trim().toLocaleLowerCase();
      if(clearButton) clearButton.hidden = !query;

      testsGroup.querySelectorAll('[data-practice-panel]').forEach(panel => {
        const cards = Array.from(panel.querySelectorAll('[data-practice-card]'));
        let visible = 0;

        cards.forEach(card => {
          const haystack = (card.dataset.search || '').toLocaleLowerCase();
          const matches = !query || haystack.includes(query);
          card.hidden = !matches;
          card.style.display = matches ? '' : 'none';
          if(matches) visible += 1;
        });

        const searchEmpty = panel.querySelector('[data-practice-search-empty]');
        const nativeEmpty = panel.querySelector('[data-practice-native-empty]');
        if(searchEmpty){
          const showSearchEmpty = Boolean(query) && cards.length > 0 && visible === 0;
          searchEmpty.hidden = !showSearchEmpty;
        }
        if(nativeEmpty){
          nativeEmpty.hidden = Boolean(query) && cards.length > 0;
        }
      });
    }

    if(searchInput){
      let searchFrame = 0;
      const scheduleFilter = () => {
        if(searchFrame) cancelAnimationFrame(searchFrame);
        searchFrame = requestAnimationFrame(filterTests);
      };
      searchInput.addEventListener('input', scheduleFilter);
      searchInput.addEventListener('search', scheduleFilter);
      if(clearButton){
        clearButton.addEventListener('click', () => {
          searchInput.value = '';
          filterTests();
          searchInput.focus();
        });
      }
      filterTests();
    }

    let navigationLocked = false;
    page.querySelectorAll('[data-practice-navigate]').forEach(link => {
      link.addEventListener('click', event => {
        if(navigationLocked || link.classList.contains('is-loading')){
          event.preventDefault();
          return;
        }
        navigationLocked = true;
        link.classList.add('is-loading');
        link.setAttribute('aria-busy', 'true');
        const label = link.querySelector('span');
        if(label){
          label.dataset.originalText = label.textContent || '';
          label.textContent = 'Opening…';
        }
      });
    });

    function resetNavigationState(){
      navigationLocked = false;
      page.querySelectorAll('[data-practice-navigate].is-loading').forEach(link => {
        link.classList.remove('is-loading');
        link.removeAttribute('aria-busy');
        const label = link.querySelector('span');
        if(label && label.dataset.originalText){
          label.textContent = label.dataset.originalText;
          delete label.dataset.originalText;
        }
      });
    }

    window.addEventListener('pageshow', resetNavigationState);
  }

  function safeInit(){
    try{
      initPracticePage();
    }catch(error){
      // The server-rendered page remains fully visible and usable.
      console.error('Practice Tests enhancement failed:', error);
      document.querySelectorAll('[data-practice-reveal]').forEach(item => {
        item.style.opacity = '1';
        item.style.transform = 'none';
      });
      document.querySelectorAll('[data-practice-panel].is-active').forEach(panel => {
        panel.hidden = false;
      });
    }
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', safeInit, { once:true });
  }else{
    safeInit();
  }
})();
