(function(){
  'use strict';

  const STORAGE_KEY='makonbook.review.answersHidden';
  const root=document.documentElement;
  const toggle=document.querySelector('[data-review-answer-toggle]');
  const label=toggle&&toggle.querySelector('[data-review-answer-toggle-label]');

  function answersAreHidden(){
    return root.classList.contains('review-answers-hidden');
  }

  function renderToggle(){
    if(!toggle)return;
    const hidden=answersAreHidden();
    toggle.setAttribute('aria-pressed',hidden?'true':'false');
    toggle.setAttribute('aria-label',hidden?'Show answers and explanation':'Hide answers and explanation');
    if(label)label.textContent=hidden?'Show answers':'Hide answers';
  }

  function setAnswersHidden(hidden,persist){
    root.classList.toggle('review-answers-hidden',Boolean(hidden));
    renderToggle();
    if(persist!==false){
      try{localStorage.setItem(STORAGE_KEY,hidden?'1':'0');}catch(error){}
    }
  }

  if(toggle){
    renderToggle();
    toggle.addEventListener('click',function(){
      setAnswersHidden(!answersAreHidden(),true);
    });
  }

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
    }else if(event.key.toLowerCase()==='h'&&toggle){
      event.preventDefault();
      setAnswersHidden(!answersAreHidden(),true);
      toggle.focus({preventScroll:true});
    }
  });
})();
