(function(){
  'use strict';
  document.addEventListener('keydown',function(event){
    const target=event.target;
    const typing=target&&(target.tagName==='INPUT'||target.tagName==='TEXTAREA'||target.tagName==='SELECT'||target.isContentEditable);
    if(typing||event.altKey||event.ctrlKey||event.metaKey)return;
    if(event.key==='ArrowLeft'){
      const link=document.querySelector('[data-review-prev]');
      if(link){event.preventDefault();window.location.assign(link.href);}
    }else if(event.key==='ArrowRight'){
      const link=document.querySelector('[data-review-next]');
      if(link){event.preventDefault();window.location.assign(link.href);}
    }else if(event.key.toLowerCase()==='r'){
      const link=document.querySelector('[data-review-results]')||document.querySelector('.review-title-link');
      if(link){event.preventDefault();window.location.assign(link.href);}
    }
  });
})();
