#!/usr/bin/env python3
"""Vibe-dashboard 'source' category colour patch (idempotent).
The source category (Glossary, References, Source Document) gets its own bright silver-white
#f2f2f2, outside the 8-colour palette, so its badge is bright and never clashes with content categories.
Sets --cat-source and (re)writes the five cat-source CSS rules.
Usage: python3 source_colour_patch.py PAGE.html"""
import re, sys
p = sys.argv[1]; s = open(p).read()
COL, TINT = '#f2f2f2', 'rgba(242,242,242,.12)'  # pure neutral: no hue, so it never clashes
# 1. colour var (replace or add)
if re.search(r'--cat-source:#[0-9a-fA-F]{6};', s):
    s = re.sub(r'--cat-source:#[0-9a-fA-F]{6};', f'--cat-source:{COL};', s)
else:
    m = re.search(r'(    --cat-[a-z]+:#[0-9a-fA-F]{6};[^\n]*\n)(?!    --cat-)', s)
    assert m, 'no --cat- vars found'
    s = s[:m.end()] + f'    --cat-source:{COL};      /* source: bright silver, outside the palette */\n' + s[m.end():]
# 2. CSS rules: drop old ones (and an older patch's comment), add the full set once
s = s.replace('  /* ---- source category colour ---- */\n', '')
s = re.sub(r'\n[ \t]*(?:\.toc-tip\.tc-source \.tip-badge|\.cat-source \.cat-badge|\.cat-source|\.toc-chip\.tc-source(?::hover)?)\{[^}]*\}', '', s)
RULES = (f'\n  .cat-source .cat-badge{{color:var(--cat-source);background:{TINT}}}'
         '\n  .cat-source{border-left:3px solid var(--cat-source)}'
         '\n  .toc-chip.tc-source{border-left-color:var(--cat-source)}'
         '\n  .toc-chip.tc-source:hover{color:var(--cat-source)}'
         f'\n  .toc-tip.tc-source .tip-badge{{color:var(--cat-source);background:{TINT}}}')
i = s.index('</style>')
s = s[:i] + '  /* ---- source category colour ---- */' + RULES + '\n' + s[i:]
# 3. fix the template's colour check: a hueless colour (hue -1) must count as far from every hue
OLD = "let hd = (a.hue<0||b.hue<0) ? 999 : Math.abs(a.hue-b.hue); if(hd>180) hd=360-hd;"
NEW = "let hd = 999; if(a.hue>=0 && b.hue>=0){ hd = Math.abs(a.hue-b.hue); if(hd>180) hd = 360-hd; }"
if OLD in s: s = s.replace(OLD, NEW)
open(p, 'w').write(s); print('source colour: set to', COL)
