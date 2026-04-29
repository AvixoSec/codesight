/* =======================================================================
   CodeSight Docs - minimal editorial script
   theme toggle, scroll progress, copy buttons
   ======================================================================= */
(function(){
  'use strict';

  var STORAGE_THEME = 'codesight-editorial-theme';

  /* --- theme (sun/moon, localStorage, prefers-color-scheme) ---------- */
  function applyTheme(theme){
    document.documentElement.setAttribute('data-theme', theme);
  }
  function getInitialTheme(){
    try {
      var stored = localStorage.getItem(STORAGE_THEME);
      if (stored === 'dark' || stored === 'light') return stored;
    } catch(_) {}
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }
    return 'light';
  }
  applyTheme(getInitialTheme());

  document.addEventListener('DOMContentLoaded', function(){
    var themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
      themeToggle.addEventListener('click', function(){
        var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        applyTheme(next);
        try { localStorage.setItem(STORAGE_THEME, next); } catch(_) {}
      });
    }

    /* --- system theme change, if user hasn't picked one explicitly --- */
    if (window.matchMedia) {
      var mq = window.matchMedia('(prefers-color-scheme: dark)');
      var listener = function(e){
        try {
          if (localStorage.getItem(STORAGE_THEME)) return;
        } catch(_) {}
        applyTheme(e.matches ? 'dark' : 'light');
      };
      if (mq.addEventListener) mq.addEventListener('change', listener);
      else if (mq.addListener) mq.addListener(listener);
    }

    /* --- scroll progress bar ---------------------------------------- */
    var fill = document.getElementById('progress-fill');
    if (fill) {
      var updateProgress = function(){
        var doc = document.documentElement;
        var scrollTop = window.pageYOffset || doc.scrollTop;
        var height = doc.scrollHeight - doc.clientHeight;
        var ratio = height > 0 ? (scrollTop / height) : 0;
        fill.style.width = (ratio * 100).toFixed(2) + '%';
      };
      updateProgress();
      window.addEventListener('scroll', updateProgress, { passive: true });
      window.addEventListener('resize', updateProgress, { passive: true });
    }

    /* --- copy buttons on code blocks -------------------------------- */
    var codeBlocks = document.querySelectorAll('.code-block');
    codeBlocks.forEach(function(block){
      var header = block.querySelector('.code-header');
      if (!header) return;
      if (header.querySelector('.copy-btn')) return;
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'copy-btn';
      btn.textContent = 'Copy';
      btn.setAttribute('aria-label', 'Copy code to clipboard');
      header.appendChild(btn);
      btn.addEventListener('click', function(ev){
        ev.preventDefault();
        var code = block.querySelector('pre code') || block.querySelector('pre');
        if (!code) return;
        var text = code.innerText;
        var done = function(){
          btn.textContent = 'Copied';
          btn.classList.add('copied');
          setTimeout(function(){
            btn.textContent = 'Copy';
            btn.classList.remove('copied');
          }, 1600);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done, function(){
            fallbackCopy(text); done();
          });
        } else {
          fallbackCopy(text); done();
        }
      });
    });

    function fallbackCopy(text){
      try {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', '');
        ta.style.position = 'absolute';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      } catch(_) {}
    }
  });
})();
