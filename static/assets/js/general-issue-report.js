(function(){
  function isVisibleFloatingButton(el){
    if(!el) return false;
    const style = window.getComputedStyle(el);
    if(style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity || '1') === 0) return false;
    if(el.classList.contains('scroll-top')) return el.classList.contains('active');
    if(el.hasAttribute('data-back-to-top')) return el.classList.contains('is-visible');
    return true;
  }

  function bindFabStacking(fab){
    if(!fab) return;
    const candidates = () => [
      document.querySelector('[data-back-to-top]'),
      document.querySelector('.scroll-top')
    ].filter(Boolean);

    const updateFabPosition = () => {
      let bottom = window.innerWidth <= 560 ? 12 : 22;
      candidates().forEach((button) => {
        if(!isVisibleFloatingButton(button)) return;
        const rect = button.getBoundingClientRect();
        const stackBottom = Math.max(0, window.innerHeight - rect.top) + 14;
        bottom = Math.max(bottom, stackBottom);
      });
      fab.style.bottom = `${bottom}px`;
    };

    updateFabPosition();
    window.addEventListener('scroll', updateFabPosition, { passive:true });
    window.addEventListener('resize', updateFabPosition);
    const observer = new MutationObserver(updateFabPosition);
    candidates().forEach((button) => observer.observe(button, { attributes:true, attributeFilter:['class','style','hidden'] }));
  }

  function init(){
    const openButtons=document.querySelectorAll('[data-issue-report-open]');
    const backdrop=document.querySelector('[data-issue-report-backdrop]');
    const fab=document.querySelector('.issue-report-fab');
    if(!openButtons.length||!backdrop||backdrop.dataset.bound==='1')return;
    backdrop.dataset.bound='1';
    bindFabStacking(fab);
    const close=backdrop.querySelector('[data-issue-report-close]');
    const form=backdrop.querySelector('[data-issue-report-form]');
    const status=backdrop.querySelector('[data-issue-report-status]');
    const pageUrl=backdrop.querySelector('[data-issue-page-url]');
    const pageTitle=backdrop.querySelector('[data-issue-page-title]');
    const issueContext=backdrop.querySelector('[data-issue-context]');
    const setOpen=(value)=>{
      backdrop.hidden=!value;
      document.body.style.overflow=value?'hidden':'';
      if(value){
        if(pageUrl) pageUrl.value=location.href;
        if(pageTitle) pageTitle.value=document.title;
        let context={};
        try{ if(typeof window.getMakonIssueContext==='function') context=window.getMakonIssueContext()||{}; }
        catch(error){ console.warn('Issue context unavailable',error); }
        if(issueContext) issueContext.value=JSON.stringify(context);
        setTimeout(()=>backdrop.querySelector('textarea[name="message"]')?.focus(),30);
      }
    };
    openButtons.forEach(btn=>btn.addEventListener('click',()=>setOpen(true)));
    close?.addEventListener('click',()=>setOpen(false));
    backdrop.addEventListener('click',e=>{if(e.target===backdrop)setOpen(false)});
    document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!backdrop.hidden)setOpen(false)});
    form?.addEventListener('submit',async e=>{
      e.preventDefault();
      status.textContent='Sending...';
      const submit=form.querySelector('button[type="submit"]');
      if(submit) submit.disabled=true;
      try{
        const response=await fetch(form.action,{method:'POST',body:new FormData(form),headers:{'X-Requested-With':'XMLHttpRequest'}});
        const data=await response.json();
        if(!response.ok||!data.ok) throw new Error(data.error||'Could not send report.');
        status.textContent='Report sent. Thank you.';
        const messageField = form.querySelector('textarea[name="message"]');
        if(messageField) messageField.value='';
        setTimeout(()=>setOpen(false),900)
      }catch(err){
        status.textContent=err.message||'Could not send report.'
      }finally{
        if(submit) submit.disabled=false;
      }
    });
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
