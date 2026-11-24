#!/usr/bin/env python3
"""Vibe-dashboard toolbar patch (idempotent).
- 'show/hide TOC' button (list icon) left of the expand/collapse button; choice remembered per viewer.
- 'expand all' + 'collapse all' merged into ONE toggle button (#toggleAll) whose icon and label
  show the next action: 'expand all' (arrows apart) until every section is open, then 'collapse all'
  (arrows together). Stays in sync when sections are opened or closed by hand.
Works on a fresh template copy and on pages that already had the separate buttons or an older TOC toggle.
Usage: python3 toolbar_patch.py PAGE.html"""
import re, sys
p = sys.argv[1]; s = open(p).read()
if 'id="toggleAll"' in s and 'id="tocToggle"' in s:
    print('toolbar: already applied'); sys.exit()

ICO = '<svg class="ico{c}" viewBox="0 0 24 24" aria-hidden="true">{d}</svg>'
I_TOC = ICO.format(c='', d='<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1.3"/><circle cx="4.5" cy="12" r="1.3"/><circle cx="4.5" cy="18" r="1.3"/>')
I_EXP = ICO.format(c=' i-exp', d='<path d="M7 9l5-5 5 5M7 15l5 5 5-5"/>')
I_COL = ICO.format(c=' i-col', d='<path d="M7 4l5 5 5-5M7 20l5-5 5 5"/>')
BTNS = (f'<button class="tool-btn" id="tocToggle" aria-pressed="true" title="Hide the table of contents to see more of the page">{I_TOC}<span class="tl">hide TOC</span></button>\n'
        f'    <button class="tool-btn" id="toggleAll" title="Open every section and item">{I_EXP}{I_COL}<span class="tl">expand all</span></button>')

# 1. markup: replace whatever expand/collapse/TOC buttons are there with the two new ones
m = re.search(r'(?:<button class="tool-btn" id="tocToggle".*?</button>\s*)?<button class="tool-btn" id="expandAll".*?</button>\s*<button class="tool-btn" id="collapseAll".*?</button>', s, re.S)
assert m, 'expand/collapse buttons not found'
s = s[:m.start()] + BTNS + s[m.end():]

# 2. CSS (drop an older copy first)
s = re.sub(r"\n  /\* ---- toolbar patch css ---- \*/.*?/\* ---- end toolbar patch css ---- \*/", "", s, flags=re.S)
s = re.sub(r"\n  \.tool-btn\{display:inline-flex;align-items:center;gap:6px;white-space:nowrap\}.*?body\.toc-hidden \.toc-bar\{display:none\}", "", s, flags=re.S)
CSS = """
  /* ---- toolbar patch css ---- */
  .tool-btn{display:inline-flex;align-items:center;gap:6px;white-space:nowrap}
  .tool-btn .ico{width:14px;height:14px;flex:none;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
  .tool-btn .ico circle{fill:currentColor;stroke:none}
  #toggleAll .tl{min-width:12ch} #tocToggle .tl{min-width:8ch}  /* label swap never shifts the toolbar */
  #toggleAll .i-col{display:none} #toggleAll.all-open .i-col{display:block} #toggleAll.all-open .i-exp{display:none}
  #tocToggle[aria-pressed="false"]{color:var(--cyan);border-color:rgba(0,229,255,.45)}
  body.toc-hidden .toc-bar{display:none}
  /* ---- end toolbar patch css ---- */"""
a = '  .tool-btn:hover{border-color:var(--cyan);color:var(--cyan)}'
assert a in s; s = s.replace(a, a + CSS, 1)

# 3. JS: replace the two old listeners with the single toggle
JS_ALL = r"""/* ---- one expand/collapse toggle (label + icon show the next action) ---- */
const toggleAllBtn = document.getElementById('toggleAll');
function syncToggleAll(){
  const open = [...sections].length > 0 && [...sections].every(s => s.classList.contains('open'));
  toggleAllBtn.classList.toggle('all-open', open);
  toggleAllBtn.querySelector('.tl').textContent = open ? 'collapse all' : 'expand all';
  toggleAllBtn.title = open ? 'Close every section and item' : 'Open every section and item';
}
toggleAllBtn.addEventListener('click', () => {
  if(toggleAllBtn.classList.contains('all-open')){
    sections.forEach(s=>s.classList.remove('open')); document.querySelectorAll('.citem').forEach(c=>c.classList.remove('open')); syncFloatingHeaders();
  } else {
    sections.forEach(s=>s.classList.add('open')); document.querySelectorAll('.citem').forEach(c=>c.classList.add('open')); fitVisibleTables(); syncFloatingHeaders();
  }
  syncToggleAll();
});
document.addEventListener('click', () => setTimeout(syncToggleAll, 0));
syncToggleAll();
"""
m1 = re.search(r"document\.getElementById\('expandAll'\)\.addEventListener\('click'.*?\n", s)
m2 = re.search(r"document\.getElementById\('collapseAll'\)\.addEventListener\('click'.*?\n", s)
assert m1 and m2, 'old listeners not found'
s = s[:m1.start()] + JS_ALL + s[m2.end():]

# 4. JS: TOC show/hide (drop an older copy first)
s = re.sub(r"\n/\* ---- show/hide TOC .*?\n\}\)\(\);\n", "\n", s, flags=re.S)
JS_TOC = r"""
/* ---- show/hide TOC (toolbar button left of the expand/collapse toggle); remembered per viewer ---- */
(function(){
  const btn = document.getElementById('tocToggle'); if(!btn) return;
  const lab = btn.querySelector('.tl');
  function apply(hidden, save){
    document.body.classList.toggle('toc-hidden', hidden);
    btn.setAttribute('aria-pressed', hidden ? 'false' : 'true');
    lab.textContent = hidden ? 'show TOC' : 'hide TOC';
    btn.title = hidden ? 'Show the table of contents' : 'Hide the table of contents to see more of the page';
    const tip = document.querySelector('.toc-tip'); if(tip) tip.classList.remove('show');
    updateStackH();
    try{ syncFloatingHeaders(); }catch(e){}  /* not yet defined on first load */
    if(save){ try{ localStorage.setItem('vibe-toc-hidden', hidden ? '1' : '0'); }catch(e){} }
  }
  btn.addEventListener('click', () => apply(!document.body.classList.contains('toc-hidden'), true));
  let saved = null; try{ saved = localStorage.getItem('vibe-toc-hidden'); }catch(e){}
  if(saved === '1') apply(true, false);
})();
"""
a = "if(document.fonts && document.fonts.ready) document.fonts.ready.then(updateStackH);\n"
assert a in s; s = s.replace(a, a + JS_TOC, 1)
open(p, 'w').write(s); print('toolbar: applied')
