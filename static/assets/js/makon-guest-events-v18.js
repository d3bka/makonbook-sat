(function(){
  'use strict';
  const form=document.querySelector('[data-guest-start-form]');
  if(!form)return;
  form.addEventListener('submit',function(){
    const button=form.querySelector('[data-start-event-button]');
    if(!button||button.disabled)return;
    button.disabled=true;
    button.dataset.originalText=button.textContent;
    button.textContent='Starting…';
  });
  window.addEventListener('pageshow',function(){
    const button=form.querySelector('[data-start-event-button]');
    if(button){button.disabled=false;button.textContent=button.dataset.originalText||'Start event';}
  });
})();
