(function(){
  function init(){
    const watcher = document.querySelector('[data-membership-status-watch]');
    if(!watcher) return;

    const refreshMs = Math.max(3000, Number(watcher.dataset.refreshMs || 5000));
    let timer = null;

    const schedule = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        const joinInput = document.querySelector('input[name="join_code"]');
        const userIsTyping = joinInput && (
          document.activeElement === joinInput || joinInput.value.trim().length > 0
        );

        if(document.visibilityState === 'visible' && !userIsTyping){
          window.location.reload();
        } else {
          schedule();
        }
      }, refreshMs);
    };

    document.addEventListener('visibilitychange', () => {
      if(document.visibilityState === 'visible') schedule();
    });

    schedule();
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', init);
  }else{
    init();
  }
})();
