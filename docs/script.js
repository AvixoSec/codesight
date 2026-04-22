/* CodeSight editorial preview - wow-grade
   ==========================================================================
   Preserved features
     - progress bar, TOC activation, dark toggle, stats count-up,
       footnote tooltips, smooth-scroll, FAQ a11y, pip copy, generic copy,
       date/time box, reading-time, word count, keyboard nav
   New in this revision
     - live GitHub metrics (5-min sessionStorage cache, AbortController)
     - architecture SVG: scroll-triggered draw + periodic pulse dots
       + node hover tooltips
     - magnetic buttons (rAF, pointer:fine)
     - custom cursor (pointer:fine, lerp 0.15, hover ring / click flash)
     - variable-font animation on <h1.display> and on <em>
     - scroll-driven palette wash (body hue modulation via CSS var)
     - TOC per-section progress bar + hover "N min" tooltip
     - opt-in Web Audio paper-fold sounds (FAQ, dark toggle, copy, markers)
     - interactive code example: hover/focus bug markers with tooltip
     - <kbd> pulse while Ctrl/Cmd held (priority-2)
   Notes
     - fully vanilla; no dependencies
     - prefers-reduced-motion disables: magnetic, cursor, pulses, palette wash,
       variable-font transitions
*/

(function(){
  'use strict';

  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const finePointer = window.matchMedia('(pointer: fine)').matches;
  const doc = document.documentElement;
  const body = document.body;

  /* HTML sanitiser: strips <script>, event handlers and javascript: URLs
     before an innerHTML assignment. Content here is authored by us, but
     defence-in-depth guards against a future dynamic source. */
  function sanitizeHtml(html){
    const tpl = document.createElement('template');
    tpl.innerHTML = String(html);
    const walker = document.createTreeWalker(tpl.content, NodeFilter.SHOW_ELEMENT);
    const remove = [];
    let node = walker.nextNode();
    while (node){
      const tag = node.tagName;
      if (tag === 'SCRIPT' || tag === 'IFRAME' || tag === 'OBJECT' || tag === 'EMBED'){
        remove.push(node);
      } else {
        for (const attr of Array.from(node.attributes)){
          const n = attr.name.toLowerCase();
          const v = (attr.value || '').trim().toLowerCase();
          if (n.startsWith('on') || ((n === 'href' || n === 'src' || n === 'xlink:href') && v.startsWith('javascript:'))){
            node.removeAttribute(attr.name);
          }
        }
      }
      node = walker.nextNode();
    }
    remove.forEach(n => n.remove());
    return tpl.innerHTML;
  }

  /* ==================================================================
     I18N - RU / EN (persisted)
     ==================================================================*/
  const LANG_KEY = 'codesight-editorial-lang';

  const DICT = {
    ru: {
      // GitHub strip
      stars: 'звёзд',
      issues: 'открытых issue',
      lastCommit: 'последний коммит',
      release: 'релиз',
      // Reading / word count
      minRead: 'мин чтения',
      readingTime: 'Время чтения &asymp; ',
      readingTimeSuffix: ' мин',
      wordsSuffix: ' слов',
      wordsPrefix: '~',
      // Copy
      copy: 'копировать',
      copied: 'скопировано',
      copyBtn: 'Копировать',
      copiedBtn: 'Скопировано',
      // Terminal
      provider: 'провайдер',
      demo: 'демо',
      complete: 'готово',
      // Bug tip fix label (also used as CSS var)
      fixLabel: 'Фикс - ',
      // TLDR
      ahead: 'Дальше: ',
      aheadEnd: 'Это конец. Попробуй команду установки сверху.',
      // Sound toggle tooltip states
      soundOn: 'Звуки включены',
      soundOff: 'Звуки выключены',
      // Page meta
      title: 'CodeSight - CLI для LLM-анализа кода',
      desc: 'Опенсорсная утилита командной строки. Гоняет код через большие языковые модели и находит реальные баги, дыры в безопасности и архитектурные проблемы.',
      // Relative time
      justNow: 'только что',
      ago: 'назад',
      // Bug tooltips
      bug1Title: 'SQL-инъекция: user_id вставляется прямо в запрос.',
      bug1Fix: 'Используй параметризованный запрос: cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))',
      bug2Title: 'Захардкоженный секрет: ключ подписи закоммичен в исходники.',
      bug2Fix: 'Читай из os.environ или secret-менеджера; проротируй значение, которое только что утекло.',
      bug3Title: 'Обход аутентификации: любой запрос с заголовком X-Debug получает права админа.',
      bug3Fix: 'Завязывай ветку на app.debug и реальную проверку auth, а не на заголовок от клиента.',
      // TLDR chips
      tldrIdea: 'идея',
      tldrCmds: '9 команд',
      tldrCompare: 'vs semgrep / CodeQL',
      tldrProviders: '16 провайдеров',
      tldrArch: 'пайплайн на странице',
      tldrSpot: '3 скрытых бага',
      tldrExample: 'вывод SARIF',
      tldrWhy: '4 решения',
      tldrTimeline: 'v0.1 → v0.3',
      tldrFaq: 'вопросы',
    },
    en: {
      stars: 'stars',
      issues: 'open issues',
      lastCommit: 'last commit',
      release: 'release',
      minRead: 'min read',
      readingTime: 'Reading time &asymp; ',
      readingTimeSuffix: ' min',
      wordsSuffix: ' words',
      wordsPrefix: '~',
      copy: 'copy',
      copied: 'copied',
      copyBtn: 'Copy',
      copiedBtn: 'Copied',
      provider: 'provider',
      demo: 'live demo',
      complete: 'complete',
      fixLabel: 'Fix - ',
      ahead: 'Up next: ',
      aheadEnd: 'That is the end. Try the install snippet up top.',
      soundOn: 'Sound on',
      soundOff: 'Sound off',
      title: 'CodeSight - CLI for LLM-powered code analysis',
      desc: 'An open-source command-line tool. Runs your code through large language models and surfaces real bugs, security holes, and architecture issues.',
      justNow: 'just now',
      ago: 'ago',
      bug1Title: 'SQL injection: user_id is concatenated straight into the query.',
      bug1Fix: 'Use a parameterised query: cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))',
      bug2Title: 'Hardcoded secret: a signing key is committed in source.',
      bug2Fix: 'Read from os.environ or a secret manager; rotate the value that just leaked.',
      bug3Title: 'Auth bypass: any request with the X-Debug header gets admin rights.',
      bug3Fix: 'Gate on app.debug and a real auth check, not on a client-supplied header.',
      tldrIdea: 'the idea',
      tldrCmds: '9 commands',
      tldrCompare: 'vs semgrep / CodeQL',
      tldrProviders: '16 providers',
      tldrArch: 'pipeline on a page',
      tldrSpot: '3 hidden bugs',
      tldrExample: 'SARIF output',
      tldrWhy: '4 decisions',
      tldrTimeline: 'v0.1 → v0.3',
      tldrFaq: 'questions',
    }
  };

  let currentLang = (function(){
    try {
      const s = localStorage.getItem(LANG_KEY);
      if (s === 'ru' || s === 'en') return s;
    } catch(_) {}
    return (navigator.language && navigator.language.toLowerCase().startsWith('ru')) ? 'ru' : 'en';
  })();

  function t(key){
    const d = DICT[currentLang] || DICT.en;
    return (key in d) ? d[key] : (DICT.en[key] !== undefined ? DICT.en[key] : key);
  }

  function applyLang(lang){
    if (lang !== 'ru' && lang !== 'en') lang = 'en';
    currentLang = lang;
    try { localStorage.setItem(LANG_KEY, lang); } catch(_){}
    doc.setAttribute('lang', lang);

    // textContent / innerHTML via data-i18n-{lang}
    const attr = 'data-i18n-' + lang;
    document.querySelectorAll('[' + attr + ']').forEach(el => {
      const v = el.getAttribute(attr);
      if (v !== null) el.innerHTML = sanitizeHtml(v);
    });

    // special attrs: aria-label, title, placeholder
    ['aria-label', 'title', 'placeholder'].forEach(a => {
      const sel = '[data-i18n-' + a + '-' + lang + ']';
      document.querySelectorAll(sel).forEach(el => {
        const v = el.getAttribute('data-i18n-' + a + '-' + lang);
        if (v !== null) el.setAttribute(a, v);
      });
    });

    // SVG data-tip attribute (architecture nodes)
    document.querySelectorAll('[data-tip-' + lang + ']').forEach(el => {
      const v = el.getAttribute('data-tip-' + lang);
      if (v !== null) el.setAttribute('data-tip', v);
    });

    // <title> + <meta name="description">
    document.title = t('title');
    const metaDesc = document.querySelector('meta[name="description"]');
    if (metaDesc) metaDesc.setAttribute('content', t('desc'));

    // CSS var for bug-tip ::before "Фикс - " / "Fix - "
    doc.style.setProperty('--bug-fix-label', '"' + t('fixLabel') + '"');

    // button label (shows what it will switch TO)
    const btn = document.getElementById('lang-toggle');
    if (btn) btn.textContent = lang === 'ru' ? 'EN' : 'RU';

    // notify listeners so dynamic text can re-render
    window.dispatchEvent(new CustomEvent('langchange', { detail: { lang } }));
  }

  // early apply (html[lang] already set by inline head script; we sync textContent now)
  applyLang(currentLang);

  // language toggle button handler
  const langBtn = document.getElementById('lang-toggle');
  if (langBtn){
    langBtn.addEventListener('click', () => {
      applyLang(currentLang === 'ru' ? 'en' : 'ru');
    });
  }

  // update inline TOC "N мин" labels on lang change (small on-hover chips)
  function refreshTocTipLabels(){
    document.querySelectorAll('.toc a .toc-tip[data-mins]').forEach(el => {
      const m = el.getAttribute('data-mins');
      if (m) el.textContent = m + ' ' + t('minRead');
    });
  }
  refreshTocTipLabels();
  window.addEventListener('langchange', refreshTocTipLabels);

  // pre-localise terminal provider label before the scene loop starts
  (function initTermProvLabel(){
    const htProvEarly = document.getElementById('ht-prov');
    if (htProvEarly) htProvEarly.textContent = t('provider') + ' · anthropic';
  })();

  /* ==================================================================
     THEME TOGGLE (persisted)
     ==================================================================*/
  const THEME_KEY = 'codesight-editorial-theme';
  const themeBtn = document.getElementById('theme-toggle');
  function applyTheme(theme){
    if (theme === 'dark') doc.setAttribute('data-theme', 'dark');
    else doc.removeAttribute('data-theme');
    if (themeBtn){
      themeBtn.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');
    }
  }
  const storedTheme = (function(){
    try { return localStorage.getItem(THEME_KEY); } catch(_) { return null; }
  })();
  if (storedTheme === 'dark' || storedTheme === 'light'){
    applyTheme(storedTheme);
  } else {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    applyTheme(prefersDark ? 'dark' : 'light');
  }
  if (themeBtn){
    themeBtn.addEventListener('click', () => {
      const next = doc.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      applyTheme(next);
      try { localStorage.setItem(THEME_KEY, next); } catch(_) {}
      sound.play('fold');
    });
  }

  /* ==================================================================
     WEB AUDIO "PAPER" SYNTHS (opt-in via localStorage)
     ==================================================================*/
  const SOUND_KEY = 'codesight-editorial-sound';
  const sound = (function(){
    let ctx = null;
    let enabled = false;
    try {
      const s = localStorage.getItem(SOUND_KEY);
      enabled = s === 'on';
    } catch(_) {}
    if (enabled) body.classList.add('sound-on');

    function ensureCtx(){
      if (ctx) return ctx;
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      ctx = new AC();
      return ctx;
    }

    /* each "event" is a tiny enveloped blip.
       we mimic paper by stacking filtered noise + a soft sine click.  */
    function burst(freq, dur, type, vol, detune){
      if (!enabled) return;
      const c = ensureCtx();
      if (!c) return;
      if (c.state === 'suspended') c.resume();

      const now = c.currentTime;

      // tone
      const osc = c.createOscillator();
      const gain = c.createGain();
      osc.type = type || 'sine';
      osc.frequency.setValueAtTime(freq, now);
      if (typeof detune === 'number') osc.detune.setValueAtTime(detune, now);
      gain.gain.setValueAtTime(0, now);
      gain.gain.linearRampToValueAtTime(vol, now + 0.006);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + dur);
      osc.connect(gain).connect(c.destination);
      osc.start(now);
      osc.stop(now + dur + 0.02);

      // shaped noise (paper-ish)
      const bufSize = Math.max(1, Math.floor(c.sampleRate * dur));
      const buf = c.createBuffer(1, bufSize, c.sampleRate);
      const data = buf.getChannelData(0);
      for (let i = 0; i < bufSize; i++){
        data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / bufSize, 2);
      }
      const noise = c.createBufferSource();
      noise.buffer = buf;
      const hp = c.createBiquadFilter();
      hp.type = 'highpass';
      hp.frequency.setValueAtTime(1800, now);
      const noiseGain = c.createGain();
      noiseGain.gain.setValueAtTime(0, now);
      noiseGain.gain.linearRampToValueAtTime(vol * 0.6, now + 0.004);
      noiseGain.gain.exponentialRampToValueAtTime(0.0001, now + dur * 0.8);
      noise.connect(hp).connect(noiseGain).connect(c.destination);
      noise.start(now);
      noise.stop(now + dur);
    }

    const api = {
      toggle(){
        enabled = !enabled;
        try { localStorage.setItem(SOUND_KEY, enabled ? 'on' : 'off'); } catch(_){}
        if (enabled){
          body.classList.add('sound-on');
          ensureCtx();
          // confirmation blip
          api.play('fold');
        } else {
          body.classList.remove('sound-on');
        }
        return enabled;
      },
      isOn(){ return enabled; },
      play(kind){
        if (!enabled) return;
        switch(kind){
          case 'fold':   burst(440,  0.08, 'sine',     0.05); break;
          case 'open':   burst(340,  0.09, 'sine',     0.05, 8); break;
          case 'close':  burst(280,  0.08, 'sine',     0.05, -8); break;
          case 'copy':   burst(700,  0.04, 'triangle', 0.04); break;
          case 'marker': burst(920,  0.035,'sine',     0.03); break;
          case 'click':  burst(520,  0.05, 'triangle', 0.04); break;
          default: break;
        }
      }
    };
    return api;
  })();

  const soundBtn = document.getElementById('sound-toggle');
  if (soundBtn){
    soundBtn.setAttribute('aria-pressed', sound.isOn() ? 'true' : 'false');
    soundBtn.addEventListener('click', () => {
      const on = sound.toggle();
      soundBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
      soundBtn.setAttribute('title', on ? t('soundOn') : t('soundOff'));
    });
  }

  /* ==================================================================
     PIP COPY + CURSOR LABEL
     ==================================================================*/
  const pip = document.getElementById('pip');
  const pipCursor = document.getElementById('pip-cursor');
  if (pip){
    pip.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText('pip install codesight'); } catch(_){}
      const c = pip.querySelector('.copy');
      c.textContent = t('copied');
      pip.classList.add('copied');
      sound.play('copy');
      setTimeout(() => { c.textContent = t('copy'); pip.classList.remove('copied'); }, 1300);
    });
    if (pipCursor){
      pip.addEventListener('mouseenter', () => {
        if (pip.classList.contains('copied')) return;
        pipCursor.classList.add('visible');
      });
      pip.addEventListener('mouseleave', () => pipCursor.classList.remove('visible'));
      pip.addEventListener('mousemove', e => {
        pipCursor.style.left = e.clientX + 'px';
        pipCursor.style.top = e.clientY + 'px';
      });
    }
  }

  /* ==================================================================
     GENERIC CODE-BLOCK COPY
     ==================================================================*/
  document.querySelectorAll('.copy-btn[data-copy-target]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const sel = btn.getAttribute('data-copy-target');
      const el = document.querySelector(sel);
      if (!el) return;
      const txt = el.innerText.trim();
      try { await navigator.clipboard.writeText(txt); } catch(_){}
      btn.textContent = t('copiedBtn');
      btn.classList.add('copied');
      sound.play('copy');
      setTimeout(() => {
        // restore to the localised default via applyLang-managed attr
        const cur = currentLang;
        const fresh = btn.getAttribute('data-i18n-' + cur);
        btn.textContent = fresh || t('copyBtn');
        btn.classList.remove('copied');
      }, 1300);
    });
  });

  /* ==================================================================
     SCROLL PROGRESS + PALETTE WASH + SECTION PROGRESS (SINGLE rAF)
     ==================================================================*/
  const fill = document.getElementById('progress-fill');
  const sections = Array.from(document.querySelectorAll('section[data-sec]'));
  const tocBox = document.getElementById('toc');
  const tocLinks = tocBox ? Array.from(tocBox.querySelectorAll('a[data-sec]')) : [];
  const tocMap = new Map();
  tocLinks.forEach(a => tocMap.set(a.dataset.sec, a));
  let tickScheduled = false;
  function scheduleTick(){
    if (tickScheduled) return;
    tickScheduled = true;
    requestAnimationFrame(onTick);
  }
  function onTick(){
    tickScheduled = false;
    const winH = window.innerHeight;
    const scrollY = window.scrollY;
    const total = doc.scrollHeight - doc.clientHeight;
    const pct = total > 0 ? scrollY / total : 0;

    // progress bar
    if (fill) fill.style.width = (pct * 100).toFixed(2) + '%';

    // palette wash - radial center moves + slight intensity curve
    // lightness drifts +/- 2% between top and middle of the page
    if (!reduce){
      const waveY = 20 + pct * 60; // 20% → 80%
      doc.style.setProperty('--wash-y', waveY + '%');
      const inten = 0.6 + Math.sin(pct * Math.PI) * 0.6; // 0.6 → 1.2
      doc.style.setProperty('--wash-opacity', inten.toFixed(3));
    }

    // TOC reveal + active section progress
    if (tocBox) tocBox.classList.toggle('visible', scrollY > 260);

    // compute which section is active + its within-section progress
    let activeIdx = -1;
    for (let i = 0; i < sections.length; i++){
      const r = sections[i].getBoundingClientRect();
      if (r.top <= winH * 0.4){ activeIdx = i; }
    }
    tocLinks.forEach(a => {
      a.classList.remove('active');
      a.style.setProperty('--sec-p', 0);
    });
    if (activeIdx !== -1){
      const sec = sections[activeIdx];
      const secId = sec.getAttribute('data-sec');
      const link = tocMap.get(secId);
      if (link){
        link.classList.add('active');
        const r = sec.getBoundingClientRect();
        const h = sec.offsetHeight || 1;
        // 0 when section top is at viewport.top+40%, 1 when it exits at viewport.top-0
        const p = Math.min(1, Math.max(0, (winH * 0.4 - r.top) / h));
        link.style.setProperty('--sec-p', p.toFixed(3));
      }
    }

  }
  window.addEventListener('scroll', scheduleTick, { passive: true });
  window.addEventListener('resize', scheduleTick, { passive: true });
  scheduleTick();

  /* ==================================================================
     SECTION REVEAL VIA IO (unchanged)
     ==================================================================*/
  if (reduce){
    sections.forEach(s => s.classList.add('visible'));
  } else {
    const revealIO = new IntersectionObserver(entries => {
      for (const e of entries){
        if (e.isIntersecting){
          e.target.classList.add('visible');
          revealIO.unobserve(e.target);
        }
      }
    }, { threshold: 0.12 });
    sections.forEach(s => revealIO.observe(s));
  }

  /* ==================================================================
     DATE + READING TIME + WORD COUNT (lang-aware)
     ==================================================================*/
  const dateBox = document.getElementById('datebox');
  const DATE_NAMES = {
    ru: {
      days: ['воскресенье','понедельник','вторник','среда','четверг','пятница','суббота'],
      months: ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря']
    },
    en: {
      days: ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'],
      months: ['January','February','March','April','May','June','July','August','September','October','November','December']
    }
  };
  function renderDate(){
    if (!dateBox) return;
    const d = new Date();
    const names = DATE_NAMES[currentLang] || DATE_NAMES.en;
    const day = names.days[d.getDay()];
    const month = names.months[d.getMonth()];
    const hh = String(d.getHours()).padStart(2,'0');
    const mm = String(d.getMinutes()).padStart(2,'0');
    if (currentLang === 'en'){
      dateBox.textContent = `${day}, ${month} ${d.getDate()} ${d.getFullYear()} - ${hh}:${mm}`;
    } else {
      dateBox.textContent = `${day}, ${d.getDate()} ${month} ${d.getFullYear()} - ${hh}:${mm}`;
    }
  }
  renderDate();
  setInterval(renderDate, 30 * 1000);

  // word count (computed once from body text)
  const words = body.innerText.trim().split(/\s+/).length;
  const minutes = Math.max(1, Math.round(words / 220));
  const rt = document.getElementById('read-time');
  const wc = document.getElementById('word-count');
  function renderReadingAndWords(){
    if (rt) rt.innerHTML = t('readingTime') + minutes + t('readingTimeSuffix');
    if (wc){
      const rounded = Math.round(words / 50) * 50;
      wc.textContent = t('wordsPrefix') + rounded.toLocaleString() + t('wordsSuffix');
    }
  }
  renderReadingAndWords();
  window.addEventListener('langchange', () => {
    renderDate();
    renderReadingAndWords();
  });

  /* ==================================================================
     STATS COUNT-UP
     ==================================================================*/
  const stats = Array.from(document.querySelectorAll('.stats .num[data-count]'));
  function animateStat(el){
    const target = parseFloat(el.getAttribute('data-count'));
    if (!isFinite(target)) return;
    const prefix = el.getAttribute('data-prefix') || '';
    const suffix = el.getAttribute('data-suffix') || '';
    const decimals = parseInt(el.getAttribute('data-decimals') || '0', 10);
    const duration = 1100;
    const start = performance.now();
    function tick(now){
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      const value = target * eased;
      const formatted = value.toFixed(decimals);
      el.innerHTML = prefix + formatted + (suffix ? `<span class="unit">${suffix}</span>` : '');
      if (t < 1) requestAnimationFrame(tick);
      else el.innerHTML = prefix + target.toFixed(decimals) + (suffix ? `<span class="unit">${suffix}</span>` : '');
    }
    requestAnimationFrame(tick);
  }
  if (stats.length && !reduce){
    const statsIO = new IntersectionObserver(entries => {
      for (const e of entries){
        if (e.isIntersecting){
          animateStat(e.target);
          statsIO.unobserve(e.target);
        }
      }
    }, { threshold: 0.6 });
    stats.forEach(s => statsIO.observe(s));
  }

  /* ==================================================================
     KEYBOARD NAV (arrow keys between sections)
     ==================================================================*/
  function currentSectionIdx(){
    const y = window.scrollY + window.innerHeight * 0.35;
    let idx = 0;
    sections.forEach((s, i) => {
      if (s.offsetTop <= y) idx = i;
    });
    return idx;
  }
  document.addEventListener('keydown', e => {
    const t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    e.preventDefault();
    const idx = currentSectionIdx();
    const target = e.key === 'ArrowDown'
      ? sections[Math.min(sections.length - 1, idx + 1)]
      : sections[Math.max(0, idx - 1)];
    if (target) target.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  });

  /* ==================================================================
     PRIORITY-2 #13 : <kbd> PULSE ON CTRL/CMD HELD
     ==================================================================*/
  document.addEventListener('keydown', e => {
    if (e.key === 'Control' || e.key === 'Meta'){
      body.classList.add('meta-held');
    }
  });
  document.addEventListener('keyup', e => {
    if (e.key === 'Control' || e.key === 'Meta'){
      body.classList.remove('meta-held');
    }
  });
  window.addEventListener('blur', () => body.classList.remove('meta-held'));

  /* ==================================================================
     FOOTNOTE TOOLTIPS (unchanged, plus focus support)
     ==================================================================*/
  const tip = document.getElementById('fn-tip');
  document.querySelectorAll('.footnote[data-note]').forEach(fn => {
    function showTip(){
      const note = fn.getAttribute('data-note');
      if (!note || !tip) return;
      tip.innerHTML = sanitizeHtml(note);
      const r = fn.getBoundingClientRect();
      const tipW = tip.offsetWidth || 200;
      const left = Math.min(window.innerWidth - tipW - 12, Math.max(12, r.left));
      tip.style.left = left + 'px';
      tip.style.top = (r.top + window.scrollY - 44) + 'px';
      tip.classList.add('visible');
    }
    function hideTip(){ if (tip) tip.classList.remove('visible'); }
    fn.addEventListener('mouseenter', showTip);
    fn.addEventListener('mouseleave', hideTip);
    fn.addEventListener('focus', showTip);
    fn.addEventListener('blur', hideTip);
  });

  /* ==================================================================
     SMOOTH SCROLL FOR ANCHORS
     ==================================================================*/
  document.querySelectorAll('a[href^="#"]').forEach(a => {
    a.addEventListener('click', ev => {
      const href = a.getAttribute('href');
      if (!href || href === '#') return;
      const target = document.querySelector(href);
      if (!target) return;
      ev.preventDefault();
      target.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
      if (history.replaceState) history.replaceState(null, '', href);
    });
  });

  /* ==================================================================
     FAQ a11y + paper-fold sound
     ==================================================================*/
  document.querySelectorAll('.faq details').forEach(det => {
    const sum = det.querySelector('summary');
    if (!sum) return;
    const sync = () => sum.setAttribute('aria-expanded', det.open ? 'true' : 'false');
    sync();
    det.addEventListener('toggle', () => {
      sync();
      sound.play(det.open ? 'open' : 'close');
    });
    sum.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' '){
        e.preventDefault();
        det.open = !det.open;
        sync();
      }
    });
  });

  /* ==================================================================
     MAGNETIC BUTTONS (pointer:fine, not reduced-motion)
     ==================================================================*/
  if (finePointer && !reduce){
    const mags = Array.from(document.querySelectorAll('.btn.magnetic'));
    const RADIUS = 90;
    const MAX_SHIFT = 9;
    const state = new Map(); // btn -> {x, y, tx, ty, raf}

    mags.forEach(btn => {
      state.set(btn, { x:0, y:0, tx:0, ty:0, raf:0 });
    });

    function animateBtn(btn){
      const s = state.get(btn);
      if (!s) return;
      s.x += (s.tx - s.x) * 0.18;
      s.y += (s.ty - s.y) * 0.18;
      btn.style.transform = `translate(${s.x.toFixed(2)}px, ${s.y.toFixed(2)}px)`;
      if (Math.abs(s.tx - s.x) > 0.08 || Math.abs(s.ty - s.y) > 0.08){
        s.raf = requestAnimationFrame(() => animateBtn(btn));
      } else {
        s.raf = 0;
        // snap if near-zero
        if (Math.abs(s.tx) < 0.1 && Math.abs(s.ty) < 0.1){
          btn.style.transform = '';
          s.x = 0; s.y = 0;
        }
      }
    }

    document.addEventListener('mousemove', e => {
      mags.forEach(btn => {
        const r = btn.getBoundingClientRect();
        const cx = r.left + r.width / 2;
        const cy = r.top + r.height / 2;
        const dx = e.clientX - cx;
        const dy = e.clientY - cy;
        const dist = Math.hypot(dx, dy);
        const s = state.get(btn);
        if (dist < RADIUS){
          const strength = 1 - dist / RADIUS;
          s.tx = dx * strength * (MAX_SHIFT / RADIUS) * 1.2;
          s.ty = dy * strength * (MAX_SHIFT / RADIUS) * 1.2;
        } else {
          s.tx = 0; s.ty = 0;
        }
        if (!s.raf) s.raf = requestAnimationFrame(() => animateBtn(btn));
      });
    }, { passive: true });

    document.addEventListener('mouseleave', () => {
      mags.forEach(btn => {
        const s = state.get(btn);
        s.tx = 0; s.ty = 0;
        if (!s.raf) s.raf = requestAnimationFrame(() => animateBtn(btn));
      });
    });
  }

  /* ==================================================================
     CUSTOM CURSOR (pointer:fine + not reduced-motion)
     ==================================================================*/
  if (finePointer && !reduce){
    const cd = document.getElementById('cursor-dot');
    const cr = document.getElementById('cursor-ring');
    if (cd && cr){
      let mx = -100, my = -100;        // raw
      let rx = -100, ry = -100;        // ring lerp
      let dx = -100, dy = -100;        // dot follows faster
      let active = false;

      function loop(){
        rx += (mx - rx) * 0.15;
        ry += (my - ry) * 0.15;
        dx += (mx - dx) * 0.35;
        dy += (my - dy) * 0.35;
        cr.style.transform = `translate(${rx}px, ${ry}px) translate(-50%,-50%)`;
        cd.style.transform = `translate(${dx}px, ${dy}px) translate(-50%,-50%)`;
        requestAnimationFrame(loop);
      }
      requestAnimationFrame(loop);

      document.addEventListener('mousemove', e => {
        mx = e.clientX; my = e.clientY;
        if (!active){
          active = true;
          body.classList.add('cursor-active');
          // seed lerp values so the first move isn't a jump
          rx = mx; ry = my; dx = mx; dy = my;
        }
      }, { passive: true });

      document.addEventListener('mouseleave', () => {
        body.classList.remove('cursor-active');
        active = false;
      });

      const hoverSel = 'a, button, .btn, .pip, .marker, summary, .footnote, .compat-row span, .arch-node';
      document.addEventListener('mouseover', e => {
        if (e.target.closest(hoverSel)) body.classList.add('cursor-hover');
      });
      document.addEventListener('mouseout', e => {
        if (e.target.closest(hoverSel)) body.classList.remove('cursor-hover');
      });
      document.addEventListener('mousedown', () => {
        body.classList.add('cursor-click');
        setTimeout(() => body.classList.remove('cursor-click'), 180);
      });
    }
  }

  /* ==================================================================
     VARIABLE-FONT ANIMATION ON H1 (on hover + subtle scroll reaction)
     ==================================================================*/
  if (!reduce){
    const h1 = document.getElementById('display-h1');
    if (h1){
      h1.addEventListener('mouseenter', () => {
        doc.style.setProperty('--h1-opsz', '96');
        setTimeout(() => doc.style.setProperty('--h1-opsz', '144'), 650);
      });
    }
  }

  /* ==================================================================
     GITHUB LIVE METRICS (5-min sessionStorage cache)
     ==================================================================*/
  const GH_CACHE_KEY = 'codesight-editorial-gh';
  const GH_CACHE_TTL = 5 * 60 * 1000;
  const ghStrip = document.getElementById('gh-strip');
  const ghLoading = document.getElementById('gh-loading');

  function relativeTime(iso){
    const ts = new Date(iso).getTime();
    const diff = Date.now() - ts;
    if (!isFinite(ts) || diff < 0) return '';
    const s = Math.floor(diff / 1000);
    if (s < 60) return t('justNow');
    const m = Math.floor(s / 60);

    if (currentLang === 'ru'){
      function plural(n, forms){
        const mod10 = n % 10;
        const mod100 = n % 100;
        if (mod10 === 1 && mod100 !== 11) return forms[0];
        if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return forms[1];
        return forms[2];
      }
      if (m < 60) return m + ' ' + plural(m, ['минуту','минуты','минут']) + ' назад';
      const h = Math.floor(m / 60);
      if (h < 24) return h + ' ' + plural(h, ['час','часа','часов']) + ' назад';
      const d = Math.floor(h / 24);
      if (d < 30) return d + ' ' + plural(d, ['день','дня','дней']) + ' назад';
      const mo = Math.floor(d / 30);
      if (mo < 12) return mo + ' ' + plural(mo, ['месяц','месяца','месяцев']) + ' назад';
      const y = Math.floor(mo / 12);
      return y + ' ' + plural(y, ['год','года','лет']) + ' назад';
    }
    // English
    function engForm(n, singular, plural){ return n === 1 ? singular : plural; }
    if (m < 60) return m + ' ' + engForm(m, 'minute', 'minutes') + ' ago';
    const h = Math.floor(m / 60);
    if (h < 24) return h + ' ' + engForm(h, 'hour', 'hours') + ' ago';
    const d = Math.floor(h / 24);
    if (d < 30) return d + ' ' + engForm(d, 'day', 'days') + ' ago';
    const mo = Math.floor(d / 30);
    if (mo < 12) return mo + ' ' + engForm(mo, 'month', 'months') + ' ago';
    const y = Math.floor(mo / 12);
    return y + ' ' + engForm(y, 'year', 'years') + ' ago';
  }

  let lastGHData = null;
  function renderGH(data){
    if (!ghStrip) return;
    lastGHData = data;
    ghStrip.classList.add('populated');
    ghStrip.innerHTML = '';

    const items = [];
    if (typeof data.stars === 'number'){
      items.push(`<span class="gh-chip"><span class="v">★ ${data.stars.toLocaleString()}</span><span class="l">${t('stars')}</span></span>`);
    }
    if (typeof data.issues === 'number'){
      items.push(`<span class="gh-chip"><span class="v">${data.issues}</span><span class="l">${t('issues')}</span></span>`);
    }
    if (data.lastCommit){
      items.push(`<span class="gh-chip relative"><span class="l">${t('lastCommit')}</span><span class="v">${relativeTime(data.lastCommit)}</span></span>`);
    }
    if (data.release){
      const rel = `<span class="gh-chip relative"><span class="l">${t('release')}</span><span class="v">${data.release.tag}</span><span class="l">- ${relativeTime(data.release.date)}</span></span>`;
      items.push(rel);
    }

    ghStrip.innerHTML = items.join('<span class="sep"></span>');
  }
  window.addEventListener('langchange', () => {
    if (lastGHData) renderGH(lastGHData);
  });

  function hideGH(){
    if (ghStrip){
      ghStrip.style.display = 'none';
      ghStrip.setAttribute('aria-hidden', 'true');
    }
  }

  function tryCachedGH(){
    try {
      const raw = sessionStorage.getItem(GH_CACHE_KEY);
      if (!raw) return null;
      const obj = JSON.parse(raw);
      if (!obj || typeof obj.t !== 'number') return null;
      if (Date.now() - obj.t > GH_CACHE_TTL) return null;
      return obj.d;
    } catch(_) { return null; }
  }
  function saveCachedGH(d){
    try { sessionStorage.setItem(GH_CACHE_KEY, JSON.stringify({ t: Date.now(), d })); } catch(_){}
  }

  async function fetchGH(){
    if (!ghStrip) return;

    const cached = tryCachedGH();
    if (cached){ renderGH(cached); return; }

    const ctrl = new AbortController();
    const tmo = setTimeout(() => ctrl.abort(), 4000);
    const base = 'https://api.github.com/repos/AvixoSec/codesight';

    try {
      const [repoRes, commitsRes, releaseRes] = await Promise.allSettled([
        fetch(base, { signal: ctrl.signal, headers: { 'Accept': 'application/vnd.github+json' } }),
        fetch(base + '/commits?per_page=1', { signal: ctrl.signal, headers: { 'Accept': 'application/vnd.github+json' } }),
        fetch(base + '/releases/latest', { signal: ctrl.signal, headers: { 'Accept': 'application/vnd.github+json' } })
      ]);
      clearTimeout(tmo);

      const d = {};

      if (repoRes.status === 'fulfilled' && repoRes.value.ok){
        const repo = await repoRes.value.json();
        if (typeof repo.stargazers_count === 'number') d.stars = repo.stargazers_count;
        if (typeof repo.open_issues_count === 'number') d.issues = repo.open_issues_count;
      }
      if (commitsRes.status === 'fulfilled' && commitsRes.value.ok){
        const commits = await commitsRes.value.json();
        if (Array.isArray(commits) && commits[0] && commits[0].commit && commits[0].commit.author){
          d.lastCommit = commits[0].commit.author.date;
        }
      }
      if (releaseRes.status === 'fulfilled' && releaseRes.value.ok){
        const rel = await releaseRes.value.json();
        if (rel && rel.tag_name && rel.published_at){
          d.release = { tag: rel.tag_name, date: rel.published_at };
        }
      }

      if (!d.stars && !d.issues && !d.lastCommit && !d.release){
        hideGH();
        return;
      }
      saveCachedGH(d);
      renderGH(d);
    } catch(err){
      clearTimeout(tmo);
      hideGH();
    }
  }
  // kick off after first paint
  if (document.readyState === 'complete') fetchGH();
  else window.addEventListener('load', fetchGH, { once: true });

  /* ==================================================================
     ARCHITECTURE SVG: SCROLL-TRIGGERED DRAW + PULSE + NODE TOOLTIPS
     ==================================================================*/
  const archSvg = document.getElementById('arch-svg');
  const archTip = document.getElementById('arch-tip');
  const archPulses = document.getElementById('arch-pulses');
  if (archSvg){
    // measure each stroke-path and set per-element --len
    const strokes = Array.from(archSvg.querySelectorAll('.arch-draw'));
    strokes.forEach((el, i) => {
      let len = 0;
      try {
        if (typeof el.getTotalLength === 'function'){
          len = el.getTotalLength();
        }
      } catch(_) {}
      if (!len || !isFinite(len)){
        // rough fallback using bounding box
        const r = el.getBBox ? el.getBBox() : null;
        if (r) len = 2 * (r.width + r.height);
        else len = 400;
      }
      el.style.setProperty('--len', len.toFixed(2));
      // staggered transition delay along the pipeline (0..1s)
      el.style.transitionDelay = (reduce ? 0 : (i * 0.018)).toFixed(3) + 's';
    });

    if (reduce){
      archSvg.classList.add('drawn');
    } else {
      const archIO = new IntersectionObserver(entries => {
        for (const e of entries){
          if (e.isIntersecting && e.intersectionRatio >= 0.5){
            archSvg.classList.add('drawn');
            archIO.disconnect();
            // start pulse loop shortly after the lines finish drawing
            setTimeout(startArchPulses, 1700);
            break;
          }
        }
      }, { threshold: [0, 0.25, 0.5, 0.75, 1] });
      archIO.observe(archSvg);
    }

    // pulse dots along the forward-pipeline path
    function startArchPulses(){
      if (!archPulses) return;
      const path = document.getElementById('arch-pulse-path');
      if (!path) return;
      let totalLen = 0;
      try { totalLen = path.getTotalLength(); } catch(_){ return; }
      if (!totalLen) return;

      const SVG_NS = 'http://www.w3.org/2000/svg';

      function emit(){
        if (document.hidden) return;
        const dot = document.createElementNS(SVG_NS, 'circle');
        dot.setAttribute('r', '3');
        dot.setAttribute('class', 'pulse-dot');
        archPulses.appendChild(dot);
        const start = performance.now();
        const dur = 2400;
        (function step(now){
          const t = Math.min(1, (now - start) / dur);
          const eased = t;
          const pt = path.getPointAtLength(eased * totalLen);
          dot.setAttribute('cx', pt.x);
          dot.setAttribute('cy', pt.y);
          // fade in/out
          const alpha = t < 0.15 ? t / 0.15 : (t > 0.85 ? (1 - t) / 0.15 : 1);
          dot.setAttribute('opacity', alpha.toFixed(3));
          if (t < 1 && !document.hidden){
            requestAnimationFrame(step);
          } else {
            dot.remove();
          }
        })(start);
      }
      // space them so roughly 1 dot in flight at a time
      emit();
      setInterval(() => {
        if (!document.hidden) emit();
      }, 2800);
    }

    // node hover tooltips (pointer + keyboard focus)
    const nodes = Array.from(archSvg.querySelectorAll('.arch-node[data-tip]'));
    function showArchTip(node, ev){
      if (!archTip) return;
      archTip.textContent = node.getAttribute('data-tip') || '';
      let x, y;
      if (ev && 'clientX' in ev){
        x = ev.clientX + 12;
        y = ev.clientY + 14;
      } else {
        const r = node.getBoundingClientRect();
        x = r.left + r.width / 2;
        y = r.top + r.height + 6;
      }
      const tw = archTip.offsetWidth || 200;
      x = Math.min(window.innerWidth - tw - 12, Math.max(12, x));
      archTip.style.left = x + 'px';
      archTip.style.top = y + 'px';
      archTip.classList.add('visible');
    }
    function hideArchTip(){
      if (archTip) archTip.classList.remove('visible');
    }
    nodes.forEach(n => {
      n.addEventListener('mouseenter', ev => showArchTip(n, ev));
      n.addEventListener('mousemove', ev => showArchTip(n, ev));
      n.addEventListener('mouseleave', hideArchTip);
    });
  }

  /* ==================================================================
     INTERACTIVE CODE EXAMPLE - BUG MARKERS
     ==================================================================*/
  function bugInfo(num){
    const bugs = {
      '1': { sev: 'CRITICAL', sevClass: '', cwe: 'CWE-89 / OWASP A03',
             title: t('bug1Title'), fix: t('bug1Fix') },
      '2': { sev: 'CRITICAL', sevClass: '', cwe: 'CWE-798',
             title: t('bug2Title'), fix: t('bug2Fix') },
      '3': { sev: 'HIGH',     sevClass: 'high', cwe: 'CWE-287',
             title: t('bug3Title'), fix: t('bug3Fix') }
    };
    return bugs[num] || null;
  }
  const bugTip = document.getElementById('bug-tip');
  const markers = Array.from(document.querySelectorAll('.codex .marker'));
  if (bugTip && markers.length){
    const btSev = bugTip.querySelector('.bt-sev');
    const btCwe = bugTip.querySelector('.bt-cwe');
    const btTitle = bugTip.querySelector('.bt-title');
    const btFix = bugTip.querySelector('.bt-fix');

    function showBug(marker){
      const num = marker.getAttribute('data-bug-num');
      const info = bugInfo(num);
      if (!info) return;
      btSev.textContent = info.sev;
      btSev.className = 'bt-sev ' + (info.sevClass || '');
      btCwe.textContent = info.cwe;
      btTitle.textContent = info.title;
      btFix.textContent = info.fix;

      const r = marker.getBoundingClientRect();
      const tw = bugTip.offsetWidth || 280;
      const th = bugTip.offsetHeight || 120;
      // prefer: to the right of the marker; flip if overflow
      let x = r.right + 14;
      let y = r.top - 8;
      if (x + tw > window.innerWidth - 12){
        x = r.left - tw - 14;
      }
      if (x < 12) x = 12;
      if (y + th > window.innerHeight - 12){
        y = window.innerHeight - th - 12;
      }
      if (y < 12) y = 12;
      bugTip.style.left = x + 'px';
      bugTip.style.top = y + 'px';
      bugTip.classList.add('visible');
      bugTip.setAttribute('aria-hidden', 'false');
      sound.play('marker');
    }
    function hideBug(){
      bugTip.classList.remove('visible');
      bugTip.setAttribute('aria-hidden', 'true');
    }

    markers.forEach(m => {
      m.addEventListener('mouseenter', () => showBug(m));
      m.addEventListener('mouseleave', hideBug);
      m.addEventListener('focus', () => showBug(m));
      m.addEventListener('blur', hideBug);
      // keyboard: Enter/Space toggles, so pressing on a focused marker fires
      // the paper sound again
      m.addEventListener('keydown', ev => {
        if (ev.key === 'Enter' || ev.key === ' '){
          ev.preventDefault();
          showBug(m);
        } else if (ev.key === 'Escape'){
          hideBug();
          m.blur();
        }
      });
    });

    // hide when mouse leaves the code block
    const codex = document.getElementById('codex');
    if (codex){
      codex.addEventListener('mouseleave', hideBug);
    }
  }

  /* ==================================================================
     TOC COLLAPSE TOGGLE
     ==================================================================*/
  const tocToggleBtn = document.getElementById('toc-toggle');
  if (tocToggleBtn && tocBox){
    const TOC_COLLAPSE_KEY = 'codesight-editorial-toc-collapsed';
    try {
      if (localStorage.getItem(TOC_COLLAPSE_KEY) === '1'){
        tocBox.classList.add('collapsed');
        tocToggleBtn.setAttribute('aria-expanded', 'false');
        const ch = tocToggleBtn.querySelector('.toc-chev');
        if (ch) ch.innerHTML = '+';
      }
    } catch(_){}
    tocToggleBtn.addEventListener('click', () => {
      const collapsed = tocBox.classList.toggle('collapsed');
      tocToggleBtn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      const ch = tocToggleBtn.querySelector('.toc-chev');
      if (ch) ch.innerHTML = collapsed ? '+' : '−';
      try { localStorage.setItem(TOC_COLLAPSE_KEY, collapsed ? '1' : '0'); } catch(_){}
    });
  }

  /* ==================================================================
     TOC HOVER TOOLTIP (min-read per item)
     ==================================================================*/
  const tocMinsTip = document.getElementById('toc-mins-tip');
  if (tocMinsTip && tocLinks.length){
    tocLinks.forEach(a => {
      const miniTip = a.querySelector('.toc-tip');
      a.addEventListener('mouseenter', () => {
        const m = miniTip ? miniTip.getAttribute('data-mins') : null;
        if (!m) return;
        tocMinsTip.textContent = m + ' ' + t('minRead');
        const r = a.getBoundingClientRect();
        tocMinsTip.style.left = (r.left - tocMinsTip.offsetWidth - 8) + 'px';
        tocMinsTip.style.top = (r.top + r.height / 2 - 10) + 'px';
        tocMinsTip.classList.add('visible');
      });
      a.addEventListener('mouseleave', () => tocMinsTip.classList.remove('visible'));
    });
  }

  /* ==================================================================
     HERO EDITORIAL TERMINAL - cycling demo
     ==================================================================*/
  const htScreen = document.getElementById('ht-screen');
  const htProv = document.getElementById('ht-prov');
  const htHint = document.getElementById('ht-hint');
  if (htScreen){
    const scenes = [
      {
        provName: 'anthropic',
        lines: [
          {prompt:'$', cmd:'codesight security src/api.py', flag:'--format sarif'},
          {type:'out-dim', text:'CodeSight 0.3.0 · model=claude-opus-4.6 · 238 LOC · 3.1s'},
          {type:'gap'},
          {type:'crit', text:'CRITICAL  src/api.py:47  SQL injection · CWE-89'},
          {type:'out-dim', text:'  › user_id concatenated into SELECT via f-string'},
          {type:'gap'},
          {type:'crit', text:'CRITICAL  src/api.py:112  Hardcoded secret · CWE-798'},
          {type:'out-dim', text:'  › AWS access key in source. Rotate + move to vault.'},
          {type:'gap'},
          {type:'high', text:'HIGH      src/api.py:203  Auth bypass · CWE-287'},
          {type:'out-dim', text:'  › X-Debug header skips admin check in prod'},
          {type:'gap'},
          {type:'ok', text:'→ 3 findings written to codesight.sarif'}
        ]
      },
      {
        provName: 'openai',
        lines: [
          {prompt:'$', cmd:'codesight scan .', flag:'--task bugs'},
          {type:'out-dim', text:'CodeSight 0.3.0 · model=gpt-5.4 · 12 files · analysing...'},
          {type:'gap'},
          {type:'out', text:'  ████████████████████████  100%'},
          {type:'out-dim', text:'  api.py   handler.py   queue.py   parser.py'},
          {type:'out-dim', text:'  ... 8 more'},
          {type:'gap'},
          {type:'high', text:'4 bugs found across 3 files'},
          {type:'out-dim', text:'  queue.py:58  race condition on `_pending` dict'},
          {type:'out-dim', text:'  parser.py:33 off-by-one in slice bound'},
          {type:'out-dim', text:'  handler.py:91 resource leak (missing close)'},
          {type:'out-dim', text:'  handler.py:127 silent exception swallowed'},
          {type:'gap'},
          {type:'ok', text:'→ pipeline completed in 11.8s  $0.04'}
        ]
      },
      {
        provName: 'ollama',
        lines: [
          {prompt:'$', cmd:'codesight review handler.py'},
          {type:'out-dim', text:'CodeSight 0.3.0 · model=llama3 · local · 1.9s'},
          {type:'gap'},
          {type:'out', text:'SUMMARY'},
          {type:'out-dim', text:'  Well-structured handler but three concerns:'},
          {type:'gap'},
          {type:'high', text:'  1. handler.py:42  Implicit dependency on global state'},
          {type:'out-dim', text:'     › pass `session` explicitly, not via module'},
          {type:'gap'},
          {type:'high', text:'  2. handler.py:88  Retry logic has no backoff ceiling'},
          {type:'out-dim', text:'     › add max_attempts + jitter'},
          {type:'gap'},
          {type:'ok', text:'→ review complete, 2 issues flagged (medium)'}
        ]
      }
    ];

    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let sceneIdx = 0;
    let running = true;

    const esc = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;');

    async function sleep(ms){
      return new Promise(r => setTimeout(r, ms));
    }

    function renderFast(scene){
      // instant render for reduced-motion
      const html = scene.lines.map(l => {
        if (l.type === 'gap') return '<br>';
        if (l.prompt){
          return `<div><span class="prompt">${l.prompt}</span> <span class="cmd">${esc(l.cmd)}</span>${l.flag ? ' <span class="flag">'+esc(l.flag)+'</span>' : ''}</div>`;
        }
        if (l.type === 'crit') return `<div><span class="crit">${esc(l.text)}</span></div>`;
        if (l.type === 'high') return `<div><span class="high">${esc(l.text)}</span></div>`;
        if (l.type === 'ok') return `<div><span class="ok">${esc(l.text)}</span></div>`;
        if (l.type === 'out-dim') return `<div><span class="dim">${esc(l.text)}</span></div>`;
        return `<div>${esc(l.text || '')}</div>`;
      }).join('');
      htScreen.innerHTML = html;
    }

    async function typeCommand(line, container){
      const wrap = document.createElement('div');
      wrap.innerHTML = `<span class="prompt">${line.prompt}</span> <span class="cmd"></span>`;
      if (line.flag){
        wrap.innerHTML += ` <span class="flag"></span>`;
      }
      const caret = document.createElement('span');
      caret.className = 'cursor';
      wrap.appendChild(caret);
      container.appendChild(wrap);

      const cmdSpan = wrap.querySelector('.cmd');
      for (let i = 0; i < line.cmd.length; i++){
        if (!running) return;
        cmdSpan.textContent += line.cmd[i];
        await sleep(18 + Math.random() * 22);
      }
      if (line.flag){
        const flagSpan = wrap.querySelector('.flag');
        await sleep(140);
        for (let i = 0; i < line.flag.length; i++){
          if (!running) return;
          flagSpan.textContent += line.flag[i];
          await sleep(18 + Math.random() * 22);
        }
      }
      await sleep(260);
      caret.remove();
    }

    async function printLine(line, container){
      await sleep(60 + Math.random() * 60);
      if (!running) return;
      const div = document.createElement('div');
      if (line.type === 'gap'){
        div.innerHTML = '&nbsp;';
      } else if (line.type === 'crit'){
        div.innerHTML = `<span class="crit">${esc(line.text)}</span>`;
      } else if (line.type === 'high'){
        div.innerHTML = `<span class="high">${esc(line.text)}</span>`;
      } else if (line.type === 'ok'){
        div.innerHTML = `<span class="ok">${esc(line.text)}</span>`;
      } else if (line.type === 'out-dim'){
        div.innerHTML = `<span class="dim">${esc(line.text)}</span>`;
      } else {
        div.textContent = line.text || '';
      }
      container.appendChild(div);
    }

    function provLabel(name){
      return t('provider') + ' · ' + name;
    }

    async function playScene(scene){
      htScreen.innerHTML = '';
      if (htProv) htProv.textContent = provLabel(scene.provName);
      if (htHint) htHint.textContent = t('demo');

      if (reduce){
        renderFast(scene);
        await sleep(4500);
        return;
      }

      for (const line of scene.lines){
        if (!running) return;
        if (line.prompt){
          await typeCommand(line, htScreen);
        } else {
          await printLine(line, htScreen);
        }
      }
      if (htHint) htHint.textContent = t('complete');
      await sleep(3400);
    }

    // update terminal labels immediately on lang change
    window.addEventListener('langchange', () => {
      if (htProv && scenes[sceneIdx]) htProv.textContent = provLabel(scenes[sceneIdx].provName);
      // htHint swaps to current-state label: if "complete" was showing, keep it as such;
      // otherwise use 'demo'. Simpler - just re-match existing class/content via DOM.
      if (htHint){
        // Heuristic: if last-rendered hint was "complete" localize to new lang, else demo
        const cur = htHint.textContent;
        if (cur === 'готово' || cur === 'complete'){
          htHint.textContent = t('complete');
        } else {
          htHint.textContent = t('demo');
        }
      }
    });

    async function loop(){
      while (running){
        await playScene(scenes[sceneIdx]);
        if (!running) return;
        // fade gap
        if (!reduce){
          htScreen.style.transition = 'opacity .4s';
          htScreen.style.opacity = '0';
          await sleep(420);
          htScreen.style.opacity = '1';
        }
        sceneIdx = (sceneIdx + 1) % scenes.length;
      }
    }

    // Start when in view, pause when out
    const heroIo = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (e.isIntersecting){
          if (!running){
            running = true;
            loop();
          }
        } else {
          running = false;
        }
      });
    }, {threshold: 0.1});
    heroIo.observe(htScreen.closest('.hero-term') || htScreen);

    // kick off
    loop();
  }

})();
