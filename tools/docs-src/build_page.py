#!/usr/bin/env python3
"""Build docs/index.html (the GitHub Pages documentation) from the vibe-dashboard template.

Usage:  python3 tools/docs-src/build_page.py TEMPLATE.html docs/index.html

Writes the content sections only. Afterwards run, in order:
  vibe-dashboard fit_patch.py, toolbar_patch.py, search_patch.py, mindmap_patch.py,
  source_colour_patch.py, tooltip_patch.py, then tools/install_steps.py and
  tools/build_docs.py (version, date, What's New), then the audio overview.
"""
import os, re, sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from svg import Svg, CYAN, GREEN, YELLOW, ORANGE, PINK, MAGENTA, VIOLET, BLUE, DIM, TEXT, MUTE  # noqa: E402

REPO_URL = 'https://github.com/swami-claude-skills/fusion-addin-selection-inspector'

# category: (colour, badge)
CATS = {
    'overview': ('#38dafa', 'Overview'),
    'release':  ('#38fa79', 'Releases'),
    'using':    ('#dafa38', 'Using It'),
    'settings': ('#fa9938', 'Settings'),
    'internals': ('#fa3899', 'Internals'),
    'testing':  ('#ea38fa', 'Testing'),
}


def rgba(hexc, a='.10'):
    h = hexc.lstrip('#')
    return 'rgba(%d,%d,%d,%s)' % (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


def cat_css():
    out = []
    for name, (col, _) in CATS.items():
        out.append('  .cat-%s .cat-badge{color:var(--cat-%s);background:%s}' % (name, name, rgba(col)))
        out.append('  .cat-%s{border-left:3px solid var(--cat-%s)}' % (name, name))
        out.append('  .toc-chip.tc-%s{border-left-color:var(--cat-%s)}' % (name, name))
        out.append('  .toc-chip.tc-%s:hover{color:var(--cat-%s)}' % (name, name))
        out.append('  .toc-tip.tc-%s .tip-badge{color:var(--cat-%s);background:%s}' % (name, name, rgba(col)))
    return '\n'.join(out)


def section(cat, title, body):
    badge = CATS[cat][1]
    t = title.replace('&', '&amp;')
    return ('  <div class="section cat-%s" data-title="%s" data-cat="%s">\n'
            '    <div class="sec-head"><span class="sec-num">00</span><span class="sec-title">%s</span>'
            '<span class="cat-badge">%s</span><span class="chevron">▶</span></div>\n'
            '    <div class="sec-body">\n%s\n    </div>\n  </div>\n') % (cat, t, cat, t, badge, body)


def li(tid, html):
    return '        <li><span class="tid">%s</span>%s</li>' % (tid, html)


def ul(desc, items, label=None):
    attr = ' data-mm-label="%s"' % label if label else ''
    return '      <ul data-desc="%s"%s>\n%s\n      </ul>' % (desc, attr, '\n'.join(li(a, b) for a, b in items))


def table(desc, head, rows, cls=''):
    th = ''.join('<th>%s</th>' % h for h in head)
    trs = '\n'.join('            <tr>%s</tr>' % ''.join('<td>%s</td>' % c for c in r) for r in rows)
    return ('      <div class="table-wrap%s" data-desc="%s">\n        <table>\n          <thead><tr>%s</tr></thead>\n'
            '          <tbody>\n%s\n          </tbody>\n        </table>\n      </div>') % (' ' + cls if cls else '', desc, th, trs)


def callout(lbl, html):
    return '      <div class="callout"><span class="lbl">%s</span>%s</div>' % (lbl, html)


def figure(tag, desc, tip, img, legend, caption):
    lg = ''
    if legend:
        items = []
        for it in legend:
            if it[0] in ('solid', 'dashed'):
                items.append('<span class="lg"><i class="lg-line%s" style="--c:%s"></i>%s</span>'
                             % (' lg-dashed' if it[0] == 'dashed' else '', it[2], it[1]))
            else:
                items.append('<span class="lg"><i class="lg-sw" style="--c:%s"></i>%s</span>' % it)
        lg = '<div class="viz-legend" aria-label="Colour key"><span class="lg-title">Key</span>%s</div>' % ''.join(items)
    return ('      <div class="subsec" data-tag="%s" data-desc="%s" data-mm-tip="%s"><figure class="viz">'
            '<div class="viz-scroll">%s</div>%s<figcaption>%s</figcaption></figure></div>') % (tag, desc, tip, img, lg, caption)


def tid(text, col):
    return '<span class="tid" style="--tc:%s">%s</span>' % (col, text)


# ------------------------------------------------------------------ diagrams
def palette_schematic():
    s = Svg(900, 470)
    s.text(24, 32, 'Selection Inspector (v2.37.0)', size=13, color=DIM, mono=True)
    s.text(876, 32, 'schematic, not a screenshot', size=11, color=MUTE, anchor='end')
    s.box(20, 46, 860, 36, CYAN, rx=6)
    for i, t in enumerate(['LIST', 'VISIBILITY', 'COLUMNS', 'TOOLS']):
        s.text(52 + i * 110, 69, t, size=11, color=TEXT, mono=True)
    s.box(780, 52, 88, 24, CYAN, 'REFRESH', title_size=10, rx=4)
    s.badge(20, 46, 1)
    s.box(20, 90, 860, 34, YELLOW, rx=6)
    s.text(36, 112, 'filter · type · Selected only · Sub-entities · Reveal selected', size=11, color=DIM, mono=True)
    s.badge(20, 90, 2)
    s.box(20, 132, 860, 26, PINK, rx=4)
    s.text(36, 150, 'ERROR  shown here as well as in the log; click to dismiss', size=11, color=TEXT, mono=True)
    s.badge(20, 132, 3)
    s.box(20, 164, 860, 26, GREEN, rx=4)
    s.text(36, 182, 'Version 2.38.0 is available   [Install update] [Download] [What\'s new]', size=11, color=TEXT, mono=True)
    s.badge(20, 164, 4)
    s.box(20, 198, 860, 150, BLUE, rx=6)
    cols = ['SHOW', 'SELECTED', 'ENTITY NAME', 'TYPE', 'QTY', 'PARENT / CHILD PATH', 'INSTANCE / STATUS']
    xs = [34, 96, 190, 330, 410, 470, 680]
    for x, c in zip(xs, cols):
        s.text(x, 220, c, size=10, color=DIM, mono=True)
    for r in range(4):
        y = 246 + r * 26
        s.parts.append('<rect x="38" y="%d" width="11" height="11" rx="2" fill="%s"/>' % (y - 10, CYAN if r != 2 else '#26262e'))
        s.parts.append('<rect x="104" y="%d" width="11" height="11" rx="2" fill="%s"/>' % (y - 10, CYAN if r == 1 else '#26262e'))
        s.text(190, y, ['Frame:1', 'Bracket:1', 'Body1', 'Base Profile'][r], size=11, color=YELLOW, mono=True)
        s.text(330, y, ['Component', 'Component', 'Body', 'Sketch'][r], size=10, color=CYAN, mono=True)
        s.text(420, y, ['2', '4', '2', '2'][r], size=11, color=ORANGE, mono=True)
        s.text(470, y, ['root', 'root / Frame:1', 'root / Frame:1', 'root / Frame:1'][r], size=11, color=YELLOW, mono=True)
        s.text(680, y, ['Local · 1 of 2', 'Linked · 1 of 4', '2 occurrences', '2 occurrences'][r], size=10, color=DIM)
    s.badge(20, 198, 5)
    s.box(20, 356, 860, 64, VIOLET, rx=6)
    s.text(36, 376, 'LOG   Copy · Color / Plain · Save · Clear · Hide', size=11, color=TEXT, mono=True)
    s.text(36, 398, '20:14:37  Selection Inspector v2.37.0 · palette UI v2.37.0 · manifest on disk v2.37.0', size=10, color=DIM, mono=True)
    s.badge(20, 356, 6)
    s.box(20, 428, 860, 30, MUTE, rx=6)
    s.text(36, 448, 'Stats: entities · listed · visible · selected in Fusion · rows selected · timeline 12/34 · LIVE', size=10, color=DIM, mono=True)
    s.badge(20, 428, 7)
    return s.img('Schematic of the Selection Inspector palette: tab strip with Refresh, toolbar, error strip, '
                 'update bar, the table, the log pane and the footer, each with a numbered marker.')


def update_flow():
    s = Svg(900, 300)
    s.box(20, 40, 150, 60, CYAN, 'Palette opens', 'at most every 2 min')
    s.box(210, 40, 170, 60, VIOLET, 'Read version.json', 'background thread')
    s.box(420, 40, 150, 60, YELLOW, 'Newer?', 'compare versions')
    s.box(610, 40, 270, 60, GREEN, 'Green bar', 'Install update · Download · What\'s new')
    s.box(420, 170, 150, 60, MUTE, 'Up to date', 'logged, no bar')
    s.box(610, 170, 120, 60, ORANGE, 'Back up', 'old files kept')
    s.box(760, 170, 120, 60, GREEN, 'Replace files', 'from the zip')
    s.arrow(170, 70, 208, 70)
    s.arrow(380, 70, 418, 70)
    s.arrow(570, 70, 608, 70)
    s.text(590, 62, 'yes', size=11, color=DIM, anchor='middle')
    s.arrow(495, 100, 495, 168, dash=True)
    s.text(505, 140, 'no', size=11, color=DIM)
    s.arrow(670, 100, 670, 168)
    s.text(680, 140, 'Install update (asks first)', size=11, color=DIM)
    s.arrow(730, 200, 758, 200)
    s.box(610, 250, 270, 36, BLUE, 'Run off, then on', None, title_size=12)
    s.arrow(820, 230, 820, 248)
    s.box(20, 170, 360, 60, MUTE, 'Tools > Check for updates', 'checks now, even with Auto-check off', dash=True)
    s.path('M 200 170 L 200 125 L 290 125 L 290 102', dash=True)
    return s.img('Flow of the update check: the palette opens, version.json is read in the background, '
                 'a newer version shows a green bar, and Install update backs up and replaces the files.')


def tree(nodes):
    def render(n):
        label, note, kids = n
        if not kids:
            return '<div class="tleaf"><span class="tlab">%s</span><span class="tnote">%s</span></div>' % (label, note)
        return ('<details class="tnode"><summary class="tree-sum"><span class="tlab">%s</span><span class="tnote">%s</span>'
                '<span class="tcount">{%d}</span></summary>%s</details>') % (label, note, len(kids), ''.join(render(k) for k in kids))
    return ''.join(render(n) for n in nodes)


FILES_TREE = [
    ('SelectionInspector/', 'the add-in folder, as it ships in the zip', [
        ('SelectionInspector.py', 'entry point: run() and stop(), scan, bridge, settings, update check', None),
        ('SelectionInspector.manifest', 'what Fusion reads to list the add-in; version must match', None),
        ('palette.html', 'the table palette (dark, self-contained)', None),
        ('legend.html', 'the Qty color legend palette', None),
        ('resources/command/', 'button icons (16, 32, 64 px and @2x)', [
            ('16x16.png · 32x32.png · 64x64.png', 'needed for a keyboard shortcut', None),
        ]),
        ('install-macos.command', 'Mac installer', None),
        ('install-windows.cmd + .ps1', 'Windows installer', None),
        ('READ ME FIRST.txt', 'three ways to install', None),
    ]),
    ('Your settings folder', 'outside the add-in, kept across reinstalls', [
        ('settings.json', 'column widths, log height, copy mode, Auto-check', None),
        ('backup-v2.37.0/', 'previous version, made by Install update', None),
    ]),
    ('The repository', 'on GitHub', [
        ('version.json', 'latest version, read by the update check', None),
        ('notes/', 'release notes, one file per version', None),
        ('docs/', 'this page and the design notes', None),
        ('tools/', 'build_release.py, build_docs.py, install_steps.py', None),
        ('.github/workflows/release.yml', 'publishes a release, refuses stale docs', None),
    ]),
]


# ------------------------------------------------------------------ sections
def build_sections():
    S = []
    # 03 What's New
    S.append(section('release', "What's New",
        '      <p>One entry per released version, newest first. This section is generated from the release notes each time a version is released, so it always matches the version in the title.</p>\n'
        '<!-- WHATSNEW:BEGIN -->\n<!-- WHATSNEW:END -->'))

    # 04 The Palette
    body = ['      <p>Selection Inspector is a <strong>non-modal palette</strong>: it docks on the right of Fusion, can be floated, and stays open while you model. Its own title bar carries the name and version, so the whole window goes to the table. Controls sit on four tabs, one shown at a time, with <strong>Refresh</strong> always on the tab strip.</p>',
            figure('diagram', 'Annotated schematic of the palette', 'The palette from top to bottom: tabs, toolbar, error strip, update bar, table, log and footer.',
                   palette_schematic(),
                   [(CYAN, 'tabs and Refresh'), (YELLOW, 'toolbar of the open tab'), (PINK, 'error strip'), (GREEN, 'update bar'),
                    (BLUE, 'the table'), (VIOLET, 'log pane'), (MUTE, 'footer')],
                   'Read it top to bottom. The numbered markers match the rows of the table below. The error strip and the update bar only appear when there is something to say.'),
            table('The parts of the palette', ['#', 'Part', 'What it does'], [
                ['<strong>1</strong>', tid('Tabs', CYAN), '<strong>List</strong>, <strong>Visibility</strong>, <strong>Columns</strong>, <strong>Tools</strong>, plus <strong>Refresh</strong> to rescan the design.'],
                ['<strong>2</strong>', tid('Toolbar', YELLOW), 'The controls of the open tab (listed in the next table).'],
                ['<strong>3</strong>', tid('Error strip', PINK), 'Any error from the add-in, also written to the log. Click it to dismiss.'],
                ['<strong>4</strong>', tid('Update bar', GREEN), 'Shows when a newer version is out: Install update, Download, What\'s new, Dismiss.'],
                ['<strong>5</strong>', tid('Table', BLUE), 'Every entity in the active design; see The Table.'],
                ['<strong>6</strong>', tid('Log', VIOLET), 'A record of everything the palette and the add-in did, hidden until you press Log.'],
                ['<strong>7</strong>', tid('Footer', '#9aa0aa'), 'Counts, the timeline position, and whether the palette is connected to Fusion (LIVE).'],
            ], 'no-sort'),
            table('What is on each tab', ['Tab', 'Holds'], [
                ['<strong>List</strong>', 'Text filter with its ×, type dropdown, <strong>Selected only</strong>, <strong>Sub-entities</strong>, <strong>Reveal selected</strong>'],
                ['<strong>Visibility</strong>', 'All / Selected / Not selected radios, <strong>Show all</strong>, <strong>Hide all</strong>'],
                ['<strong>Columns</strong>', '<strong>Fit columns</strong>'],
                ['<strong>Tools</strong>', '<strong>Under-constrained</strong>, <strong>Legend</strong>, <strong>Log</strong>, <strong>Check for updates</strong>, <strong>Auto-check</strong>, <strong>Docs</strong>, <strong>Reset all</strong>'],
            ], 'no-sort'),
            callout('Opening state', 'The palette always opens the same way: List tab, log hidden, filters empty and every toggle off. Only how things look once you use them (column widths, log height, copy mode) is remembered.')]
    S.append(section('using', 'The Palette', '\n'.join(body)))

    # 05 The Table
    body = ['      <p>One row per entity in the active design: components, bodies, meshes, sketches, construction planes, axes, points and joints. With <strong>Sub-entities</strong> on, faces, edges, vertices and sketch curves and points are listed too, grouped under their owner.</p>',
            table('Columns of the table', ['Column', 'What it shows'], [
                ['<strong>Show</strong>', 'The light bulb. Tick or untick to show or hide; showing a nested item also shows the parents that were hiding it.'],
                ['<strong>Selected</strong>', 'Whether the entity is selected in Fusion right now. Ticking or unticking changes the Fusion selection.'],
                ['<strong>Entity Name</strong>', 'The name as in the browser, coloured to match its Qty cell.'],
                ['<strong>Type</strong>', 'Component, Body, Mesh, Sketch, Plane, Axis, Point, Joint, and the sub-entity types. Colour-coded and filterable.'],
                ['<strong>Qty</strong>', 'Instance count, coloured by placement: suppressed, unplaced, linked, local, multiple or single. The Legend button explains the colours.'],
                ['<strong>Parent / Child Path</strong>', 'The ancestry, e.g. <code>root / Frame:1 / Bracket:1</code>. Shared ancestry folds into a leading …'],
                ['<strong>Instance / Status</strong>', 'For components: local or linked, instance n of m, grounded, suppressed, isolated. For the rest: which component owns it and how many occurrences.'],
            ]),
            ul('Reading the table', [
                ('Sorting', 'Click a header: ascending, descending, then back to the natural order.'),
                ('Widths', 'Drag a header edge to resize; double-click it to fit that column. A <strong>FIT</strong> marker in a header means the column is hiding text.'),
                ('Grouping', 'With sub-entities on, a body opens into one group per type (Face × 248, Edge × 612), each closed until you open it.'),
                ('Rows are readouts', 'Clicking a row does nothing. The two checkboxes and the caret are the only controls in a row; right-click a name for Show in Browser, Window or Timeline.'),
            ], 'How to read it')]
    S.append(section('using', 'The Table', '\n'.join(body)))

    # 06 Working With It
    body = ['      <p>The everyday moves, by what you want to do.</p>',
            ul('Everyday tasks', [
                ('Find something', 'Type in the filter (name, path, status, type) or pick a type. Esc clears it.'),
                ('Follow the selection', '<strong>Selected only</strong> lists just what is picked in Fusion and follows the selection as it changes. <strong>Reveal selected</strong> opens the groups a pick is buried in and scrolls to it.'),
                ('Show and hide', 'Filter first, then <strong>Show all</strong> or <strong>Hide all</strong> act on exactly what is listed. On the Visibility tab, <strong>Selected</strong> hides everything but the selection and <strong>Not selected</strong> hides the selection.'),
                ('Select from the table', 'Tick <strong>Selected</strong> on rows to build a Fusion selection; group checkboxes select a whole run.'),
                ('Go back in time', 'Roll the timeline marker back and the table rebuilds to match; the footer shows <code>timeline 12/34</code> in amber while rolled back.'),
                ('Sketch checks', 'While editing a sketch, <strong>Under-constrained</strong> runs Fusion\'s own under-constrained highlight.'),
                ('Report a problem', 'Open the <strong>Log</strong>, then <strong>Copy</strong> (Color or Plain) or <strong>Save</strong> it to the Desktop as HTML and text.'),
            ], 'Tasks'),
            callout('Keyboard shortcut', 'Right-click the Selection Inspector button in any INSPECT panel and choose <strong>Change Keyboard Shortcut</strong>. The shortcut belongs to you, not the add-in, and survives reinstalls and updates.')]
    S.append(section('using', 'Working With It', '\n'.join(body)))

    # 07 Settings & Reset All
    body = ['      <p>Since v2.37.0 the add-in keeps its preferences in a settings file <strong>outside the add-in folder</strong>, so reinstalling, updating or clearing Fusion\'s web cache keeps them. The first time v2.37.0 runs it copies the widths, log height and copy mode the palette had saved before.</p>',
            table('What is saved', ['Setting', 'Default', 'Changed by'], [
                ['<strong>Column widths</strong>', 'per column', 'Dragging or fitting a column'],
                ['<strong>Log height</strong>', '150 px', 'Dragging the bar above the log'],
                ['<strong>Copy mode</strong>', 'Color', 'Color / Plain beside the log\'s Copy button'],
                ['<strong>Auto-check</strong>', 'On', 'Tools ▸ Auto-check'],
            ]),
            table('Where the settings file is', ['System', 'Path'], [
                ['<strong>macOS</strong>', '<code>~/Library/Application Support/SwamiFusionAddins/SelectionInspector/settings.json</code>'],
                ['<strong>Windows</strong>', '<code>%APPDATA%\\SwamiFusionAddins\\SelectionInspector\\settings.json</code>'],
            ], 'no-sort'),
            callout('Reset all', '<strong>Tools ▸ Reset all</strong> asks first, then puts every setting back to its default and returns the palette to its opening state: List tab, log hidden, filters cleared, Selected only, Sub-entities and Reveal selected off, natural sort order and default column widths. It cannot be undone.')]
    S.append(section('settings', 'Settings & Reset All', '\n'.join(body)))

    # 08 Updates & Errors
    body = ['      <p>Each time the palette opens (at most once every two minutes) the add-in reads <code>version.json</code> from GitHub in the background, so Fusion never waits on the network.</p>',
            figure('diagram', 'Workflow of the update check', 'How a newer version is found, offered and installed.', update_flow(),
                   [(CYAN, 'you open the palette'), (VIOLET, 'background check'), (GREEN, 'offered or installed'), (ORANGE, 'backup'), (BLUE, 'your step in Fusion'), ('#6a6f78', 'nothing to install'),
                    ('solid', 'happens in order', DIM), ('dashed', 'other path or on demand', DIM)],
                   'Follow the arrows from the left. Install update always asks first and backs up the current files into the settings folder.'),
            ul('Update controls', [
                ('Install update', 'Downloads the latest SelectionInspector.zip, checks it is a newer Selection Inspector, backs up the current files and replaces them. Then turn the Run switch off and on in Scripts and Add-Ins.'),
                ('Download', 'Opens the zip link in your browser, for installing by hand.'),
                ('Check for updates', 'Tools tab. Checks now, even with Auto-check off.'),
                ('Auto-check', 'Tools tab. Off means no automatic check and no green bar.'),
            ], 'Controls'),
            callout('Errors', 'Anything that goes wrong shows in a red strip at the top of the palette as well as in the log, because a docked panel that silently does nothing is the hardest failure to diagnose. Click the strip to dismiss it. Full tracebacks go to <strong>Utilities ▸ Text Commands</strong>.')]
    S.append(section('settings', 'Updates & Errors', '\n'.join(body)))

    # 09 Install & Update
    body = ['      <p>Three ways to install. The first needs no approval on a Mac because no installer script runs. The same steps ship in the zip as <code>READ ME FIRST.txt</code>.</p>',
            '<!-- INSTALL-TABLES:BEGIN -->\n<!-- INSTALL-TABLES:END -->',
            callout('Where the button is', 'The <strong>Selection Inspector</strong> button is in the <strong>INSPECT</strong> panel of every tab (SOLID, SURFACE, MESH, SHEET METAL and the rest). The add-in finds those panels when it starts, so new tabs pick it up too.'),
            callout('Version shown in Scripts and Add-Ins', 'Fusion reads the manifest once and caches it, so the version listed there can lag behind. The palette title, the button tooltip and the first log line always show the version actually running.')]
    S.append(section('release', 'Install & Update', '\n'.join(body)))

    # 10 Files & Folders
    body = ['      <p>What is where: the add-in folder you install, the settings folder it creates, and the repository it is built from.</p>',
            '      <div class="subsec" data-tag="tree" data-desc="Folders and files" data-mm-tip="The add-in folder, the settings folder and the repository, file by file.">'
            '<div class="tree-tools"><button class="tool-btn tree-exp">expand tree</button><button class="tool-btn tree-col">collapse tree</button></div>'
            '<div class="tree">%s</div></div>' % tree(FILES_TREE)]
    S.append(section('internals', 'Files & Folders', '\n'.join(body)))

    # 11 How It Works
    body = ['      <p>A few design decisions explain most of the behaviour. The full reasoning is in the design notes in the repository <span class="cite" data-ref="2">[2]</span>.</p>',
            ul('Design decisions', [
                ('Selection matching', 'A pick in the canvas comes back as a proxy whose token differs from the object the scan found, so each row is indexed under every key it might be found by and a pick is matched against all of them.'),
                ('Staying current', 'The table rescans when the selection changes, the document changes, the timeline marker moves or a command changes the model. When an edit needs a manual <strong>Refresh</strong>, the footer says <em>model changed</em>.'),
                ('Sub-entity cap', 'Faces, edges and sketch points can run to tens of thousands, so they are capped at 12,000 rows and built group by group only when opened.'),
                ('Two files, one version', 'Python and the palette page are loaded by different things. The page reports its own version on connect; on a mismatch the add-in reloads it, and the first log line shows both.'),
                ('Shortcut survives', 'The button\'s command definition is reused rather than deleted on Stop, because a keyboard shortcut is tied to it. Its click handler is detached on Stop, so Stop then Run never answers one click twice.'),
                ('Nothing from the internet', 'The palette loads no fonts or scripts from the web; only the update check talks to GitHub, on a background thread.'),
            ], 'Decisions')]
    S.append(section('internals', 'How It Works', '\n'.join(body)))

    # 12 First-Run Test Checklist
    tests = [
        ('Download', 'The latest SelectionInspector.zip downloads and unzips to one SelectionInspector folder.', 'v2.36.6'),
        ('Install', 'Shift+S, + next to My Add-Ins, pick the folder; Run and Run on Startup turn on with no error.', 'v2.36.6'),
        ('Installers', 'install-macos.command (Open Anyway once) and install-windows.cmd copy it into Fusion\'s AddIns folder.', 'v2.36.6'),
        ('Button', 'The Selection Inspector button shows in the INSPECT panel of each tab.', 'v2.36.6'),
        ('Palette', 'Opens with the version in its title, docks and undocks, and stays open while you work.', 'v2.36.6'),
        ('Selection', 'Selecting faces, edges, bodies and sketch items updates the table straight away.', 'v2.36.6'),
        ('Opening state', 'Every time it opens: List tab, log hidden, toggles off.', 'v2.36.6'),
        ('Settings', 'Change column widths, log height and copy mode, restart Fusion: they are kept.', 'v2.37.0'),
        ('Reset all', 'Tools ▸ Reset all asks first, then brings every setting back to its default.', 'v2.37.0'),
        ('Dark mode', 'Dark theme with no white flash; text looks right with no internet connection.', 'v2.37.0'),
        ('Shortcut', 'Right-click the button, Change Keyboard Shortcut; the shortcut opens the palette.', 'v2.36.6'),
        ('Stop', 'Turn Run off: button and palette go away cleanly, no error. Run again: one click opens it once.', 'v2.37.0'),
        ('Update bar', 'With v2.37.0 installed and a newer version released, the green bar offers it.', 'v2.37.0'),
        ('Update', 'Install update replaces the files, keeps a backup, and after Run off and on the title shows the new version.', 'v2.37.0'),
        ('Kept', 'Settings survive the update; turning Auto-check off hides the bar.', 'v2.37.0'),
    ]
    rows = [['<strong>%d</strong>' % i, '<span class="tid">%s</span>' % t, d, w] for i, (t, d, w) in enumerate(tests, 1)]
    body = ['      <p>Run these once in Fusion after installing, on macOS and on Windows. The <strong>From</strong> column names the first version the check applies to.</p>',
            table('Checks to run in Fusion', ['#', 'Topic', 'Step', 'From'], rows, 'no-sort')]
    S.append(section('testing', 'First-Run Test Checklist', '\n'.join(body)))
    return S


GLOSSARY = [
    # id, match, code, term, topic, colour, definition
    ('fusion', r'Autodesk Fusion|Fusion', '', 'Fusion', 'Fusion', CYAN, 'Autodesk Fusion (formerly Fusion 360), the CAD/CAM program this add-in runs inside.'),
    ('addin', r'add-ins?', '', 'Add-in', 'Fusion', CYAN, 'A Python program that loads into Fusion and stays running, adding buttons and panels.'),
    ('palette', r'palettes?', '', 'Palette', 'Fusion', CYAN, 'A Fusion window that shows an HTML page and can dock or float while you keep working.'),
    ('inspect-panel', r'INSPECT panels?', '', 'INSPECT panel', 'Fusion', CYAN, 'The toolbar panel on each Fusion tab that holds measuring and checking tools; the button lives there.'),
    ('sai', r'Scripts and Add-Ins', '', 'Scripts and Add-Ins', 'Fusion', CYAN, 'Fusion\'s dialog (Shift+S) for adding, running and stopping add-ins.'),
    ('timeline', r'timeline marker|timeline', '', 'Timeline', 'Fusion', CYAN, 'Fusion\'s history of features; rolling its marker back shows the design at an earlier step.'),
    ('occurrence', r'occurrences?', '', 'Occurrence', 'Design', GREEN, 'One placed instance of a component in an assembly.'),
    ('component', r'components?', '', 'Component', 'Design', GREEN, 'A part or sub-assembly that holds bodies, sketches and other components.'),
    ('sub-entity', r'sub-entit(?:y|ies)', '', 'Sub-entity', 'Design', GREEN, 'A face, edge or vertex of a body, or a point or curve of a sketch.'),
    ('proxy', r'prox(?:y|ies)', '', 'Proxy', 'Design', GREEN, 'The version of an entity as seen inside a particular occurrence, which is what a canvas pick returns.'),
    ('light-bulb', r'light bulbs?', '', 'Light bulb', 'Design', GREEN, 'Fusion\'s show/hide switch next to each item in the browser.'),
    ('settings-file', r'settings file|settings folder', 'settings.json', 'Settings file', 'Add-in', ORANGE, 'The JSON file outside the add-in folder that keeps your preferences across reinstalls.'),
    ('defaults', r'DEFAULTS|defaults?', '', 'Defaults', 'Add-in', ORANGE, 'The factory settings in the add-in\'s code; Reset all returns to them.'),
    ('version-json', r'version\.json', 'version.json', 'version.json', 'Releases', YELLOW, 'A small file in the repository that names the latest version; the update check reads it.'),
    ('manifest', r'manifest', 'SelectionInspector.manifest', 'Manifest', 'Releases', YELLOW, 'The file Fusion reads to list the add-in: name, version, id and Run on Startup.'),
    ('release', r'releases?', '', 'Release', 'Releases', YELLOW, 'A published version on GitHub with SelectionInspector.zip attached.'),
    ('gatekeeper', r'Gatekeeper|Open Anyway', '', 'Gatekeeper', 'Installing', PINK, 'macOS protection that blocks a downloaded script until you allow it under Privacy & Security.'),
    ('smartscreen', r'SmartScreen|Windows protected your PC', '', 'SmartScreen', 'Installing', PINK, 'Windows protection that warns about downloaded files; More info, then Run anyway.'),
]

REFS = [
    ('1', 'GitHub', 'Repository', CYAN, 'Selection Inspector repository: add-in, releases and tools', 'Install &amp; Update, Files &amp; Folders', 'github.com', REPO_URL),
    ('2', 'GitHub', 'Repository', CYAN, 'Design notes: how the add-in works and why', 'How It Works', 'github.com', REPO_URL + '/blob/main/docs/design-notes.md'),
    ('3', 'GitHub', 'Releases', GREEN, 'Every released version with its zip', "What's New, Updates &amp; Errors", 'github.com', REPO_URL + '/releases'),
    ('4', 'Autodesk', 'Fusion help', YELLOW, 'Autodesk Fusion product help', 'The Palette', 'help.autodesk.com', 'https://help.autodesk.com/view/fusion360/ENU/'),
]


def main():
    tpl, out = sys.argv[1], sys.argv[2]
    s = open(tpl, encoding='utf-8').read()

    def rep(a, b):
        nonlocal s
        assert a in s, a[:60]
        s = s.replace(a, b, 1)

    # categories
    rep("    --cat-overview:#38dafa;   /* palette 1 (cyan)  */\n    --cat-source:#38fa79;     /* palette 2 (green) */",
        '\n'.join('    --cat-%s:%s;' % (n, c) for n, (c, _) in CATS.items()) + '\n    --cat-source:#f2f2f2;')
    m = re.search(r"  /\* live defs for the template's two example sections.*?(?=  \.chevron\{)", s, re.S)
    assert m
    s = s[:m.start()] + cat_css() + '\n' + s[m.end():]
    s = s.replace('</style>', EXTRA_CSS + '</style>', 1)

    # header
    rep('{{PAGE_TITLE}}', 'Selection Inspector')
    rep('{{KICKER}}', 'FUSION ADD-IN DOCUMENTATION')
    rep('{{H1_TITLE}} <br><span class="sub">{{H1_SUBTITLE}}</span>',
        'Selection Inspector (v<!--VERSION-->2.37.0<!--/VERSION-->) <br><span class="sub">Every entity in your Autodesk Fusion design in one dark, dockable table: path, quantity, status, selection and show/hide</span>')
    rep('    <span>{{BYLINE_A}}</span>\n    <span>{{BYLINE_B}}</span>',
        '    <span>Swami</span>\n    <span>Autodesk Fusion add-in</span>\n'
        '    <span>Version <strong><!--VERSION-->2.37.0<!--/VERSION--></strong> · released <strong><!--DATE-->Nov 24, 2026<!--/DATE--></strong></span>')
    i = s.index('</header>')
    s = s[:i] + '<!-- INSTALL-PANEL:BEGIN -->\n<!-- INSTALL-PANEL:END -->\n' + s[i:]

    # summary
    rep('{{SUMMARY_BADGE}}', 'Overview')
    rep('{{SUMMARY_INTRO}}',
        'Selection Inspector is an Autodesk Fusion add-in that lists every entity in the active design in a sortable, resizable table, '
        'with each item\'s parent path, instance count, status, live selection state and a show/hide checkbox. This page covers what is new, '
        'how to use the palette, where settings are kept, how updates work, how to install it, and a checklist for testing it in Fusion. '
        'Most sections carry a diagram, a tree or a table; terms with a dotted underline jump to the Glossary.')
    rep('{{SUMMARY_CALLOUT_LABEL}}', 'Quick start')
    rep('{{SUMMARY_CALLOUT_TEXT}}', 'Download the zip above, add the SelectionInspector folder in Scripts and Add-Ins (Shift+S, + next to My Add-Ins), '
        'turn on Run and Run on Startup, then click Selection Inspector in any INSPECT panel.')
    rows = [
        ("What's New", 'Changes in each released version', 'Checking what changed after an update'),
        ('The Palette', 'The parts of the window and what is on each tab', 'Finding a control'),
        ('The Table', 'What each column shows and how to read it', 'A colour or a column is unclear'),
        ('Working With It', 'Everyday tasks: filter, follow the selection, show and hide, report a problem', 'Doing something specific'),
        ('Settings &amp; Reset All', 'What is saved, where, and what Reset all does', 'Moving machines or starting fresh'),
        ('Updates &amp; Errors', 'The update check, Install update, Auto-check and the error strip', 'A green or red bar appears'),
        ('Install &amp; Update', 'Three ways to install, step by step', 'Installing on a new machine'),
        ('Files &amp; Folders', 'The add-in folder, the settings folder and the repository', 'Looking for a file'),
        ('How It Works', 'The design decisions behind the behaviour', 'Something behaves unexpectedly'),
        ('First-Run Test Checklist', 'Checks to run in Fusion after installing', 'Testing a new version'),
    ]
    trs = '\n'.join('            <tr><td><span class="secnum">%02d</span></td><td><strong>%s</strong></td><td class="sec-cat"></td><td>%s</td><td>%s</td></tr>'
                    % (n, t, f, w) for n, (t, f, w) in enumerate(rows, 2))
    m = re.search(r'            <tr><td><span class="secnum">02</span></td><td><strong>\{\{SEC_A_TITLE\}\}.*?<!-- one row per remaining section -->', s, re.S)
    assert m
    s = s[:m.start()] + trs + s[m.end():]
    s = re.sub(r'\n\s*<tr><td><span class="secnum" data-target-title="Source Document \(Verbatim\)"></span>.*?</tr>', '', s)

    # content sections: replace the example section
    m = re.search(r'  <!-- SECTION PATTERN.*?(?=  <!-- OPTIONAL \(include whenever)', s, re.S)
    assert m
    s = s[:m.start()] + ''.join(build_sections()) + '\n' + s[m.end():]

    # glossary
    rep('<thead><tr><th>Term</th><th>Definition</th><th>Appears in</th><th>Qty</th></tr></thead>',
        '<thead><tr><th>Term</th><th>Topic</th><th>Definition</th><th>Appears in</th><th>Qty</th></tr></thead>')
    grows = '\n'.join('            <tr data-gterm="%s" data-match="%s" data-code="%s"><td><strong>%s</strong></td><td>%s</td><td>%s</td><td class="gloss-uses"></td><td class="gloss-count"></td></tr>'
                      % (g[0], g[1], g[2], g[3], tid(g[4], g[5]), g[6]) for g in GLOSSARY)
    m = re.search(r'            <tr data-gterm="\{\{GLOSS_A_ID\}\}".*?<!-- one row per term -->', s, re.S)
    assert m
    s = s[:m.start()] + grows + s[m.end():]
    rep("click it to land on its row.", "click it to land on its row. Each term's <strong>Topic</strong> tag names what it is about, one color per topic.")
    if "def = row.cells[1].textContent.trim();" in s:
        s = s.replace("def = row.cells[1].textContent.trim();",
                      "def = ([...row.cells].slice(1).find(c => !c.querySelector('.tid') && !c.matches('.gloss-uses,.gloss-count')) || {textContent:''}).textContent.trim();")

    # references
    rrows = '\n'.join('            <tr data-ref="%s"><td><strong>[%s] %s</strong></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td><a href="%s" target="_blank" rel="noopener">open ↗</a></td></tr>'
                      % (r[0], r[0], r[1], tid(r[2], r[3]), r[4], r[5], r[6], r[7]) for r in REFS)
    m = re.search(r'            <tr data-ref="\{\{REF_A_NUM\}\}".*?<!-- one row per cited source -->', s, re.S)
    assert m
    s = s[:m.start()] + rrows + s[m.end():]

    # drop the verbatim section and its script block
    m = re.search(r'  <!-- OPTIONAL verbatim source section.*?</div>\n  </div>\n', s, re.S)
    assert m
    s = s[:m.start()] + s[m.end():]
    m = re.search(r"/\* ---- verbatim content.*?\n\}\n", s, re.S)
    assert m
    s = s[:m.start()] + s[m.end():]

    rep('{{MAIL_SUBJECT}}', 'Selection Inspector')
    assert '{{' not in s, re.findall(r'\{\{[A-Z_0-9]+\}\}', s)[:5]

    # tree + figure script
    j = s.rindex('</script>')
    s = s[:j] + EXTRA_JS + s[j:]
    open(out, 'w', encoding='utf-8').write(s)
    print('wrote', out, len(s), 'bytes')


EXTRA_CSS = """
  /* ---- visuals: figures, keys and trees ---- */
  .viz{margin:6px 0 4px}
  .viz-scroll{overflow-x:auto;border-radius:14px}
  .viz img{width:100%;min-width:720px;display:block}
  .viz figcaption{margin-top:8px;font-size:13px;color:var(--text-dim)}
  .viz-legend{display:flex;flex-wrap:wrap;align-items:center;gap:6px 16px;margin:10px 2px 0;font-size:12.5px;color:var(--text-dim)}
  .viz-legend .lg-title{font-family:var(--mono);font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:var(--text-mute)}
  .viz-legend .lg{display:inline-flex;align-items:center;gap:7px}
  .viz-legend .lg-sw{width:13px;height:13px;border-radius:4px;border:1.5px solid var(--c);background:color-mix(in srgb,var(--c) 22%,transparent);flex:none}
  .viz-legend .lg-line{width:26px;height:0;border-top:2px solid var(--c);flex:none}
  .viz-legend .lg-dashed{border-top-style:dashed}
  .tree-tools{display:flex;gap:8px;margin:2px 0 10px}
  .tree{font-size:13.5px}
  .tree details{margin-left:16px;border-left:1px dashed #3a3a46;padding-left:10px}
  .tree > details{margin-left:0}
  .tree summary{cursor:pointer;list-style:none;padding:3px 0}
  .tree summary::-webkit-details-marker{display:none}
  .tree summary::before{content:'▸ ';color:var(--cyan);font-family:var(--mono)}
  .tree details[open] > summary::before{content:'▾ '}
  .tree .tleaf{margin-left:16px;padding:3px 0 3px 10px;border-left:1px dashed #3a3a46}
  .tree .tleaf::before{content:'● ';color:var(--cyan);font-size:9px;vertical-align:2px}
  .tree .tlab{font-family:var(--mono);color:var(--text)}
  .tree .tnote{color:var(--text-mute);margin-left:10px}
  .tree .tcount{font-family:var(--mono);color:var(--text-mute);margin-left:8px;font-size:12px}
"""

EXTRA_JS = r"""
/* ---- trees: expand / collapse buttons ---- */
document.querySelectorAll('.tree-tools').forEach(tt => {
  const tree = tt.nextElementSibling;
  tt.querySelector('.tree-exp').addEventListener('click', () => tree.querySelectorAll('details').forEach(d => d.open = true));
  tt.querySelector('.tree-col').addEventListener('click', () => tree.querySelectorAll('details').forEach(d => d.open = false));
});
"""

if __name__ == '__main__':
    main()
