# Selection Inspector

An Autodesk Fusion add-in that lists every entity in the active design in a dark, dockable table: sortable and resizable columns, parent/child path, instance count, instance status, live selection state and a show/hide checkbox per row. Rows highlight as you pick in the canvas or browser, and ticking **Selected** changes the Fusion selection.

**[⬇ Download the latest version](https://github.com/swami-claude-skills/fusion-addin-selection-inspector/releases/latest/download/SelectionInspector.zip)** · **[Documentation](https://swami-claude-skills.github.io/fusion-addin-selection-inspector/)** · **[All versions](https://github.com/swami-claude-skills/fusion-addin-selection-inspector/releases)**

## Install

1. Download **SelectionInspector.zip** and unzip it. Put the **SelectionInspector** folder somewhere it can stay (for example a Fusion add-ins folder in Documents); Fusion runs it from there.
2. In Fusion open **Scripts and Add-Ins**: press **Shift+S**, or click the **UTILITIES** tab, open the **ADD-INS** drop-down and choose **Scripts and Add-Ins**. Click the **+** next to **My Add-Ins** and choose the **SelectionInspector** folder.
3. Turn on **Run on Startup** and **Run** for **SelectionInspector**.

Nothing has to be approved in macOS Settings this way, because no installer script runs. The zip also has double-click installers for macOS and Windows; `READ ME FIRST.txt` inside it walks through all three ways.

The button is in the **INSPECT** panel of every tab. To give it a keyboard shortcut, right-click the button and choose **Change Keyboard Shortcut**; the shortcut survives reinstalls.

## In this repository

| Path | What it is |
|---|---|
| `SelectionInspector/` | The add-in exactly as it ships in the zip |
| `version.json` | Latest version, read by the documentation and the add-in's update check |
| `notes/` | Release notes, one file per version |
| `docs/` | The documentation page (GitHub Pages) and the design notes |
| `tools/build_release.py` | Builds `dist/SelectionInspector.zip` and refreshes `version.json` |
| `tools/build_docs.py` | Stamps the docs with the version and rebuilds What's New from `notes/` |
| `tools/install_steps.py` | One source for the install steps in the docs and `READ ME FIRST.txt` |
| `.github/workflows/release.yml` | Publishes a release when `version.json` changes, and refuses if the docs are stale |

## Releasing

1. Bump `VERSION` in `SelectionInspector/SelectionInspector.py`, the manifest's `version` and `UI_VERSION` in `palette.html`.
2. Write `notes/vX.Y.Z.md`.
3. `python3 tools/install_steps.py docs/index.html` and `python3 tools/build_docs.py docs/index.html`.
4. `python3 tools/build_release.py "One-line notes"`, then commit and push to `main`.

Vibe Coding: Swami · AI: Claude
