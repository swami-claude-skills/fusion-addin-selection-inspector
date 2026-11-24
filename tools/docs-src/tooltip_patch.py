#!/usr/bin/env python3
"""Vibe-dashboard tooltip patch (idempotent): no system (browser) tooltips anywhere.
Every element's title attribute, present at load or set later by a script, is moved to data-vtip
and shown in the house tooltip style (the .gj-tip card: panel-2 background, cyan border, soft shadow),
on hover and on keyboard focus, clamped to the viewport. Inline <svg><title> elements are moved too.
Usage: python3 tooltip_patch.py PAGE.html"""
import sys
p = sys.argv[1]; s = open(p).read()
if '/* ---- house-style tooltips' in s:
    print('tooltips: already applied'); sys.exit()
CSS = """
  /* ---- house-style tooltips (replace every system title tooltip) ---- */
  .vtip{max-width:300px;font-size:12.5px;line-height:1.45;color:var(--text);padding:7px 10px;z-index:95}
"""
assert '</style>' in s
i = s.index('</style>'); s = s[:i] + CSS + s[i:]
JS = r"""
/* ---- house-style tooltips: move every title attribute to data-vtip and show it in the .gj-tip style ---- */
(function(){
  const tip = document.createElement('div');
  tip.className = 'gj-tip vtip'; tip.setAttribute('role', 'tooltip');
  document.body.appendChild(tip);
  let cur = null;
  function place(el){
    const r = el.getBoundingClientRect();
    tip.style.left = '0px'; tip.style.top = '0px';
    const w = tip.offsetWidth, h = tip.offsetHeight;
    let x = Math.max(8, Math.min(r.left + r.width / 2 - w / 2, innerWidth - w - 8));
    let y = r.bottom + 8; if(y + h > innerHeight - 8) y = Math.max(8, r.top - h - 8);
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  }
  function show(el){ cur = el; tip.textContent = el.dataset.vtip; place(el); tip.classList.add('show'); }
  function hide(){ cur = null; tip.classList.remove('show'); }
  function conv(el){
    if(!el || el.nodeType !== 1) return;
    if(el.tagName.toLowerCase() === 'title' && el.closest('svg')){          /* inline <svg><title> */
      const host = el.parentNode; const t = el.textContent.trim(); el.remove();
      if(host && t){ host.dataset.vtip = t; }
      return;
    }
    if(!el.hasAttribute('title')) return;
    const t = el.getAttribute('title'); el.removeAttribute('title');
    if(!t.trim()) return;
    el.dataset.vtip = t;
    if(!el.hasAttribute('aria-label') && !el.textContent.trim()) el.setAttribute('aria-label', t);
    if(el === cur){ tip.textContent = t; place(el); }
  }
  document.querySelectorAll('[title], svg title').forEach(conv);
  new MutationObserver(ms => {
    for(const m of ms){
      if(m.type === 'attributes'){ conv(m.target); continue; }
      m.addedNodes.forEach(n => { if(n.nodeType !== 1) return; conv(n); n.querySelectorAll && n.querySelectorAll('[title], svg title').forEach(conv); });
    }
  }).observe(document.documentElement, {subtree:true, childList:true, attributes:true, attributeFilter:['title']});
  document.addEventListener('pointerover', e => {
    const el = e.target.closest && e.target.closest('[data-vtip]');
    if(el){ if(el !== cur) show(el); } else if(cur) hide();
  }, true);
  document.addEventListener('focusin', e => { const el = e.target.closest && e.target.closest('[data-vtip]'); if(el && el.matches(':focus-visible')) show(el); });
  document.addEventListener('focusout', hide);
  document.addEventListener('keydown', e => { if(e.key === 'Escape') hide(); });
  addEventListener('scroll', () => { if(cur) hide(); }, {passive:true});
})();
"""
j = s.rindex('</script>'); s = s[:j] + JS + s[j:]
open(p, 'w').write(s); print('tooltips: applied')
