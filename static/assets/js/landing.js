(() => {
  document.documentElement.classList.add('js-ready');

  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const header = document.querySelector('[data-header]');
  const navToggle = document.querySelector('[data-nav-toggle]');
  const nav = document.querySelector('[data-nav]');

  const setHeaderState = () => {
    if (!header) return;
    header.classList.toggle('is-scrolled', window.scrollY > 18);
  };

  setHeaderState();
  window.addEventListener('scroll', setHeaderState, { passive: true });

  if (navToggle && nav) {
    navToggle.addEventListener('click', () => {
      const isOpen = nav.classList.toggle('is-open');
      navToggle.classList.toggle('is-active', isOpen);
      navToggle.setAttribute('aria-expanded', String(isOpen));
    });

    nav.querySelectorAll('a').forEach((link) => {
      link.addEventListener('click', () => {
        nav.classList.remove('is-open');
        navToggle.classList.remove('is-active');
        navToggle.setAttribute('aria-expanded', 'false');
      });
    });
  }

  const navLinks = Array.from(document.querySelectorAll('.site-nav a[href^="#"]'));
  const navTargets = navLinks
    .map((link) => ({
      link,
      section: document.querySelector(link.getAttribute('href')),
    }))
    .filter((item) => item.section);

  let navTicking = false;

  const markActiveNav = (activeId) => {
    navTargets.forEach(({ link }) => {
      const isActive = link.getAttribute('href') === `#${activeId}`;
      link.classList.toggle('is-active', isActive);
      if (isActive) {
        link.setAttribute('aria-current', 'page');
      } else {
        link.removeAttribute('aria-current');
      }
    });
  };

  const setActiveNav = () => {
    if (!navTargets.length) return;

    const focusLine = Math.min(window.innerHeight * 0.42, 360);
    const pageBottom = window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 8;

    if (pageBottom) {
      markActiveNav(navTargets[navTargets.length - 1].section.id);
      return;
    }

    let activeId = navTargets[0].section.id;
    let bestDistance = Number.POSITIVE_INFINITY;

    navTargets.forEach(({ section }) => {
      const rect = section.getBoundingClientRect();
      const crossesFocusLine = rect.top <= focusLine && rect.bottom >= focusLine;
      const distance = crossesFocusLine ? -1 : Math.abs((rect.top + rect.height * 0.33) - focusLine);

      if (distance < bestDistance) {
        bestDistance = distance;
        activeId = section.id;
      }
    });

    markActiveNav(activeId);
  };

  const requestActiveNavUpdate = () => {
    if (navTicking) return;
    navTicking = true;
    requestAnimationFrame(() => {
      setActiveNav();
      navTicking = false;
    });
  };

  navTargets.forEach(({ link, section }) => {
    link.addEventListener('click', () => {
      markActiveNav(section.id);
      window.setTimeout(setActiveNav, 450);
    });
  });

  setActiveNav();
  window.addEventListener('scroll', requestActiveNavUpdate, { passive: true });
  window.addEventListener('resize', setActiveNav);

  const backToTop = document.querySelector('[data-back-to-top]');
  let topButtonTicking = false;

  const setBackToTopState = () => {
    if (!backToTop) return;
    backToTop.classList.toggle('is-visible', window.scrollY > Math.min(420, window.innerHeight * 0.52));
  };

  const requestTopButtonUpdate = () => {
    if (topButtonTicking) return;
    topButtonTicking = true;
    requestAnimationFrame(() => {
      setBackToTopState();
      topButtonTicking = false;
    });
  };

  if (backToTop) {
    setBackToTopState();
    window.addEventListener('scroll', requestTopButtonUpdate, { passive: true });

    backToTop.addEventListener('click', (event) => {
      event.preventDefault();
      backToTop.classList.add('is-boosting');
      window.setTimeout(() => backToTop.classList.remove('is-boosting'), 620);
      window.scrollTo({ top: 0, behavior: prefersReducedMotion ? 'auto' : 'smooth' });
    });
  }

  const revealItems = document.querySelectorAll('[data-reveal], .reveal-up, .reveal-scale');
  if (prefersReducedMotion || !('IntersectionObserver' in window)) {
    revealItems.forEach((item) => item.classList.add('is-visible'));
  } else {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.16, rootMargin: '0px 0px -50px 0px' });

    revealItems.forEach((item) => observer.observe(item));
  }

  document.querySelectorAll('[data-stagger]').forEach((group) => {
    Array.from(group.children).forEach((child, index) => {
      child.style.setProperty('--delay', `${index * 90}ms`);
    });
  });

  const counters = document.querySelectorAll('[data-counter]');
  counters.forEach((counter) => {
    const target = Number(counter.dataset.counter || '0');
    counter.textContent = target.toLocaleString('en-US');
  });

  const runCounter = (counter) => {
    const target = Number(counter.dataset.counter || '0');
    const duration = 1100;
    const start = performance.now();
    counter.textContent = '0';

    const step = (now) => {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      counter.textContent = Math.round(target * eased).toLocaleString('en-US');
      if (progress < 1) requestAnimationFrame(step);
    };

    requestAnimationFrame(step);
  };

  if (prefersReducedMotion || !('IntersectionObserver' in window)) {
    counters.forEach((counter) => {
      counter.textContent = Number(counter.dataset.counter || '0').toLocaleString('en-US');
    });
  } else {
    const counterObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          runCounter(entry.target);
          counterObserver.unobserve(entry.target);
        }
      });
    }, { threshold: 0.45 });

    counters.forEach((counter) => counterObserver.observe(counter));
  }

  document.querySelectorAll('[data-tilt]').forEach((card) => {
    if (prefersReducedMotion) return;

    card.addEventListener('mousemove', (event) => {
      const rect = card.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - 0.5;
      const y = (event.clientY - rect.top) / rect.height - 0.5;
      card.style.setProperty('--tilt-x', `${y * -5}deg`);
      card.style.setProperty('--tilt-y', `${x * 6}deg`);
    });

    card.addEventListener('mouseleave', () => {
      card.style.setProperty('--tilt-x', '0deg');
      card.style.setProperty('--tilt-y', '0deg');
    });
  });

  document.querySelectorAll('details.faq-item').forEach((item) => {
    item.classList.toggle('is-open', item.open);

    item.addEventListener('toggle', () => {
      item.classList.toggle('is-open', item.open);

      if (!item.open) return;
      document.querySelectorAll('details.faq-item[open]').forEach((other) => {
        if (other !== item) other.removeAttribute('open');
      });
    });
  });
})();
