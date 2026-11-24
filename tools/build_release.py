#!/usr/bin/env python3
"""Build the release zip and refresh version.json for SelectionInspector.

Usage:  python3 tools/build_release.py ["One-line release notes"]

- Reads VERSION from SelectionInspector/SelectionInspector.py and checks that the manifest
  and the palette's UI_VERSION agree with it.
- Writes dist/SelectionInspector.zip (one folder, installers inside) with a fixed name,
  so https://github.com/<repo>/releases/latest/download/SelectionInspector.zip always
  serves the newest release.
- Rewrites version.json, which the add-in reads to tell users a newer version exists.
  Without notes it keeps the notes already in version.json for this version.
"""
import json, os, re, sys, zipfile, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
NAME = 'SelectionInspector'
ADDIN = os.path.join(ROOT, NAME)
REPO = 'swami-claude-skills/fusion-addin-selection-inspector'
SKIP_FILES = {'.DS_Store'}


def versions():
    py = open(os.path.join(ADDIN, NAME + '.py'), encoding='utf-8').read()
    version = re.search(r"^VERSION\s*=\s*'([^']+)'", py, re.M).group(1)
    man = json.load(open(os.path.join(ADDIN, NAME + '.manifest'), encoding='utf-8'))
    ui = re.search(r"const UI_VERSION\s*=\s*'([^']+)'",
                   open(os.path.join(ADDIN, 'palette.html'), encoding='utf-8').read())
    return version, man.get('version'), ui.group(1) if ui else None


def main():
    notes = sys.argv[1] if len(sys.argv) > 1 else ''
    version, man_v, ui_v = versions()
    if man_v != version or ui_v != version:
        sys.exit('version mismatch: .py=%s manifest=%s palette UI_VERSION=%s' % (version, man_v, ui_v))

    dist = os.path.join(ROOT, 'dist')
    os.makedirs(dist, exist_ok=True)
    zpath = os.path.join(dist, NAME + '.zip')
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        for base, dirs, files in os.walk(ADDIN):
            dirs[:] = sorted(d for d in dirs if d != '__pycache__')
            for f in sorted(files):
                if f.endswith('.pyc') or f in SKIP_FILES:
                    continue
                full = os.path.join(base, f)
                if os.path.getsize(full) == 0:
                    sys.exit('refusing to ship an empty file: ' + full)
                arc = os.path.relpath(full, ROOT)
                info = zipfile.ZipInfo(arc, date_time=(2026, 1, 1, 0, 0, 0))
                info.external_attr = (0o100755 if f.endswith('.command') else 0o100644) << 16
                info.create_system = 3
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, open(full, 'rb').read())

    vpath = os.path.join(ROOT, 'version.json')
    old = {}
    if os.path.exists(vpath):
        old = json.load(open(vpath, encoding='utf-8'))
    if not notes and old.get('version') == version:
        notes = old.get('notes', '')
    vj = {
        'version': version,
        'date': old.get('date') if old.get('version') == version and old.get('date')
                else datetime.date.today().strftime('%b %d, %Y').replace(' 0', ' '),
        'notes': notes,
        'zip': 'https://github.com/%s/releases/latest/download/%s.zip' % (REPO, NAME),
        'dashboard': 'https://swami-claude-skills.github.io/fusion-addin-selection-inspector/',
    }
    with open(vpath, 'w', encoding='utf-8') as f:
        json.dump(vj, f, indent=2)
        f.write('\n')
    print('built', zpath, os.path.getsize(zpath), 'bytes; version.json ->', version)


if __name__ == '__main__':
    main()
