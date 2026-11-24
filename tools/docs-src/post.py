"""Page edits after the vibe-dashboard patches (idempotent). Order: build_page.py, fit_patch, toolbar_patch,
search reset left, search_patch, post.py, mindmap_patch, source_colour_patch, tooltip_patch, install_steps, build_docs, audio."""
import re, sys
p = sys.argv[1]; s = open(p).read()
m = re.search(r"const TAG_CH = \{[^}]*\}", s); t = m.group(0)
if 'diagram:' not in t:
    s = s.replace(t, t[:-1] + ", diagram:'DIAGRAM', tree:'TREE'}", 1)
s = s.replace("'gloss-jump','tid']", "'gloss-jump','tid','tree-sum','viz','tlab']")
if 'function openDetailsFor' not in s:
    s = s.replace("function jumpToEl(el){\n  if(!el) return;\n",
                  "function openDetailsFor(el){\n  for(let d = el && el.closest('details'); d; d = d.parentElement && d.parentElement.closest('details')) d.open = true;\n}\n"
                  "function jumpToEl(el){\n  if(!el) return;\n  openDetailsFor(el);\n", 1)
    s = s.replace("  const m=matches[current];\n  if(!m) return;\n  m.classList.add('active');\n",
                  "  const m=matches[current];\n  if(!m) return;\n  openDetailsFor(m);\n  m.classList.add('active');\n", 1)
    assert s.count('openDetailsFor(') >= 3
open(p, 'w').write(s); print('post: applied')
