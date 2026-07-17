(function(){
  'use strict';
  document.addEventListener('DOMContentLoaded',function(){
    document.querySelectorAll('[data-start-test-link]').forEach(function(link){
      link.addEventListener('click',function(event){
        if(link.dataset.opening==='1'){
          event.preventDefault();
          return;
        }
        link.dataset.opening='1';
        link.classList.add('is-loading');
        const original=link.innerHTML;
        link.innerHTML='<i class="fa fa-circle-o-notch fa-spin" aria-hidden="true"></i> Opening…';
        window.setTimeout(function(){
          if(document.visibilityState==='visible'){
            link.dataset.opening='0';
            link.classList.remove('is-loading');
            link.innerHTML=original;
          }
        },8000);
      });
    });
  });
})();
