# Selection Inspector — design notes

**v2.37.0**

How the add-in works and why it was built that way. For installing, see
[README.md](../README.md) or `READ ME FIRST.txt` inside the zip.

A non-modal palette that lists every entity in the active design in an interactive table:
sortable columns, drag-resizable columns with fit-to-widest, and a show/hide checkbox per row.
Rows matching the current Fusion selection highlight live as you pick in the canvas or browser.

## Selection matching

A pick in the canvas hands back a *proxy* — the entity as it appears inside an occurrence —
whose `entityToken` differs from the native object the scan collected off the component. Matching
on a single token therefore never succeeded, which is why the Selected column stayed blank and
"Selected only" appeared to do nothing. Each row is now indexed under every key it might be found
by (its own token, its native object's token, and a structural fallback for unsaved documents
where tokens aren't available at all), and a pick is matched against all of them.

## Install

Three ways, all described step by step in `READ ME FIRST.txt` in the zip and on the
[documentation page](https://swami-claude-skills.github.io/fusion-addin-selection-inspector/):

1. **In Fusion** (recommended): Scripts and Add-Ins (Shift+S) → **+** next to My Add-Ins → choose
   the `SelectionInspector` folder → turn on **Run** and **Run on Startup**.
2. **macOS installer**: double-click `install-macos.command`. macOS blocks it the first time; allow
   it in **System Settings ▸ Privacy & Security ▸ Open Anyway**.
3. **Windows installer**: **Extract All** first, then double-click `install-windows.cmd`. If
   SmartScreen appears, **More info ▸ Run anyway**.

Both installers copy the add-in into Fusion's per-user `AddIns` folder, replacing any older copy,
and leave themselves and `READ ME FIRST.txt` behind:

- macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/`
- Windows: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\`

## Where the button lives

**The INSPECT panel of every context tab** — SOLID, SURFACE, MESH, SHEET METAL and any other
tab that has one — promoted so it sits on the panel rather than in the overflow.

Those panels don't share a single id, and the ids differ between Fusion versions, so the add-in
discovers them at startup by walking every toolbar panel and matching on id or name rather than
hard-coding a guessed list. That keeps working when Autodesk adds or renames a tab. A panel that
refuses the button is logged and skipped, not fatal — the rest still get it. Teardown sweeps
*all* panels, so nothing is left stranded.

If no INSPECT panel exists at all, it falls back to the ADD-INS panel and notes that in the
Text Commands log.

## Keyboard shortcut

Fusion only offers a shortcut for commands that have an icon — this one ships with a
16/32/64 px icon set, so it's eligible. There's no API to hard-code a hotkey, so bind it yourself:

1. Hover the **Selection Inspector** button in the INSPECT panel.
2. Click the **…** on the button (or right-click it) → **Change Keyboard Shortcut**.
3. Press the key combination you want and confirm.

The binding is stored against the command definition, so the add-in deliberately **reuses** that
definition instead of deleting and recreating it on each run — deleting it takes the shortcut with
it, which is why bindings used to disappear on every reinstall. `stop()` therefore leaves the
definition registered (harmlessly: its handlers are released, so a stopped add-in does nothing)
and `run()` picks it back up, refreshing the tooltip.

One upstream quirk worth knowing: after a Fusion restart the shortcut sometimes isn't *displayed*
next to the command even though it still works. Open **Change Keyboard Shortcut** to confirm it's
still bound.

## The table

| Column | What it shows |
| --- | --- |
| **Show** | Light-bulb state. Tick/untick to show or hide. Disabled where visibility is read-only. |
| **Selected** | An active checkbox, both ways. It shows whether the entity is selected in Fusion right now, and ticking or unticking it changes the Fusion selection. Sorting it twice brings everything selected to the top. |
| **Entity Name** | Colored to match its Qty cell. The name as it appears in the browser. A tooltip appears only when the name was too long to show in full, and then it shows the name — not the path, which has its own column. |
| **Type** | Component, Body, Mesh, Sketch, Plane, Axis, Point, Joint — plus, with **Sub-entities** on, Face / Edge / Vertex and Sketch Point / Sketch Line / Sketch Arc / Sketch Spline etc. Color-coded by family and filterable from the dropdown. |
| **Qty** | Instance count, color-coded by placement state — suppressed (struck through), unplaced (pink), linked (violet), local (green), multiple (amber), single (yellow). Components resolve to linked or local; the count-based colors therefore apply to bodies and sketches. Precedence runs in that order; the **Legend** button opens the key in its own window. Each cell also explains itself on hover. |
| **Parent / Child Path** | The entity's **ancestry**, e.g. `root / Frame:1 / Bracket:1` for a rail inside `Bracket:1`. The entity's own segment isn't repeated here — it's the Entity Name column. Colored to match its Qty cell. Ancestry shared by every listed row folds into a leading `…` — see [Fitting long names](#fitting-long-names). The topmost element is always the literal `root` rather than the root component's name, which is identical on every row and just eats column width. |
| **Instance / Status** | For components: Local/Linked · instance *n* of *m* · grounded / suppressed / isolated / hidden by parent. For everything else: which component owns it and how many occurrences that component has (`Root component`, `4 occurrences`, `Unplaced`). |

### Columns flag, they don't resize

A column that is hiding text puts a **FIT** marker in its header. Clicking it fits that one column
to its widest entry. Nothing resizes on its own.

The marker used to be `⤢` (U+2922, Miscellaneous Symbols and Arrows) and reportedly rendered as
nothing at all — that block has poor coverage in monospace faces, and Fusion's CEF is old enough
that its font fallback can't be relied on. A marker you have to hope renders is not a marker.
Everything the palette draws is now ASCII, and a test enforces it.

That is the whole design decision. A column that widens itself shifts every column after it, under a
cursor that was aimed at something else — and "widest entry" is a property of the data, not of your
intent. On a table where one path is four times longer than the rest, auto-fitting is the wrong
answer often enough that it should be asked for rather than assumed. The marker also carries the
information that matters, which is *that something is hidden* — the fix is one click away either way.

Detection has to be uniform because the two ways text disappears are not. Entity Name and Path are
middle-truncated by `squeeze()`, so their text fits by construction and `scrollWidth` reports no
overflow at all; Qty, Type and Status simply overflow and get a CSS ellipsis. So the check is
`scrollWidth > clientWidth` **plus** whatever `squeeze()` had to shorten, folded in directly.

A marker that is always calm is a marker you stop seeing, so it **flashes three times** when it
first appears — about 1.3 seconds, over before it can nag — then sits quietly. It flashes again only
when a column starts hiding text that wasn't hidden before, never on a scroll or a redraw.
`prefers-reduced-motion` turns the animation off; the marker is still amber and still there.

The notice itself is a **bar directly above the table**, not a toast. A toast was the wrong
container three ways over: bottom-center when you're looking at the top, small and low-contrast,
and gone in five seconds. The bar sits above the columns it's describing, stays until it's dealt
with, and carries the action it's asking for — **Fit them**, or **Dismiss**. Dismissing is
remembered until the next scan, so a scroll can't raise it again, and the bar clears itself when
nothing is hidden any more.

The log keeps a copy for the record, since the log is a record rather than a notification: it
scrolls, and it can be hidden entirely.

### Column widths

Resizing produced four complaints that sounded like four bugs — a column that wouldn't drag wider
again after being dragged narrower, dragging one column moving others, a column snapping to its
widest entry unasked, and double-click fit-to-widest leaving text still truncated. They came from
three causes, none of them in the drag code.

**The layout algorithm was redistributing width.** A fixed-layout table whose used width exceeds the
sum of its columns hands the excess *back to the columns*. With `width: max-content; min-width: 100%`
there was always excess whenever the columns didn't fill the pane, so freed space flowed straight
back into the column you were trying to shrink, and into its neighbours.

Parking that excess in a trailing `width: auto` spacer fixes it on a current engine — but *how* the
excess gets split is exactly what older Chromium builds disagree on, and Fusion's CEF is old enough
that this file already avoids `:has()` for it. So there is now no excess at all: `applyWidths()`
measures the pane, gives the leftover to the spacer as a hard pixel width, and sets the table to the
exact total. Every width in the table is a number this code wrote.

**Everything re-clamped on every write.** `applyWidths()` used to run `clampW()` over all seven
columns each time it was called. The first render after data arrived therefore re-applied the
32-character cap to every column at once — so columns you never touched jumped, and it looked like
dragging one moved the others. Clamping now lives in `setWidth()`, which is the only thing that
changes a width, and it clamps only the column being changed.

**A 32-character ceiling was capping both.** Every column was limited to the width of 32 characters
in its own font. That's why fit-to-widest wouldn't reach a long entry and why dragging stopped
short — `MIP SCREEN FRAME ASSY (swamitized!)-A1` is 38 characters and could not be shown in full by
any means. The refusal was silent, which is what made it read as broken resize code.

The cap existed to stop one long entry from fitting its column into something enormous and shoving
the rest of the table off screen — the only defence against overflow back when a too-narrow column
just cut text off. Middle truncation replaced that defence: a narrow column now shows
`Rail-LEFT-EXTRU…6061-T6:1` rather than a useless fragment, so the ceiling had stopped buying
anything and was purely in the way. It's gone. What remains is `MAX_W`, a 4000px sanity bound that
exists so a stray value can't produce a column wider than any screen; you will not meet it by hand.

**Fit ignored everything that wasn't text.** It measured the widest string and added a flat 22px,
counting neither the caret, nor a nested row's indent, nor a `3 of 248` chip — so a fitted Entity
Name column came out roughly a caret and an indent too narrow, and every name stayed truncated.
`cellOverhead()` now measures a real cell of each row kind (plain, nested, group) and takes the
worst, and fit measures the text the column actually prints — for Path that's the ancestry, not the
raw field.

**And in the end there were two measurements.** The FIT marker decided a column was cut off from
`squeeze()`'s record of what it had shortened; Fit decided the same question with its own arithmetic.
They disagreed, and the log said so out loud:

```
Fit: "Entity Name" (FIT marker) — 257→329px
"Entity Name" is too narrow for the content — use FIT in the header…
Fit: "Entity Name" (FIT marker) — already fits
```

Three lines, one column, mutually exclusive conclusions. The fix isn't to find the discrepancy — it's
to stop having two of them. `columnShortfall()` is now the single answer to *"how much wider does
this column need to be?"*; the marker lights when it's above zero, and **Fit widens until it isn't**,
in a bounded loop. Fit's success is defined as *the marker goes out*, so the two cannot disagree by
construction. When the pane genuinely isn't wide enough, it says that instead of claiming success.

**And it could not see the row that was actually too narrow.** Fit measured `view` — the entity
rows — but a **group** header (`Sketch Curve × 4`, plus a `1 of 4 selected` chip) is not in `view`
at all, so its label was never measured. The verification pass didn't catch it either: a name cell
is a flex row, and a flex item *shrinks* rather than overflowing, so a truncated name reports
`scrollWidth === clientWidth`. Fitting that column twice changed nothing while the FIT marker stayed
lit, which is exactly what it looked like.

`columnShortfall()` now asks squeeze's question instead — does the full string fit the space the
span actually has — which covers entity rows, group rows and their chips alike, and it corrects
twice, because widening a column can expose a second row that the first one's truncation was hiding.

**And it never said what it did.** If fit computed widths close to the current ones, nothing moved —
and with the log hidden by default there was no way to tell *"did nothing"* from *"did nothing it
needed to"*. Both read as broken. **Fit columns** now reports into the notice bar: which columns
changed and from what to what, or plainly that every column already fits. Fitting a *single* column —
the FIT marker in a header, or a double-click on a divider — reports the same way, for the same
reason. A column that can't be
measured is named rather than silently skipping the other six.

**And it measured a string nobody was rendering.** Canvas `measureText` knows the font and nothing
else: it does not apply `text-transform`, and it does not add `letter-spacing`. The **Type** column
is a pill with both (`uppercase`, `.08em`), as is every column header — so fit came back short every
time, and a column it had just "fitted" stayed truncated. `textMetrics()` reads the transform, the
spacing and the pill's own padding and border off the element; `renderedWidth()` applies them.

Because a measurement can still be wrong, fit no longer trusts itself: after setting the width it
compares `scrollWidth` against `clientWidth` on the cells actually on screen and, if anything still
overflows, grows the column by exactly the shortfall. Estimate for the rows it can't see, real
layout for the ones it can.

### Fitting long names

Real assemblies defeat a fixed-width table twice over. Component names run long
(`Rail-LEFT-EXTRUSION-6061-T6:1`), and every path repeats the same ancestry, so a document called
`MIP SCREEN FRAME ASSY (swamitized!)-A1` spends forty identical characters per row before reaching
anything that varies. Widen every column to suit and the table no longer fits the palette; leave
them narrow and a plain CSS ellipsis cuts the tail — which in CAD is exactly where the
distinguishing part lives: `:1` versus `:2`, `-LEFT` versus `-RIGHT`, the `-A1` revision.

Two things address that:

**The entity's own segment is dropped.** Path is the *ancestry*, not the full chain. The last
segment is the entity itself, which the Entity Name column already shows in full — repeating it
spent the widest column in the table saying nothing new.

**Shared ancestry hidden.** What every listed row has in common folds into a leading `…`, so a rail
whose ancestry is `root / MIP SCREEN FRAME ASSY (swamitized!)-A1 / Frame Weldment` displays as
`… / Frame Weldment`. Only whole segments are stripped — a path trimmed mid-segment reads as valid
and isn't — and the immediate parent is never stripped, so the column always names *something*. A
`…` chip in the header says what's hidden, and every cell keeps its full ancestry in its tooltip.

The prefix is recomputed against what's *listed*, not what exists, so filtering to one sub-assembly
shortens the paths further. That's the intent — the column shows what currently varies — but it
does mean paths shift as you filter.

**Middle truncation.** What still overflows is cut from the middle rather than the end, keeping both
ends: `Rail-LEFT-EXTRU…6061-T6:1`. Names split near evenly (`tail: 0.42`); paths keep more of their
tail (`0.62`), since their last segment is the entity itself.

CSS has no middle ellipsis, so this is measured — the same canvas metrics that back **Fit columns** —
and re-measured whenever a width changes. Three details make that affordable and safe:

- **Only visible rows are measured.** Rows outside the viewport keep the CSS ellipsis until you
  scroll to them. A 3000-row table therefore costs one screenful of measurement per frame while
  dragging a column edge, not three thousand.
- **Width is read from the cell, never from the span.** A flex item measured after its text shrinks
  reports the shorter width; measuring the span would ratchet the text smaller on each pass and
  never let it grow back.
- **The CSS ellipsis stays underneath as the fallback.** If measurement fails or never runs, text is
  tail-clipped as before rather than lost, and `squeeze()` is wrapped so a display error can't take
  the render with it.

Everything here is display-only. Tooltips, sorting, filtering, the log, and every id sent back to
Fusion use the full strings — filtering on text hidden inside a folded prefix still matches.

### One color per row

Entity Name, Qty and Parent / Child Path all take the row's placement color, so a row reads as a
single signal instead of three things to cross-reference. Placement is the axis you scan a long
list for — which of these is linked, which is unplaced, which got suppressed — and the eye follows
a color across a row faster than it re-reads three columns.

The **Type** column deliberately keeps its own family colors. Type and placement are independent
facts about an entity, and collapsing both onto one palette would leave the table encoding less
than it does now, not more.

Group headers stay neutral in all three columns, because a group of 248 faces has no single
placement state to report.

Two implementation notes worth keeping:

- The name color lands on the inner `.txt` span, not the cell. `tbody tr.sub td.c-name` and
  `tbody tr.off td.c-name` outrank any two-class selector, but a declaration on the span beats an
  inherited one whatever the cell's specificity. Path has no such competing rules, so its color
  sits on the cell.
- Hidden and sub-entity rows used to signal themselves by dimming the name's color, which the
  placement colors overwrite. That cue is now opacity, so a row can be both hidden and legibly
  color-coded.

### Component, occurrence, instance

A **component** is the definition — geometry, sketches, bodies, joints — and exists once. An
**occurrence** is one placement of it in an assembly, with its own position and visibility; the
`:1` suffix on a name is the occurrence number. Every node in Fusion's browser tree is an
occurrence, even though the UI mostly says "component".

Rows are typed **Component**, matching the browser and everyday usage. The occurrence dimension
stays visible three ways: the `:N` suffix in the name, the **Instance / Status** column
(`Local · instance 2 of 3`), and the **Qty** column counting placements. Hovering the Component
tag spells it out — *One placement (occurrence) of this component — Local · instance 2 of 3*.

Occurrences are grouped by their component definition using a key built from the component's
token, id *and* name together. No one of those is reliable alone — entityToken is not distinct
across linked/external components — and a collision merges unrelated components, reporting four
separate top-level components as "instance 1…4 of 4".

Entities owned by a component are listed **once per component definition**, not once per instance —
so a 40-copy assembly gives you one `Rail` row with Qty 40 instead of 40 identical rows.
Toggling it affects every instance, which is how the light bulb behaves in Fusion anyway.

## What you get on open

Everything off. The palette opens showing the design, not a previous session's settings:

| | |
| --- | --- |
| Tab | **List** |
| Filter / type filter | empty / all types |
| Selected only, Sub-entities, Reveal selected | off |
| Log pane | hidden |
| Visibility | **All**, with Show all / Hide all untouched |
| Tools | nothing lit; Under-constrained disabled outside a sketch |

The title bar reads **Selection Inspector (v2.34.0)** — parenthesized, lower-case `v`.

Setting those defaults wasn't enough on its own. The palette still opened on whatever tab you last
used with the log still showing, because `savePrefs()` stored the active tab and the log's
visibility and `loadPrefs()` restored them — so a session that happened to end on **Tools** reopened
there forever. **Opening state is not a preference.**

What is stored: log height, copy mode, column widths — how things look once you're using them —
plus whether to check for updates. What isn't: the active tab, whether the log is showing, and which
toggles are lit. Older stored values for those are ignored rather than read back.

## Settings and Reset all

Since v2.37.0 the stored preferences live in a settings file outside the add-in folder, so
reinstalling (which wipes the folder) and clearing Fusion's web cache both keep them:

- macOS: `~/Library/Application Support/SwamiFusionAddins/SelectionInspector/settings.json`
- Windows: `%APPDATA%\SwamiFusionAddins\SelectionInspector\settings.json`

`DEFAULTS` in `SelectionInspector.py` is the factory state and the schema. Loading merges the file
over it, so a setting added in a later version appears with its default, and unknown or out-of-range
values are dropped. The first time v2.37.0 runs, the widths, log height and copy mode the palette
had in browser storage are copied into the file once.

**Tools ▸ Reset all** asks first, then puts every stored preference back to `DEFAULTS` and returns
the palette to its opening state: List tab, log hidden, filter and type filter cleared, Selected only,
Sub-entities and Reveal selected off, natural sort order, default column widths.

## Errors and updates

Errors from either side show in a red strip at the top of the palette as well as in the log, because
a docked panel that silently does nothing is the hardest failure to diagnose. Click it to dismiss.

Each time the palette opens (at most once every two minutes) it reads `version.json` from GitHub on
a background thread. When a newer version is out, a green bar offers **Install update**, which
downloads `SelectionInspector.zip`, backs up the current files to the settings folder and replaces
them; then turn the add-in's Run switch off and on in Scripts and Add-Ins. **Tools ▸ Check for
updates** checks on demand, **Tools ▸ Auto-check** turns the automatic check and its green bar off
or on (saved as `checkUpdates`), and **Tools ▸ Docs** opens the documentation.

The title bar reads **Selection Inspector (v2.34.1)** — parenthesized, lower-case `v`. Fusion
renders palette titles in capitals, so on screen it shows as `(V2.34.1)`; that's Fusion's styling,
not the string.

The development tests (not part of this repository) assert the opening state as declared and as
rendered, and drive two sessions against one storage — end the first on Tools with the log open, and check the second still
opens on List with it hidden.

## The toolbar

Controls are grouped into four tabs, one panel visible at a time:

| Tab | Holds |
| --- | --- |
| **List** | What the table lists — text filter with its **×**, type dropdown, **Selected only**, **Sub-entities** |
| **Visibility** | What's shown in the viewport — the All / Selected / Not selected radios, **Show all**, **Hide all** |
| **Columns** | **Fit columns** |
| **Tools** | **Under-constrained**, **Legend**, **Log**, **Check for updates**, **Auto-check**, **Docs**, **Reset all** |

**Refresh** sits outside the tabs, on the tab strip itself, so a rescan is one click away wherever
you are. The palette always opens on List (see "What you get on open").

## Interactions

- **Sort** — click a header: ascending → descending → back to natural order.
- **Resize** — drag the right edge of any header. Double-click it to fit that column to its widest entry, in full — there is no width ceiling.
- **Fit to widest** — double-click a header's right edge to fit that one column; **Fit columns** in the toolbar fits them all. Widths are measured against the actual rendered text. Since v2.37.0 they are saved to the settings file (see "Settings and Reset all"), so they persist reliably.
- **Legend** — opens `legend.html` as its own floating palette: a vertical list of color swatches and what each means, with no quantities in it. Non-modal, so you can leave it open beside the table or drag it anywhere.

  It opens fully expanded — no scrolling, nothing clipped — because the page measures its own content once webfonts have settled and hands the size back to Fusion, which resizes the window to match. Descriptions are `nowrap`, so the width follows the longest line rather than a number I guessed. Python clamps the result to sane bounds in case the measurement ever comes back degenerate.

  The window is **not resizable** — it opens at exactly the size its content needs, so there is
  nothing to adjust. Closing the Selection Inspector closes the legend with it; the legend is only
  hidden rather than destroyed, so the button brings it straight back.

  It anchors with its **top-right corner on the table palette's top-left corner**, floating rather than docked, and re-anchors every time you open it so it follows the table around. If the table palette is docked (no meaningful coordinates), the legend is left wherever Fusion put it rather than being thrown to 0,0. The button mirrors whether the window is open, and `stop()` disposes of it.
- **Reset all** (Tools tab) — asks first, then restores every setting and the opening state; see "Settings and Reset all".
- **Select** — tick the **Selected** checkbox to select that entity in Fusion, untick to deselect. The palette sends the complete desired set each time rather than a delta, so the table and Fusion can't drift apart. A nested body is selected through its occurrence proxy, since Fusion won't take the raw component-level object. Hidden entities can't be selected in Fusion at all — that comes back as a message rather than a checkbox that silently springs back.
- **Rows are still inert** — left-clicking a row does nothing. The two checkboxes and the caret are the only left-click controls in a row.
- **Right-click a name** — a small menu offers **Show in Browser**, **Show in Window** and **Show in Timeline**. Each selects that entity in Fusion, then runs Fusion's matching Find command. Only `FindInWindow` is documented. Each destination carries a list of likely ids and, when none of
them resolve, searches Fusion's live command list for a definition whose id or name mentions the
destination *and* reads as a find/show command. Merely matching the word isn't enough — "Play
Timeline" contains "timeline", and running it because the name overlapped would be worse than
reporting nothing. The id that worked is logged and cached, so the search happens once per session.
If nothing suitable exists, the log names the related commands that do, which is what makes a miss
diagnosable instead of dead.
- **Selected only** — toggle in the toolbar, with a live count of what Fusion has selected. Narrows the table to just those rows and re-lists automatically as the selection changes. If nothing is selected it says so rather than just emptying.
- **Sub-entities** — toggle in the toolbar. Off by default; switch it on to also list sketch points and curves, and body faces, edges and vertices. These have no light bulb of their own in Fusion, so their Show checkbox is disabled and mirrors their owner. Capped at 12,000 sub-entity rows, and the table renders the first 3,000 rows at a time.
- **Reveal selected** — when something is picked in Fusion, open whatever it's buried under and scroll to it. A picked face has a row, but that row sits inside a collapsed type group inside a collapsed body, possibly thousands of rows down; a table that reports `1 rows matched` and won't show you which one isn't much help. It only ever *opens* rows — nothing you expanded gets closed — it leaves the scroll alone if the row is already on screen, and it re-renders only when it actually had to open something. On by default; the toggle is remembered.
- **Grouping** — with sub-entities on, the table becomes a three-level tree, everything closed by default:

  ```
  ▸ Housing                Body
      ▸ Face × 248         Face
          Face 1           Face
      ▸ Edge × 612         Edge
  ```

  The parent entity row gets a caret when it owns sub-entities; opening it reveals one group per type, and opening a group reveals its entities. So switching sub-entities on adds carets rather than thousands of rows, and a 248-face body costs nothing until you ask for it. Open/closed state is remembered while you work, so collapsing a parent and reopening it leaves its groups as you left them.

  Only the caret is clickable on an entity row — clicking the name or path still does nothing, per the rule that rows are readouts. Group rows are clickable anywhere, since they're not entities.

  A group carries its own tally: `Face × 248` with a `3 of 248 selected` chip, and the Qty column
  reads `3 / 248`. The parent row rolls the same figure up across every type it owns
  (`5 of 8 selected`), so a collapsed row still tells you how much of it is picked. Both appear
  only when something is selected.

  The group's checkbox selects or deselects the whole run and shows indeterminate when only part of it is selected. A **parent** row shows the same hyphen when something inside it is selected but the parent itself isn't — so a collapsed row still tells you there's a selection buried in it. If the parent entity is itself selected, its own tick wins. Ticking a parent selects only that entity; children are left alone. Sorting and filtering still apply — they order rows within each level rather than interleaving sub-entities from different owners. If a filter hides a parent but keeps its children (filtering to `Face`, say), that parent's groups are promoted to the top level so they're still reachable.
- **Show all / Hide all** — applies to whatever is currently listed, so filter first, then bulk-toggle.
- **All / Selected / Not selected** — radio group that *sets* viewport visibility from the Fusion selection, rather than filtering the table. `Selected` hides everything except the selection (switching on its parent occurrences so it's actually visible); `Not selected` hides the selection and shows the rest; `All` shows everything. Each click writes real light-bulb state, so it lands in Fusion's browser tree, and the response is a full rescan — the Show column always mirrors the browser rather than drifting from it. Sub-entities are skipped, since faces and sketch geometry follow their owner. With nothing selected, `Selected` and `Not selected` say so and leave the model alone.
- **Filter** — free text across name, path, status, type and selection state, plus a type dropdown. Esc clears the text filter *and* resets the visibility radios to All.
- **Under-constrained** — runs Fusion's `sketch.showunderconstrained` text command. Grayed out and unclickable unless Fusion is actually in a sketch edit session, with a tooltip naming the open sketch when it is. The palette can only ask for commands on a small allowlist — it can't pass arbitrary text through to Fusion.
- **Log** — a resizable pane at the bottom of the table, on by default (the **Log** button hides it). It records a full interaction trace: every button, radio, dropdown choice, Show and Selected checkbox, group checkbox, caret, and even clicks on an entity name — which do nothing, and the log says so. Clicks are captured *before* the action they trigger, so the log reads as cause then effect (`Click: Show all` followed by `Shown 12 item(s)`). Interaction lines sit in a dimmer color than results, so a scan of the log still picks out what actually changed.

  Each outcome is logged once. Where Python already reports a result, the palette's matching toast
  is marked silent — it still appears on screen but doesn't write a second line. Without that, a
  single action produced two near-identical entries and read as though it had happened twice. Drag the divider above it to resize; **Copy** honors the **Color / Plain** choice beside it, which defaults to Color and is remembered.
  Color puts the log on the clipboard in two flavours at once: `text/html` so colors survive a
  paste into anything rich (Word, Google Docs, email, a Vibe dashboard), and `text/plain` for
  editors and terminals — the destination picks whichever it understands. Plain puts only the
  text flavour on the clipboard, for when a destination would otherwise pick up styling you
  don't want. The HTML sits on a pure black background, declared on every line and every text run rather than
  on a wrapper — rich-text converters map background color onto character runs and discard a
  block's backdrop, so a wrapper-only background pastes as white, and its colors are darkened versions of the on-screen palette so a line stays
  readable whether that background survives the paste or the target strips it. It copies via a throwaway textarea, since
  Fusion's `file://` origin isn't a secure context and the modern clipboard API is absent there —
  its absence used to fail silently and leave the previous clipboard contents in place, **Save** writes the log to your Desktop as a standalone HTML file (plus a `.txt` sibling) —
  the reliable way to keep the colors, since it renders exactly as written instead of passing
  through whatever converter the destination app uses. **Clear** empties it.

  A note on pasting into **TextEdit**: its *Use Dark Background for Windows* setting inverts black
  and white inside the window, so the black backdrop arrives as white. That's TextEdit redrawing
  the document, not the clipboard data — turn that setting off, paste into another app, or use
  **Save** instead. It records what the add-in is doing — every message that appears as a toast, plus events pushed from Python: commands run, visibility changes, entities Fusion refused to select, and errors, each timestamped and color-coded. On connect it logs the version and folder actually running, so the true version is always one click away.
- **Timeline sync** — the table follows the history marker. Roll it back and the rows rebuild to match that point in history; roll forward and they come back. The footer shows `timeline 12/34`, tinted amber and marked *(rolled back)* while you're not at the end.

  Fusion has no "marker moved" event, so this rides on `commandTerminated`: after every command the add-in compares the marker position and length, and rescans only when one has actually changed. That also catches a new feature being added, not just the marker being dragged. A marker move rebuilds the model, so row ids no longer refer to the same entities — the expansion state is dropped rather than reopening arbitrary rows. An ordinary refresh leaves the tree as you had it.
- **Refresh** — rescans the design (also on F5/Ctrl-R, and automatically when you switch documents).

Each **Show** checkbox drives its own row only — no action-at-a-distance from whatever happens to
be selected in Fusion. For bulk visibility work, turn on **Selected only** (or filter) and use
**Show all / Hide all**, which act on exactly what's listed.

### Showing something also shows its parents

Ticking **Show** on a nested entity switches on every parent occurrence above it as well.
Without that, the tick does nothing you can see — Fusion keeps a child hidden while any
ancestor's light bulb is off, which reads as a broken checkbox. When parents get switched on,
the toast says so (`Shown 1 item(s), plus 2 parent(s) that were hidden.`) and the table rescans
so those parent rows show their new state.

**Hiding never touches parents** — hiding a rail shouldn't blank the whole frame.

### Two selection counts

The status bar separates them deliberately:

- **N selected in Fusion** — raw count of entities selected in Fusion, faces and edges included.
- **N rows selected** — how many table rows that maps to.

That second one used to read *"N rows matched"*, which was misread as *rows matching the filter* —
a reasonable reading, since the filter box is right there and has its own count. Both labels were
changed rather than explained: the filter's readout now says **"2 of 7 listed"** whenever a filter
is narrowing things, so neither number needs a footnote.

They differ when you pick geometry that has no row of its own: select three faces of one body and
you'll see `3 selected in Fusion` / `1 rows matched`, because all three resolve to the same body —
which reads `SELECTED` in the Selection column, since that body is what's picked in Fusion.

## The status bar

The strip along the bottom — the counts, the timeline position and the LIVE badge. Standard names
for it are **status bar** or **status strip**; in the source it's the `<footer>` element. It reads:

```
STATS:  20 entities  20 listed  20 visible  0 selected in Fusion  0 rows matched  timeline 5/5  LIVE
```

The `STATS:` label is there because the row is otherwise a wall of unlabeled numbers with no
indication of what kind of thing it is.

The active document's name used to sit at the left. It's gone: Fusion already shows it in the
document tab directly above, and at 230px of ellipsized filename it was the widest item in the bar
while being the one piece of information you never had to look here for.

## Why Sub-entities got slow, and what fixed it

There were two separate costs, on opposite sides of the bridge. The scan happens in Python before
anything is drawn; the render happens in the palette afterwards. A log line reports the scan
duration, which is what tells the two apart.

### The scan: entityToken, twelve thousand times

A Sub-entities scan of a 12,000-entity model took **78 seconds**, all of it before a single row was
drawn. Almost all of that was one property.

Every row is indexed by its identity keys so that a canvas pick can be matched back to it, and
`_keys()` reads `entityToken` twice — once on the entity, once on its native object. `entityToken`
is not a field read: it serializes a *persistent* reference to the entity, which costs milliseconds.
That's fine for the few hundred bodies, sketches and components in a design. It is ruinous for
twelve thousand faces and edges: about 24,000 token serializations, which is the 78 seconds almost
exactly.

Sub-entity keys exist for exactly one purpose — matching a pick — so they are now computed when a
pick needs them. During the scan a sub-entity row is stored and queued against its owner; the first
time you pick a face, that one body's children get indexed and the lookup retries. The cost is
bounded by a single body or sketch, and it happens once. Picking a second face in the same body is
a dictionary hit.

A smaller waste went with it: once the 12,000 cap was reached the scan kept enumerating every
remaining body's face, edge and vertex collections, paying full price for rows it had already
decided not to add. It now stops before enumerating.

### The render: 3,000 rows of DOM for the 40 on screen

Switching **Sub-entities** on turns a 400-row table into a 12,000-row one, and it got noticeably
slower around v2.24.0. Measured against the same 12,000-row dataset, `render()` cost 2.2x what it
had in v2.23.0. The staleness check added in v2.28.0 was not the cause — it accounts for about 2%.

The cost was DOM construction. The table built rows for everything it was willing to show, up to
`RENDER_CAP`, so roughly 3,000 rows of elements were constructed on every render. About forty of
them fit on screen.

**Rendering is now windowed.** The row list is planned but not rendered; only the slice around the
viewport becomes DOM, with two spacer rows standing in for everything above and below so the
scrollbar keeps the length it should have. Scrolling repaints the slice — a few dozen rows instead
of a few thousand. On the same dataset that is 34 ms against 3,777 ms, about 110x.

Three consequences are easy to get wrong and are handled explicitly:

- **Striping** comes from an `alt` class computed from the absolute row index. `nth-child(even)`
  stripes by position in the DOM, and with a sliding window the stripes would crawl as you scroll.
- **Spacers must never be mistaken for rows.** They're `pointer-events: none`, and every selector
  that samples "the first row of kind X" — column fitting, cell-overhead measurement, truncation —
  excludes them.
- **Not rendered is not absent.** Filtering, sorting, counts and everything sent to Fusion work from
  the model, so a row 4,000 places down the list is still found by the filter box.

Two smaller savings landed alongside: each row's ancestry is computed once when rows arrive rather
than on every render, and the path cell no longer carries a third copy of its own text in a data
attribute — `squeeze()` recovers the untruncated string from the tooltip it already needs.

## When do I have to press Refresh?

Ideally never, and the table now tells you the exception rather than leaving you to guess.

**It rescans itself** when the selection changes, when you switch documents, when the history
marker moves, and — new in v2.28.0 — when a command leaves the model with a different fingerprint.

That last one closes a real gap. Fusion has no "the design changed" event. The timeline covers most
edits, but not all: renaming a body and toggling a light bulb in the browser both leave the marker
exactly where it was, so a table watching only the timeline went quietly out of date with nothing on
screen to admit it. `Component.revisionId` moves whenever a component is modified in any way, so
after every command the add-in hashes every component's revision — no geometry traversal, cheap
enough to do constantly — and compares. If `revisionId` isn't available it falls back to component
and occurrence counts, which is weaker (a rename won't move it) but never throws.

**It asks you** only when rescanning would be intrusive. Full scans are timed; if the last one took
longer than `AUTO_SCAN_MS` (300 ms), a changed fingerprint doesn't trigger a rescan. Instead the
**Refresh** button turns amber and pulses, a **MODEL CHANGED** chip appears in the status bar, and
the log says how long the scan takes and what the limit is. Both indicators clear together the
moment a fresh scan lands, and a fresh scan can never be stale by definition.

So: **if Refresh isn't lit, you're looking at the current model.** Stale means the table is behind,
not that it's wrong — the rows on screen were accurate when they were built, and stay usable until
you catch up.

### The cost of a pick

Picking a sub-entity redraws the table, and at 44,000 rows that started to drag. Profiled, one
selection change cost 149 ms in the harness, of which **44 ms was recomputing the shared path
prefix** — splitting all 44,000 paths — for an answer that cannot change when the selection changes.
It's now memoized against the things that actually decide it (row count, filter text, type filter,
Sub-entities, Selected only). Three other whole-table passes went the same way:

- `annotateSelection()` walked every row to set two fields; it now touches only the rows whose
  state actually changed, which is the handful you picked plus the handful you unpicked.
- `revealSelection()` walked every row looking for selected ones; it now walks the selection.
- `updateCounts()` allocated a fresh 44,000-element array via `rows.filter` on every render, to
  produce one number. It counts in place. Not cached — a visibility toggle changes it, and a stale
  count is worse than a cheap loop.

The parent → type → children map that `buildDisplay()` rebuilt every render went the same way — it
depends only on which rows are listed, so it's cached against the same key, and the *"3 of 248
selected"* counts are now derived from the selection (a handful of ids) instead of by re-filtering
every child list.

Measured on 44,139 rows, median of 30, DOM writes excluded so the number reflects what changed:
**56.7 ms → 4.6 ms per selection, about 12x.** The DOM write on top is a few dozen rows either way,
since rendering is windowed.

On the Fusion side, matching a picked face to its row can mean indexing its owner's deferred
children for the first time. That now **stops at the row it was looking for** and leaves the rest
deferred, so picking the third face of a 3,000-face body doesn't index all three thousand. Two picks
in the same body still cost no more in total than indexing it once.

Both halves are timed. If a pick takes more than 250 ms the log says where it went — *"Selection
took 610 ms — 480 ms matching in Fusion, 130 ms redrawing 44,139 rows"* — because when this feels
slow, which half it is determines what to do about it.

### Sub-entities load when you open them

Turning **Sub-entities** on used to walk every body's faces, edges and vertices up front — even
though every group starts collapsed and you might open two of them. That walk was the whole cost:
6 seconds at a 12,000 cap, 101 seconds at 50,000. Enumerating a BRep collection is milliseconds per
entity and no amount of work on this side of the bridge changes that.

So it doesn't enumerate any more. The scan asks each body and sketch how many children it has —
`faces.count`, `edges.count`, `sketchCurves.count`, which are free — and emits a group row saying
`Face × 248 · not loaded`. **Expanding that group is what fetches those 248 rows**, for that one
body and that one type. Collapsing keeps them; reopening is instant.

Three consequences, each handled:

- **A pick can be for a row that doesn't exist yet.** Select a face whose group is closed and there
  is nothing to highlight. Python reports which group the picked entity *would* be in, and with
  **Reveal selected** on, that one group is loaded and opened. You pick a face, the table shows it.

  Those hints arrive two ways, and v2.33.0 only handled one: with a **selection push** (you picked
  something) and with a **full payload** (you switched Sub-entities on, or turned Reveal on, while
  something was already picked). The second is exactly the moment a pick most needs its group, and
  it was silent — which made the whole feature look broken. Both paths now go through one
  `applyHints()`, and turning Reveal on re-asks Fusion rather than re-rendering rows that were never
  built.
- **Filtering and sorting only see rows that exist.** That's the real cost of this design, so there's
  a **Load all (N)** button that appears whenever anything is still counted-but-not-built, states how
  many rows that is, and warns that it's the slow path — because it's the 100 seconds this change
  was made to avoid.
- **A group knows two different numbers**: how many rows it will have (always) and how many it has
  (once loaded). The group row shows the first. Confusing the two is the bug this design invites, so
  the tests check it specifically.

`SUB_ENTITY_CAP` (12,000) still bounds **Load all**, and nothing else — a normal scan can't reach it.

## Flashing an entity

Click **anywhere in a row** and its entity blinks in the viewport, until the pointer leaves that
row. (v2.35.0 only listened on the Entity Name cell, so a click on Type or Path did nothing and the
feature looked dead — which is how it was reported.) Checkboxes and carets keep their own jobs.

Every flash reports into the log: how the entity was drawn, or why it couldn't be. "Nothing
happened" and "the click never landed" look identical otherwise.

**It does not select it.** That's the constraint the whole design follows from — selecting would be
the obvious way to point at something, and it would destroy the one thing the table exists to show,
which is what *you* have picked. Fusion has no "highlight without selecting" API, so the add-in
draws its own overlay with **custom graphics**: view-only, no document change, gone on `deleteMe()`.

Each kind of entity gets the best representation available, and every attempt is guarded because
none of these are guaranteed across Fusion builds:

| Entity | Drawn as |
| --- | --- |
| Face | its display mesh |
| Body, mesh body | the body |
| Edge | its curve |
| Sketch geometry | its **world** geometry, so the sketch's plane transform is already applied |
| Anything else | a bounding-box wireframe |

The bounding box is the floor: worse than the real shape, but always available and unmistakable. If
even that can't be built, the palette says so instead of leaving you looking at an unchanged viewport.

The blink timer lives in the palette, because an add-in has no reliable one — Fusion just applies
whichever half of the blink it's told. The overlay is cleared when the pointer leaves the row, when
the table rescans (row ids change), when the window loses focus, when the table scrolls, and when
the add-in stops.

### Selected sub-entities you can't see yet

Sub-entity rows are built on expand, so a selection can include entities that have no row. The
status bar used to read `31 selected in Fusion · 1 rows selected` with no explanation, which looks
like the table has lost track of the selection.

It now says `1 (+2 in unopened groups)`, with a tooltip naming what to do about it. The group hints
Python already sends are recorded whether or not **Reveal selected** is on — Reveal acts on them,
but they answer the question either way. Loading a group also reports how many rows arrived, and
says so when the answer is none.

## Under-constrained

Fusion has no API for "show under-constrained geometry"; the only route is the text command
`sketch.showunderconstrained`, run through `Application.executeTextCommand`. The button is disabled
outside a sketch, because that's the one precondition worth checking in advance.

When it fails, it now says something. It used to print

```
Fusion refused "sketch.showunderconstrained":
```

— with nothing after the colon, because Fusion raised an exception carrying **no message** and the
handler printed it regardless. A blank reason reads as a broken add-in rather than as Fusion
declining.

Three changes:

- **More than one spelling is tried.** Text command names are undocumented and their casing has
  varied between builds, so the entry is a list; the one that works is logged, so a spelling only
  has to be discovered once.
- **An empty exception is reported as `(no message)`**, and every attempt is listed.
- **A rolled-back history marker is named as the likely cause.** Fusion refuses this command while
  the timeline is not at the end — the sketch is open, the button is enabled, and it still fails,
  which is exactly the state that produced the report. The message says where the marker is and to
  roll it forward.

## Error handling

- Expected problems (no design open, palette file missing, read-only visibility) surface as plain messages — no traceback noise.
- Unexpected errors are caught at every Fusion boundary (`run`, `stop`, every `notify`) and written to the Text Commands log with a full traceback, so the add-in never fails silently.
- Bulk visibility changes collect per-item failures instead of aborting on the first: failed rows revert, get marked read-only, and a toast names the first failure.
- `stop()` removes the button, the command definition, the palette and both application event subscriptions, so reloading never stacks duplicate buttons.

## Live vs. preview

The footer carries a badge:

- **LIVE** (green) — the palette is talking to Fusion; everything you see is your real design.
- **PREVIEW** (amber) — Fusion's JS bridge wasn't detected, so the table is showing a small
  built-in demo dataset. That's the expected state when you open `palette.html` in a browser.

Fusion injects its bridge object into the palette *after* the page script runs, sometimes a
second or two later on a cold start, so the palette polls for it for ~12 seconds and switches to
LIVE the moment it appears. If it ever sticks on PREVIEW inside Fusion, hit **Refresh**, and check
**Utilities → Text Commands** — every message the palette sends is logged there as
`Selection Inspector: <- ready`. No such line means the bridge never came up.

## Version numbering

`VERSION` in `SelectionInspector.py` is the single source of truth. The manifest must carry the
same string, and the palette title, the button tooltip and the log banner are all derived from it.

The scheme is semantic versioning, judged by what changes for *you*, not by how much code moved:

| Part | Bumped when | Examples from this add-in |
| --- | --- | --- |
| **Major** | Existing behavior is deliberately reversed | `2.0.0` — the Selected column became a control that writes to the Fusion selection, reversing the earlier rule that the table never touches it |
| **Minor** | A new capability appears | `2.1.0` grouping · `2.2.0` collapsible parents · `2.5.0` the log pane · `2.7.0` selection counts · `2.9.0` the Color/Plain choice |
| **Patch** | A fix, with nothing new to learn | `2.2.1`/`2.2.2` the row-height bugs · `2.7.1` Copy writing nothing · `2.9.1`–`2.9.3` diagnostics and copy fixes |

A patch release should never change how you use the add-in — if the README needs a new sentence
describing something you can now do, it isn't a patch.

### Code and palette versions

The add-in is **two files loaded by two different things**: Fusion imports
`SelectionInspector.py`, and CEF loads `palette.html`. They can disagree.

That cost three releases. The palette title bar and the startup banner are both written by Python,
so both read the new version while CEF was serving a `palette.html` it had cached earlier — and
every symptom of that is indistinguishable from "the change didn't work". Nothing on screen told
the two apart.

So the page now declares its own `UI_VERSION` and sends it to Python on every connect. On a
mismatch Python reloads the page from disk once (reassigning `Palette.htmlFileURL` is what forces
CEF to re-fetch) and says what it did; if it comes back mismatched again, the log says that plainly
instead of pretending. The startup banner reports all three:

```
Selection Inspector v2.31.3 · palette UI v2.31.3 · manifest on disk v2.31.3 · /Users/you/…/AddIns/SelectionInspector
```

Any of the three disagreeing appends `<-- MISMATCH` and colors the line red. `tools/build_release.py`
refuses to build if `VERSION`, the manifest and the palette's `UI_VERSION` disagree.


`VERSION` in `SelectionInspector.py` is the single source of truth. It feeds the palette title bar,
the button's tooltip, and a line written to **Utilities → Text Commands** at every startup:

```
Selection Inspector: running v2.37.0 from /Users/you/Library/.../AddIns/SelectionInspector
```

That log line is authoritative — it names the version *and* the folder actually loaded. If the
manifest next to that file disagrees with the code, startup logs a warning naming both, which
catches a half-copied install.

**Fusion's own Scripts and Add-Ins panel is not authoritative, and the add-in cannot refresh it.**
Fusion reads the `.manifest` when it first registers an add-in and caches that metadata against the
manifest's `id` GUID. Neither Stop/Run nor reinstalling the files makes it re-read, and in practice
a plain restart often doesn't either — the cache is keyed to the registration, not the session.

To force it to re-read:

1. In **Scripts and Add-Ins → Add-Ins**, select the add-in and **remove** it from the list
   (the `-`/right-click option — this does not delete your files).
2. Quit and reopen Fusion.
3. Add it back with the **+** button, pointing at
   `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/SelectionInspector`.

Changing the manifest `id` each release would also force a re-read, but Fusion would treat every
version as a brand-new add-in — losing your Run-on-Startup setting and your keyboard shortcut with
it. Not worth it, so the GUID stays fixed.

**Where to read the real version instead**, all of which update immediately:

- the palette's title bar
- the **Log** pane, first line, which also names the folder it loaded from
- the button's tooltip
- **Utilities → Text Commands**, which logs both the code version and the manifest version on disk

## Layout

There's no in-page header — the palette's own title bar carries the name and version
(`Selection Inspector (v2.37.0)`), so all the vertical space goes to the table. The active document
name sits at the left of the footer.

The version comes from one place: `VERSION` in `SelectionInspector.py`, which builds the palette
title at startup. Bumping it there (and in the manifest) is the whole job.

## Notes

- The palette is a **palette**, so it's inherently non-modal — dock it, float it, keep modeling with it open. It opens docked right at 940×560.
- `palette.html` can be opened directly in a browser; it falls back to a small demo dataset so you can check the UI without launching Fusion.
- Nothing loads from the internet: the palette uses JetBrains Mono and DM Sans if they are installed, and the system monospace and sans fonts otherwise. `color-scheme: dark` keeps scrollbars and form controls dark on Windows.
