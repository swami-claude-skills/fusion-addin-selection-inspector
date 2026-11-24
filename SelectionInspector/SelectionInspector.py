# Selection Inspector - Autodesk Fusion add-in
#
# A non-modal HTML palette that lists every togglable entity in the active
# design in an interactive table: sortable, resizable columns (with
# fit-to-widest), a parent/child path, instance quantity, occurrence status,
# and a show/hide checkbox per row. Rows matching the current Fusion selection
# are highlighted live.
#
# Sits in the INSPECT panel of every context tab. Ships with an icon so a shortcut
# can be assigned (Fusion only offers shortcuts for commands that have an icon).
#
# Row clicks are inert; the Selected checkbox is the one control that writes
# back to the Fusion selection.

import adsk.core
import adsk.fusion
import datetime
import json
import os
import time
import traceback

# ---------------------------------------------------------------------------
# Module-level state. Handlers MUST live here: Fusion holds event handlers by
# weak reference, so anything not kept alive gets garbage-collected and the
# event silently stops firing.
# ---------------------------------------------------------------------------
app = adsk.core.Application.get()
ui = app.userInterface

handlers = []                 # keeps every event handler alive
_app_events = []              # (event, handler) pairs to unsubscribe in stop()

ADDIN_TITLE = 'Selection Inspector'
VERSION = '2.36.6'      # single source of truth - pushed to the palette header

CMD_ID = 'swamiSelectionInspectorCmd'
CMD_NAME = 'Selection Inspector'
CMD_DESC = ('Selection Inspector v' + VERSION + '\n\n'
            'Inspect every entity in the active design in a sortable, resizable table '
            'with show/hide checkboxes.\n\n'
            'Tip: right-click this button and choose "Change Keyboard Shortcut" to bind a hotkey.')

PALETTE_ID = 'swamiSelectionInspectorPalette'
PALETTE_NAME = 'Selection Inspector (v' + VERSION + ')'   # shown in the palette title bar
PALETTE_FILE = 'palette.html'

LEGEND_PALETTE_ID = 'swamiSelectionInspectorLegend'
LEGEND_PALETTE_NAME = 'Qty color legend'
LEGEND_FILE = 'legend.html'
# Allowance for the palette's own title bar and borders, on top of the content
# size the page reports. Slightly generous: better a few spare pixels than a
# scrollbar over a window meant to show everything at once.
LEGEND_CHROME_W = 10
LEGEND_CHROME_H = 40

# The button goes into EVERY INSPECT panel Fusion exposes - SOLID, SURFACE,
# MESH, SHEET METAL and any other context tab - discovered at runtime rather
# than hard-coded, since the ids differ per tab and per version.
INSPECT_MATCH = 'inspect'
FALLBACK_PANEL_ID = 'SolidScriptsAddinsPanel'  # only if no INSPECT panel exists
ICON_FOLDER = './resources/command'

# The topmost element of every path. The root component's real name is noise
# here - it's the same on every row - so paths read "root / Frame:1 / Rail".
# Only the path column uses this; the Name column still shows real names.
ROOT_LABEL = 'root'


# Row bookkeeping, rebuilt on every scan.
_entity_map = {}        # row id -> Fusion entity
_token_index = {}       # identity key -> row id
_ancestors = {}         # row id -> [occurrence, ...] outermost-first
# Sub-entity rows whose identity keys have not been computed yet, grouped by
# the row id of the body or sketch they came out of. See add_row.
_lazy_subs = {}         # owner row id -> [row id, ...]
_lazy_done = set()      # owner row ids already indexed
# Everything an owner needs to build its children later: the body or sketch
# itself, and the row context those children inherit.
_sub_context = {}       # owner row id -> {entity, kind, qty, path, status, ...}
_sub_loaded = set()     # (owner row id, type) already built
_next_id = [0]          # row ids continue past the scan, for rows loaded later
# The version the loaded palette.html reports for itself, and whether we have
# already forced it to reload this session. See _check_ui_version.
_ui_version = [None]
_ui_reloaded = [False]

_placed_panels = []     # ids of every panel the button was added to
_legend_size = [340, 300]    # last content size the legend page reported
_last_marker = [None]        # last seen timeline marker, to spot it moving
_pushing_selection = False   # guards our own selection writes from echoing back
_include_sub = False    # list sketch points/curves and body faces/edges/vertices
_scan_stats = {}        # counters from the last scan, for the palette footer


class UserError(Exception):
    """Expected, user-facing problem. Reported plainly, without a traceback."""
    pass


# ---------------------------------------------------------------------------
# Small safety helpers - the API raises on plenty of properties depending on
# document type and version, so every property read is defensive.
# ---------------------------------------------------------------------------
def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _keys(obj):
    """Every key an entity might be recognized by.

    This is the crux of matching the Fusion selection to a row. A pick in the
    canvas hands back a *proxy* (the entity as it appears inside an occurrence),
    whose entityToken differs from the native object the scan collected off the
    component - so a single-token index never matches. Unsaved documents make it
    worse: entityToken can be unavailable entirely. So index every row under all
    the keys it might be found by, and match on any of them.
    """
    keys = []

    tok = _safe(lambda: obj.entityToken)
    if tok:
        keys.append('T:' + str(tok))

    native = _safe(lambda: obj.nativeObject)
    if native is not None:
        ntok = _safe(lambda: native.entityToken)
        if ntok:
            keys.append('T:' + str(ntok))

    # Structural fallback for when no token is available at all.
    name = _safe(lambda: obj.name, '')
    if name:
        otype = _safe(lambda: obj.objectType, 'unknown')
        owner = (_safe(lambda: obj.parentSketch.name) or
                 _safe(lambda: obj.body.name) or
                 _safe(lambda: obj.parentComponent.name) or '')
        keys.append('S:{}|{}|{}'.format(otype, owner, name))

    return keys


def _identity(obj):
    """First key, or a per-object fallback. Only used where uniqueness matters."""
    keys = _keys(obj)
    return keys[0] if keys else 'O:{}'.format(id(obj))


def _component_key(component):
    """Grouping key for a component *definition*.

    Occurrences are grouped by this to work out instance counts, so a collision
    here merges unrelated components and reports, say, four separate top-level
    components as "instance 1..4 of 4".

    It combines the token, the id and the name rather than trusting any one of
    them: entityToken is not reliably distinct across linked/external
    components, and names are not guaranteed unique either. Together they only
    collide when every part agrees - which is exactly when merging is right.
    """
    token = _safe(lambda: component.entityToken, '') or ''
    ident = _safe(lambda: component.id, '') or ''
    name = _safe(lambda: component.name, '') or ''
    if not (token or ident or name):
        return 'C:obj{}'.format(id(component))     # last resort, never merges
    return 'C:{}|{}|{}'.format(token, ident, name)


def _get_visible(entity):
    """Light-bulb state. Falls back to isVisible for types that lack the bulb."""
    for attr in ('isLightBulbOn', 'isVisible'):
        try:
            val = getattr(entity, attr)
            if isinstance(val, bool):
                return val
        except Exception:
            pass
    return True


def _can_toggle(entity):
    for attr in ('isLightBulbOn', 'isVisible'):
        try:
            getattr(entity, attr)
            return True
        except Exception:
            pass
    return False


def _set_visible(entity, value):
    """Set light-bulb/visibility. Raises with a readable message if neither sticks."""
    last = None
    for attr in ('isLightBulbOn', 'isVisible'):
        try:
            setattr(entity, attr, bool(value))
            return
        except Exception as err:
            last = err
    raise RuntimeError(str(last) if last else 'visibility is read-only for this entity')


def _active_design():
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise UserError('Open a Design or Part document first - Selection Inspector '
                        'reads the design tree.')
    return design


# ---------------------------------------------------------------------------
# Scanning the model
# ---------------------------------------------------------------------------
def _walk_occurrences(occurrences, parent_path, parent_chain, out):
    """Depth-first walk of the whole occurrence tree. Empty in flat Part docs.

    Carries the chain of ancestor occurrence objects alongside the name path so
    "show this" can switch its parents' light bulbs on as well - an entity whose
    parent occurrence is hidden stays invisible no matter what its own bulb says.
    """
    for occ in occurrences:
        name = _safe(lambda o=occ: o.name, '<unnamed>')
        path = parent_path + [name]
        chain = parent_chain + [occ]
        out.append((occ, path, chain))
        children = _safe(lambda o=occ: o.childOccurrences)
        if children:
            _walk_occurrences(children, path, chain, out)


def _occurrence_flags(occ):
    """Placement state, sent as data for the Qty color coding."""
    linked = bool(_safe(lambda: occ.isReferencedComponent, False))
    return {
        'linked': linked,
        'local': not linked,       # defined in this document rather than referenced
        'suppressed': bool(_safe(lambda: occ.isSuppressed, False)),
        'grounded': bool(_safe(lambda: occ.isGrounded, False)),
    }


def _occurrence_status(occ, index, total):
    bits = []
    if _safe(lambda: occ.isReferencedComponent, False):
        bits.append('Linked')
    else:
        bits.append('Local')
    bits.append('instance {} of {}'.format(index, total))
    if _safe(lambda: occ.isGrounded, False):
        bits.append('grounded')
    if _safe(lambda: occ.isSuppressed, False):
        bits.append('suppressed')
    if _safe(lambda: occ.isIsolated, False):
        bits.append('isolated')
    if not _safe(lambda: occ.isVisible, True):
        bits.append('hidden by parent')
    return ' · '.join(bits)


# (label, accessor) for everything that hangs off a Component and has a bulb.
ENTITY_SOURCES = (
    ('Body',   lambda c: list(c.bRepBodies)),
    ('Mesh',   lambda c: list(c.meshBodies)),
    ('Sketch', lambda c: list(c.sketches)),
    ('Plane',  lambda c: list(c.constructionPlanes)),
    ('Axis',   lambda c: list(c.constructionAxes)),
    ('Point',  lambda c: list(c.constructionPoints)),
    ('Joint',  lambda c: list(c.joints)),
)


# Back to 12,000 after 50,000 was measured on a real model: 101 seconds, against
# 6 seconds for the same design at 12,000.
#
# Raising it looked safe because the two costs just fixed - entity tokens and
# DOM rows - no longer scale with it, and the JSON that does was measured at
# 12 MB and 200 ms. What that reasoning missed is the cost nothing had removed:
# *enumerating* the geometry. `body.faces`, `.edges` and `.vertices` are Fusion
# API collections, and walking them is milliseconds per entity regardless of
# what this add-in does with the result. The old cap was never limiting the
# payload - it was stopping the walk a quarter of the way through, which is why
# a 3.6x larger cap cost 17x the time.
#
# So this number is a time budget, not a memory one. The rate is logged every
# scan, so the trade is visible rather than inferred.
SUB_ENTITY_CAP = 12000


def _short_type(obj):
    return (_safe(lambda: obj.objectType, '') or '').split('::')[-1]


def _camel_to_words(text):
    out = []
    for i, ch in enumerate(text):
        if ch.isupper() and i > 0:
            out.append(' ')
        out.append(ch)
    return ''.join(out).strip()


def _sketch_children(sketch):
    """Points and curves inside a sketch, typed by their real API class."""
    items = []
    for i, pt in enumerate(_safe(lambda: list(sketch.sketchPoints), []) or [], 1):
        items.append(('Sketch Point', 'Point {}'.format(i), pt))
    for i, curve in enumerate(_safe(lambda: list(sketch.sketchCurves), []) or [], 1):
        label = _camel_to_words(_short_type(curve)) or 'Sketch Curve'
        short = label[7:] if label.startswith('Sketch ') else label
        items.append((label, '{} {}'.format(short, i), curve))
    return items


# Enumerating a collection is the expensive part; asking it how many items it
# holds is not. These two tables let the scan report "Face x 248" without ever
# touching a face, and let a later request enumerate exactly one collection.
BODY_PARTS = (
    ('Face',   lambda b: b.faces),
    ('Edge',   lambda b: b.edges),
    ('Vertex', lambda b: b.vertices),
)
SKETCH_PARTS = (
    ('Sketch Point', lambda s: s.sketchPoints),
    ('Sketch Curve', lambda s: s.sketchCurves),
)


def _sub_groups(owner, kind):
    """[{type, count}] for one body or sketch, from count properties only."""
    parts = BODY_PARTS if kind == 'Body' else SKETCH_PARTS
    out = []
    for label, get in parts:
        n = _safe(lambda g=get: g(owner).count, 0) or 0
        if n:
            out.append({'type': label, 'count': n})
    return out


def _sub_items(owner, kind, type_label):
    """(name, entity) for one owner's children of one type. The only place that
    walks a BRep collection, and it walks exactly one."""
    parts = BODY_PARTS if kind == 'Body' else SKETCH_PARTS
    for label, get in parts:
        if label != type_label:
            continue
        coll = _safe(lambda g=get: list(g(owner)), []) or []
        if type_label == 'Sketch Curve':
            # curves are typed individually - a line and an arc are different
            # rows - so the label comes from the object, not the collection
            out = []
            for i, c in enumerate(coll, 1):
                lab = _camel_to_words(_short_type(c)) or 'Sketch Curve'
                short = lab[7:] if lab.startswith('Sketch ') else lab
                out.append(('{} {}'.format(short, i), c, lab))
            return out
        return [('{} {}'.format(type_label.replace('Sketch ', ''), i), c, type_label)
                for i, c in enumerate(coll, 1)]
    return []


def _body_children(body):
    """Faces, edges and vertices of a solid/surface body."""
    items = []
    for kind, attr in (('Face', 'faces'), ('Edge', 'edges'), ('Vertex', 'vertices')):
        coll = _safe(lambda a=attr: list(getattr(body, a)), []) or []
        for i, item in enumerate(coll, 1):
            items.append((kind, '{} {}'.format(kind, i), item))
    return items


def _scan():
    """Build the full row list for the active design and refresh the id maps."""
    design = _active_design()
    root = design.rootComponent
    root_name = ROOT_LABEL

    _entity_map.clear()
    _token_index.clear()
    _ancestors.clear()
    _lazy_subs.clear()
    _lazy_done.clear()
    _sub_context.clear()
    _sub_loaded.clear()
    rows = []
    # module-level, because sub-entity rows are created after this function
    # returns and must not reuse an id
    _next_id[0] = 0
    next_id = _next_id
    sub_count = [0]
    truncated = [False]

    def add_row(entity, name, kind, qty, path_parts, status, ancestors,
                togglable=None, visible=None, parent_id=None, flags=None,
                defer_keys=False):
        rid = next_id[0]
        next_id[0] += 1
        _entity_map[rid] = entity
        if defer_keys:
            # _keys() reads entityToken, twice - and entityToken is the most
            # expensive property in the Fusion API, because it serializes a
            # persistent reference rather than reading a field. At a few
            # milliseconds each that is fine for the few hundred bodies and
            # sketches in a design and ruinous for twelve thousand faces and
            # edges: it was the whole of a 78-second Sub-entities scan.
            #
            # Sub-entity keys exist for one purpose, matching a canvas pick to
            # a row, so they are computed when a pick actually needs them -
            # and then only for the children of the one body or sketch that
            # was picked in. Scanning pays nothing.
            _lazy_subs.setdefault(parent_id, []).append(rid)
        else:
            for key in _keys(entity):
                _token_index.setdefault(key, rid)
        _ancestors[rid] = ancestors or []
        rows.append({
            'id': rid,
            'name': name,
            'type': kind,
            'qty': qty,
            'path': ' / '.join(path_parts),
            'status': status,
            'visible': _get_visible(entity) if visible is None else bool(visible),
            'canToggle': _can_toggle(entity) if togglable is None else bool(togglable),
            # Row id of the body/sketch this came out of, so the palette can
            # group sub-entities under their owner. None for top-level rows.
            'parentId': parent_id,
            # Structured state for the Qty color coding. Sent as data rather
            # than left for the palette to infer by parsing the status string.
            'flags': flags or {},
        })
        return rid

    # --- pass 1: the occurrence tree -------------------------------------
    occ_list = []
    _walk_occurrences(_safe(lambda: root.occurrences, []) or [], [root_name], [], occ_list)

    counts = {}
    rep_path = {}
    rep_chain = {}
    for occ, path, chain in occ_list:
        comp = _safe(lambda o=occ: o.component)
        if not comp:
            continue
        key = _component_key(comp)
        counts[key] = counts.get(key, 0) + 1
        if key not in rep_path:
            rep_path[key] = path
            rep_chain[key] = chain

    seen_index = {}
    for occ, path, chain in occ_list:
        comp = _safe(lambda o=occ: o.component)
        key = _component_key(comp) if comp else None
        total = counts.get(key, 1)
        seen_index[key] = seen_index.get(key, 0) + 1
        # Typed as Component: that is what the browser shows and what people
        # call it. The row is strictly one *occurrence* of that component, and
        # the Instance / Status column carries which one.
        add_row(occ,
                _safe(lambda o=occ: o.name, '<unnamed>'),
                'Component',
                total,
                path,
                _occurrence_status(occ, seen_index[key], total),
                chain[:-1],          # its own parents, not itself
                flags=_occurrence_flags(occ))

    # --- pass 2: everything owned by each component definition ------------
    # Listed once per component (not once per instance) so a 40-copy assembly
    # doesn't produce 40 identical body rows. Quantity is the instance count.
    components = _safe(lambda: list(design.allComponents), None)
    if components is None:
        components = [root]

    root_key = _component_key(root)
    for comp in components:
        key = _component_key(comp)
        is_root = (key == root_key)
        qty = 1 if is_root else counts.get(key, 0)
        base_path = [root_name] if is_root else rep_path.get(key, [root_name,
                     _safe(lambda c=comp: c.name, '<unnamed>')])
        # The occurrence chain this component definition sits inside. Root-owned
        # entities have none; everything else inherits its host occurrences.
        base_chain = [] if is_root else rep_chain.get(key, [])
        if is_root:
            comp_status = 'Root component'
        elif qty == 0:
            comp_status = 'Unplaced (no occurrence)'
        else:
            comp_status = '{} occurrence{}'.format(qty, '' if qty == 1 else 's')

        for kind, fetch in ENTITY_SOURCES:
            items = _safe(lambda f=fetch, c=comp: f(c), []) or []
            for item in items:
                item_name = _safe(lambda i=item: i.name, '<unnamed>')
                owner_id = add_row(item, item_name, kind, qty,
                                   base_path + [item_name], comp_status, base_chain,
                                   flags={'root': is_root, 'unplaced': (not is_root and qty == 0)})
                item_visible = _get_visible(item)

                # --- pass 3: sub-entities ----------------------------------
                # Counted, not enumerated. Walking a body's faces costs
                # milliseconds per face, and every group starts collapsed, so
                # the old scan spent a hundred seconds building rows nobody had
                # asked to see. The counts come from `.count` properties, which
                # are free; the rows arrive when a group is expanded.
                if not _include_sub or kind not in ('Sketch', 'Body'):
                    continue
                groups = _sub_groups(item, kind)
                if groups:
                    rows[-1]['subGroups'] = groups
                    for g in groups:
                        sub_count[0] += g['count']
                    # everything a later expand will need, kept so the rows
                    # can be built without re-deriving where they came from
                    _sub_context[owner_id] = {
                        'entity': item, 'kind': kind, 'qty': qty,
                        'path': base_path + [item_name],
                        'status': comp_status, 'chain': base_chain,
                        'visible': item_visible,
                        'groups': [g['type'] for g in groups],
                    }

    _scan_stats['sub'] = sub_count[0]
    _scan_stats['truncated'] = truncated[0]
    return rows


def _load_sub_rows(owner_id, type_label):
    """Build the rows for one owner's children of one type, on demand.

    This is the whole point of the redesign: the only walk of a BRep collection
    happens here, for one body and one kind, because someone expanded that
    group. A model with 44,000 sub-entities costs nothing until then, and then
    costs one body's worth.
    """
    ctx = _sub_context.get(owner_id)
    if not ctx:
        _log('No sub-entity context for row {} - the table was rescanned since '
             'that row was built. Refresh and try again.'.format(owner_id), 'warn')
        return []
    if (owner_id, type_label) in _sub_loaded:
        _log('"{}" under "{}" was already built; its rows are in the table.'
             .format(type_label, ctx['path'][-1]), 'info')
        return []
    _sub_loaded.add((owner_id, type_label))

    started = time.time()
    items = _sub_items(ctx['entity'], ctx['kind'], type_label)
    out = []
    for name, entity, label in items:
        rid = _next_id[0]
        _next_id[0] += 1
        _entity_map[rid] = entity
        # keys stay deferred here too - matching a pick still pays for them
        # one owner at a time, and expanding a group is not a reason to
        _lazy_subs.setdefault(owner_id, []).append(rid)
        _lazy_done.discard(owner_id)
        _ancestors[rid] = ctx['chain'] or []
        out.append({
            'id': rid, 'name': name, 'type': label,
            # the group this row belongs to, which is not its type: sketch
            # curves are declared as one "Sketch Curve" group but each row is
            # typed individually, as a Line or an Arc
            'group': type_label,
            'qty': ctx['qty'],
            'path': ' / '.join(ctx['path'] + [name]),
            'status': ctx['status'],
            'visible': bool(ctx['visible']),
            # faces, edges and sketch geometry have no light bulb of their own
            'canToggle': False,
            'parentId': owner_id,
            'flags': {},
        })
    if not out:
        _log('Fusion listed no {} for "{}" - it reported {} of them when scanning.'
             .format(type_label, ctx['path'][-1],
                     next((g for g in ctx.get('groups', [])), '?')), 'warn')
    ms = (time.time() - started) * 1000.0
    if ms > 400:
        _log('Loaded {:,} {} from "{}" in {:.1f} s.'
             .format(len(out), type_label, ctx['path'][-1], ms / 1000.0), 'info')
    return out


# ---------------------------------------------------------------------------
# Flashing an entity in the viewport
# ---------------------------------------------------------------------------
# Fusion has no "highlight this without selecting it" API. Selecting would be
# the easy route and is exactly what was asked against - the table must not
# disturb what you have picked - so this draws its own overlay with custom
# graphics and blinks it. Nothing about the document or the selection changes;
# custom graphics are view-only and vanish with deleteMe().
FLASH_RGBA = (255, 225, 77, 255)      # the same yellow the table uses for Single

# Never write `if obj:` about a Fusion object in this block, and prefer
# `is None` everywhere else in it too. A CustomGraphicsGroup is a *collection*,
# so its Python wrapper has __len__, so a group that was just created and is
# therefore empty is falsy. `if not grp:` threw away every group Fusion handed
# back, and the add-in reported that Fusion "returned nothing" - which is what
# it looked like from inside a boolean test, and was wrong. Nothing flashed,
# for any entity kind, from v2.35.0 until this was found.
_flash = {'group': None, 'rid': None, 'how': '', 'why': '', 'owner': ''}


def _flash_clear():
    """Remove the overlay. Safe to call when there is nothing to remove."""
    grp = _flash.get('group')
    _flash['group'] = None
    _flash['rid'] = None
    _flash['how'] = ''
    _flash['why'] = ''
    _flash['owner'] = ''
    if grp is not None:
        _safe(lambda: grp.deleteMe())
        _safe(lambda: app.activeViewport.refresh())


def _bbox_lines(box):
    """The twelve edges of a bounding box, as Line3D.

    The fallback for anything there is no better representation for - a
    component, a sketch, a point. A wireframe box is unmistakable in the
    viewport and costs nothing to build.
    """
    if box is None:
        return []
    mn, mx = box.minPoint, box.maxPoint
    xs, ys, zs = (mn.x, mx.x), (mn.y, mx.y), (mn.z, mx.z)
    pts = [adsk.core.Point3D.create(xs[i], ys[j], zs[k])
           for i in (0, 1) for j in (0, 1) for k in (0, 1)]
    # index pairs of the box edges, over the 000..111 ordering above
    pairs = ((0, 1), (0, 2), (0, 4), (1, 3), (1, 5), (2, 3),
             (2, 6), (3, 7), (4, 5), (4, 6), (5, 7), (6, 7))
    out = []
    for a, b in pairs:
        line = _safe(lambda p=pts[a], q=pts[b]: adsk.core.Line3D.create(p, q))
        if line is not None:
            out.append(line)
    return out


def _view_scale():
    """A length that reads as "small but visible" at the current zoom.

    A marker drawn in model units is either invisible on a large part or
    absurd on a small one, so it is sized from the camera instead: the marker
    stays roughly the same size on screen whatever the model measures.
    """
    cam = _safe(lambda: app.activeViewport.camera)
    if cam is None:
        return 0.5
    span = _safe(lambda: cam.eye.distanceTo(cam.target), 0.0) or 0.0
    extents = _safe(lambda: cam.viewExtents, 0.0) or 0.0
    # viewExtents is an area for orthographic cameras; its square root is the
    # length we actually want. Either measure alone can be zero, so take the
    # larger and floor it so a degenerate camera still draws something.
    ref = max(span, extents ** 0.5 if extents > 0 else 0.0)
    return max(ref * 0.02, 0.05)


def _point_of(entity):
    """The Point3D an entity *is*, if it is one, else None.

    Sketch points, construction points and BRep vertices are all points, and
    they reach that fact by different property names.
    """
    for get in (lambda: entity.worldGeometry,
                lambda: entity.geometry,
                lambda: entity.point):
        pt = _safe(lambda g=get: adsk.core.Point3D.cast(g()))
        if pt is not None:
            return pt
    return None


def _point_marker(grp, pt):
    """Draw a three-axis cross at a point. Returns how, or ''.

    A point has no curve and no bounding box, so both of the other routes had
    nothing to work with - which is why clicking a sketch point flashed
    nothing at all. A cross is unambiguous and is built from the Line3D that
    every Fusion build has.
    """
    if pt is None:
        return ''
    r = _view_scale()
    drawn = 0
    for dx, dy, dz in ((r, 0, 0), (0, r, 0), (0, 0, r)):
        a = _safe(lambda: adsk.core.Point3D.create(pt.x - dx, pt.y - dy, pt.z - dz))
        b = _safe(lambda: adsk.core.Point3D.create(pt.x + dx, pt.y + dy, pt.z + dz))
        line = None if (a is None or b is None) else \
            _safe(lambda: adsk.core.Line3D.create(a, b))
        if line is not None and _safe(lambda l=line: grp.addCurve(l)) is not None:
            drawn += 1
    if not drawn:
        # last resort: a point set, which is smaller on screen but is drawn by
        # a different code path in Fusion and so can survive when curves do not
        if _safe(lambda: grp.addPointSet(
                [pt.x, pt.y, pt.z], [0],
                adsk.fusion.CustomGraphicsPointTypes.PointCloudCustomGraphicsPointType,
                '')) is not None:
            return 'point'
    return 'point marker' if drawn else ''


def _graphics_owners(entity):
    """Components worth trying to hang a custom graphics group on, best first.

    Every example uses rootComponent, and rootComponent is exactly what
    refused. A custom graphics group is owned by a component, so the component
    Fusion is currently willing to touch is the one that is currently being
    edited - which, inside a sketch or with the timeline rolled back, is not
    the root. The entity's own component is tried first because it is
    guaranteed to be part of whatever is on screen.
    """
    design = _safe(lambda: adsk.fusion.Design.cast(app.activeProduct))
    out, seen = [], set()
    for get in (lambda: entity.parentSketch.parentComponent,
                lambda: entity.parentComponent,
                lambda: entity.body.parentComponent,
                lambda: entity.component,
                lambda: design.activeComponent,
                lambda: design.rootComponent):
        comp = _safe(get)
        if comp is None:
            continue
        # deduplicated by name so the failure message reads as a list of
        # places rather than the same place three times
        name = _safe(lambda: comp.name, '') or ''
        if name and name in seen:
            continue
        seen.add(name)
        out.append(comp)
    return out


def _new_graphics_group(entity):
    """Make a custom graphics group. Returns (group, note).

    The note is Fusion's own words on why each candidate refused. The previous
    version wrapped this one call in _safe(), so a refusal and a returned None
    and a missing design all arrived as the same silent nothing - which is the
    exact shape of the bug that made this function necessary.
    """
    notes = []
    for comp in _graphics_owners(entity):
        name = _safe(lambda: comp.name, '?') or '?'
        try:
            grp = comp.customGraphicsGroups.add()
            if grp is not None:
                return grp, name
            notes.append('{}: returned nothing'.format(name))
        except Exception as err:
            msg = str(err).strip().replace('\n', ' ')[:140]
            notes.append('{}: {}'.format(name, msg or '(no message)'))
    if not notes:
        return None, 'there is no component to draw into'
    note = 'tried ' + '; '.join(notes)
    tl = _safe(lambda: _timeline_state(), {}) or {}
    if tl.get('available') and tl.get('position', 0) < tl.get('count', 0):
        note += ('. The timeline is rolled back to {} of {}, which is the '
                 'likeliest cause - roll it to the end and try again'
                 .format(tl.get('position'), tl.get('count')))
    return None, note


def _flash_build(entity):
    """Draw one entity as custom graphics. Returns how it was drawn, or ''.

    Each entity kind has its own best representation and none of them are
    guaranteed across Fusion builds, so every attempt is guarded and the
    bounding box is the floor: worse, but always available and always visible.
    """
    design = _safe(lambda: adsk.fusion.Design.cast(app.activeProduct))
    if design is None:
        _flash['why'] = 'There is no active design to draw into.'
        return ''
    grp, note = _new_graphics_group(entity)
    if grp is None:
        _flash['why'] = ('Fusion would not create a custom graphics group: '
                         + note + '.')
        return ''
    _flash['owner'] = note

    kind = _short_type(entity)
    how = ''

    if kind == 'BRepFace':
        mesh = _safe(lambda: entity.meshManager.displayMeshes.bestMesh)
        if mesh is not None and _safe(lambda: grp.addMesh(mesh.nodeCoordinatesAsDouble,
                                              mesh.nodeIndices,
                                              mesh.normalVectorsAsDouble,
                                              mesh.nodeIndices)):
            how = 'face mesh'

    if not how and kind in ('BRepBody', 'MeshBody'):
        if _safe(lambda: grp.addBRepBody(entity)) is not None:
            how = 'body'

    if not how and kind == 'BRepEdge':
        geo = _safe(lambda: entity.geometry)
        if geo is not None and _safe(lambda: grp.addCurve(geo)) is not None:
            how = 'edge curve'

    if not how and kind.startswith('Sketch'):
        # sketch geometry knows its own world-space form, which is what the
        # viewport needs - the sketch's own plane transform is already applied
        geo = _safe(lambda: entity.worldGeometry)
        if geo is not None and _safe(lambda: grp.addCurve(geo)) is not None:
            how = 'sketch curve'

    # v2.36.0: a point is neither a curve nor a box, so both routes above and
    # the fallback below had nothing to draw and a sketch point flashed
    # nothing whatsoever. This is the branch that was missing.
    if not how:
        how = _point_marker(grp, _point_of(entity))

    if not how:
        box = (_safe(lambda: entity.boundingBox) or
               _safe(lambda: entity.geometry.boundingBox))
        lines = _bbox_lines(box)
        drawn = 0
        for line in lines:
            if _safe(lambda l=line: grp.addCurve(l)) is not None:
                drawn += 1
        if drawn:
            how = 'bounding box'
        elif box is not None:
            # a box with no extent is a point wearing a box's name
            how = _point_marker(grp, _safe(lambda: box.minPoint))

    if not how:
        _flash['why'] = ('Fusion offers no drawable form for a {} '
                         '- no curve, no mesh, no point and no bounding box.'
                         .format(kind or 'row'))
        _safe(lambda: grp.deleteMe())
        return ''

    # bright, and drawn over the model rather than inside it
    color = _safe(lambda: adsk.fusion.CustomGraphicsSolidColorEffect.create(
        adsk.core.Color.create(*FLASH_RGBA)))
    for i in range(_safe(lambda: grp.count, 0) or 0):
        item = _safe(lambda idx=i: grp.item(idx))
        if item is None:
            continue
        if color is not None:
            _safe(lambda it=item: setattr(it, 'color', color))
        _safe(lambda it=item: setattr(it, 'depthPriority', 10))
        # a default-weight curve is one pixel wide, which is not a flash so
        # much as a rumour - and the point marker is nothing but curves
        _safe(lambda it=item: setattr(it, 'weight', 4))
    _flash['group'] = grp
    return how


def _flash_set(rid):
    """Start flashing one row's entity, replacing anything already flashing."""
    _flash_clear()
    entity = _entity_map.get(int(rid))
    if entity is None:
        _flash['why'] = ('That row is no longer attached to an entity '
                         '- press Refresh.')
        return ''
    how = _flash_build(entity)
    if how:
        _flash['rid'] = int(rid)
        _flash['how'] = how
        _safe(lambda: app.activeViewport.refresh())
    return how


def _flash_pulse(on):
    """Blink. The palette owns the timer - an add-in has no reliable one - so
    this just applies whichever half of the blink it was told."""
    grp = _flash.get('group')
    if grp is None:
        return False
    _safe(lambda: setattr(grp, 'isVisible', bool(on)))
    _safe(lambda: app.activeViewport.refresh())
    return True


def _show_ancestors(rid):
    """Switch on every parent occurrence of a row. Returns how many were off.

    Without this, ticking Show on a nested entity does nothing visible: Fusion
    keeps it hidden while any ancestor's light bulb is off.
    """
    turned_on = 0
    for ancestor in _ancestors.get(rid, []):
        try:
            if not _get_visible(ancestor):
                _set_visible(ancestor, True)
                turned_on += 1
        except Exception:
            pass   # a parent we can't toggle shouldn't fail the child's show
    return turned_on


# Text commands the palette is allowed to run. An allowlist rather than a
# free-text pass-through: the HTML side can only ask for these exact commands.
TEXT_COMMANDS = {
    'showUnderConstrained': {
        # Text command names are undocumented and have varied in case between
        # Fusion builds, so each entry is a list tried in order. The one that
        # works is logged, so a spelling only has to be discovered once.
        'command': ['sketch.showunderconstrained',
                    'Sketch.ShowUnderConstrained',
                    'sketch.showUnderConstrained'],
        'label': 'Show under-constrained',
        'needsSketch': True,
    },
}


def _timeline_state():
    """Where the history marker sits, and how long the timeline is.

    Only parametric designs have a timeline; direct-modeling documents and
    non-design products report unavailable rather than raising.
    """
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        return {'available': False, 'position': -1, 'count': 0}

    timeline = _safe(lambda: design.timeline)
    if timeline is None:
        return {'available': False, 'position': -1, 'count': 0}

    return {'available': True,
            'position': _safe(lambda: timeline.markerPosition, -1),
            'count': _safe(lambda: timeline.count, 0)}


def _marker_key():
    state = _timeline_state()
    return (state['available'], state['position'], state['count'])


# How long the last full scan took, and whether the table is currently behind
# the model. AUTO_SCAN_MS is the line between "just rescan, nobody will notice"
# and "say so and let the user decide" - a rescan of a 12k-entity assembly is
# not something to fire off after every command.
AUTO_SCAN_MS = 300
_last_scan_ms = [0.0]
_last_payload_kb = [0]
_last_model = [None]
_stale = [False]


def _model_key():
    """A cheap fingerprint of the model, for answering "did anything change?"
    without paying for a full scan.

    Fusion has no "the design changed" event. The timeline covers most edits,
    but not all of them: renaming a body and toggling a light bulb in the
    browser both leave the marker exactly where it was, so a table watching
    only the timeline goes quietly out of date. Component.revisionId changes
    whenever a component is modified in any way, so hashing every component's
    revision catches those - and costs no geometry traversal.

    If revisionId is unavailable, the fallback is component and occurrence
    counts. That is weaker (a rename doesn't move it), but a weak signal beats
    an exception, and the honest failure mode is the old behavior."""
    # deliberately not _active_design(): a missing design is a normal state
    # here, not an error to raise at the user
    design = _safe(lambda: adsk.fusion.Design.cast(app.activeProduct), None)
    if not design:
        return None
    parts = []
    comps = _safe(lambda: design.allComponents, None)
    if comps:
        for comp in comps:
            rev = _safe(lambda c=comp: c.revisionId, None)
            parts.append(rev if rev else _safe(lambda c=comp: c.name, '?'))
    if not parts:
        return ('fallback',
                _safe(lambda: design.allComponents.count, 0),
                _safe(lambda: design.rootComponent.allOccurrences.count, 0))
    return hash(tuple(parts))


def _sketch_state():
    """Whether Fusion is currently in sketch edit mode, and which sketch.

    activeEditObject is what actually distinguishes 'editing a sketch' from
    'a sketch happens to be selected' - the SKETCH tab being visible isn't
    enough, and the text command only means anything inside the edit session.
    """
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        return {'inSketch': False, 'sketch': ''}
    edit_obj = _safe(lambda: design.activeEditObject)
    if edit_obj is not None and isinstance(edit_obj, adsk.fusion.Sketch):
        return {'inSketch': True, 'sketch': _safe(lambda: edit_obj.name, '') or ''}
    return {'inSketch': False, 'sketch': ''}


def _selectable_forms(rid, entity):
    """The entity, and the instance-specific proxy for it where that applies.

    Rows for bodies, sketches and the like hold the *native* object off the
    component definition, which Fusion often won't select directly - selection
    wants the entity in the context of a particular occurrence. So try the
    proxy first and fall back to the native object.
    """
    forms = [entity]
    if isinstance(entity, adsk.fusion.Occurrence):
        return forms                      # already instance-specific
    ancestors = _ancestors.get(rid) or []
    if ancestors:
        proxy = _safe(lambda: entity.createForAssemblyContext(ancestors[-1]))
        if proxy is not None:
            forms.insert(0, proxy)
    return forms


def _set_selection(ids):
    """Replace the Fusion selection with exactly these rows.

    The palette sends the whole desired set rather than "add this one", so the
    two can never disagree about what is selected - and it only needs clear()
    and add(), which behave consistently across versions.
    """
    global _pushing_selection
    _pushing_selection = True
    try:
        sels = ui.activeSelections
        sels.clear()

        refused = []
        for rid in ids:
            rid = int(rid)
            entity = _entity_map.get(rid)
            if entity is None:
                continue
            added, last_error = False, None
            for form in _selectable_forms(rid, entity):
                try:
                    sels.add(form)
                    added = True
                    break
                except Exception as err:
                    last_error = err
            if not added:
                name = _safe(lambda e=entity: e.name, '?')
                refused.append('{}: {}'.format(name, last_error or 'not selectable'))
                _log('Could not select {} - {}'.format(name, last_error or 'not selectable'), 'err')

        payload = _payload_full()          # rescan so the table matches Fusion
        payload['refused'] = refused[:20]
        return payload
    finally:
        _pushing_selection = False


# "Show in ..." maps to Fusion's own Find commands. Only FindInWindow is
# documented. Each entry lists likely ids, plus the words to search the live
# command list for when none of them resolve - guessing ids is what made
# "Show in Timeline" fail, so the fallback asks Fusion what it actually has.
SHOW_IN_COMMANDS = {
    'browser':  ('Show in Browser',  ['FindInBrowser', 'FindInBrowserCommand', 'BrowserFind'],
                 ['browser']),
    'window':   ('Show in Window',   ['FindInWindow', 'FindInWindowCommand'],
                 ['window']),
    'timeline': ('Show in Timeline', ['FindInTimeline', 'FindInTimelineCommand', 'TimelineFind'],
                 ['timeline']),
}

_command_cache = {}      # destination -> command id that worked


def _search_command_definitions(words):
    """Every command definition whose id or name contains all of `words`.

    Fusion's command ids are not fully documented and change between versions,
    so this asks the running application rather than trusting a hard-coded list.
    """
    found = []
    definitions = ui.commandDefinitions
    for i in range(_safe(lambda: definitions.count, 0) or 0):
        definition = _safe(lambda idx=i: definitions.item(idx))
        if definition is None:
            continue
        cid = _safe(lambda d=definition: d.id, '') or ''
        cname = _safe(lambda d=definition: d.name, '') or ''
        haystack = (cid + ' ' + cname).lower()
        if all(word in haystack for word in words):
            found.append((cid, cname, definition))
    return found


def _resolve_show_in(where):
    """(definition, id, note) for a destination, or (None, None, note)."""
    label, candidates, words = SHOW_IN_COMMANDS[where]

    cached = _command_cache.get(where)
    if cached:
        definition = ui.commandDefinitions.itemById(cached)
        if definition:
            return definition, cached, ''

    for command_id in candidates:
        definition = ui.commandDefinitions.itemById(command_id)
        if definition:
            _command_cache[where] = command_id
            return definition, command_id, ''

    # None of the guesses exist - ask Fusion what it has.
    matches = _search_command_definitions(words)
    if not matches:
        return None, None, 'no command mentioning "{}" exists'.format(words[0])

    # Only accept something that reads as a find/show command. Merely
    # mentioning "timeline" is not enough - "Play Timeline" matches that word
    # too, and running it because the name overlapped would be worse than
    # reporting nothing found.
    preferred = [m for m in matches
                 if any(verb in (m[0] + ' ' + m[1]).lower()
                        for verb in ('find', 'show', 'locate'))]
    if not preferred:
        return None, None, 'nothing that reads as a find command'
    chosen = preferred[0]
    _command_cache[where] = chosen[0]
    _log('{}: matched command "{}" ({}) by searching Fusion\'s command list.'
         .format(label, chosen[0], chosen[1]), 'info')
    return chosen[2], chosen[0], 'found by search'


def _report_candidates(where):
    """Names every related command, so a miss is diagnosable instead of dead."""
    _, _, words = SHOW_IN_COMMANDS[where]
    matches = _search_command_definitions(words)
    if matches:
        _log('Commands mentioning "{}": {}'.format(
            words[0], ', '.join(sorted(m[0] for m in matches)[:12])), 'warn')
    else:
        _log('No command definition mentions "{}" in this version of Fusion.'
             .format(words[0]), 'warn')


def _show_in(row_id, where):
    """Select the row's entity, then run Fusion's matching Find command."""
    spec = SHOW_IN_COMMANDS.get(where)
    if not spec:
        raise UserError('Unknown destination "{}".'.format(where))
    label = spec[0]

    entity = _entity_map.get(int(row_id))
    if entity is None:
        raise UserError('That row is stale - hit Refresh and try again.')

    _set_selection([int(row_id)])        # the Find commands act on the selection

    definition, command_id, note = _resolve_show_in(where)
    if definition is None:
        _report_candidates(where)
        raise UserError('{} is not available in this version of Fusion.\n'
                        'See the log for the related commands that do exist.'
                        .format(label))

    try:
        definition.execute()
    except Exception as err:
        _command_cache.pop(where, None)      # do not keep a command that fails
        _report_candidates(where)
        raise UserError('{} failed:\n{}'.format(label, err))

    _log('{} ({}{}) on "{}".'.format(label, command_id, ' - ' + note if note else '',
         _safe(lambda e=entity: e.name, '?')), 'ok')
    return {'ok': True, 'used': command_id}


def _legend_palette():
    return ui.palettes.itemById(LEGEND_PALETTE_ID)


def _place_legend(palette):
    """Float the legend with its top-right corner on the table palette's
    top-left corner, so it sits alongside without overlapping or docking."""
    _safe(lambda: setattr(palette, 'dockingState',
                          adsk.core.PaletteDockingStates.PaletteDockStateFloating))

    width, height = _legend_size
    _safe(lambda: setattr(palette, 'width', width))
    _safe(lambda: setattr(palette, 'height', height))

    main = _palette()
    if not main:
        return
    left = _safe(lambda: main.left)
    top = _safe(lambda: main.top)
    if left is None or top is None:
        return          # docked table palette: leave the legend where Fusion put it

    _safe(lambda: setattr(palette, 'left', max(0, int(left) - int(width))))
    _safe(lambda: setattr(palette, 'top', int(top)))


def _resize_legend(width, height):
    """Called by the legend page once it has measured its own content."""
    palette = _legend_palette()
    if not palette:
        return {'ok': True}

    _legend_size[0] = max(240, min(int(width or 0) + LEGEND_CHROME_W, 900))
    _legend_size[1] = max(160, min(int(height or 0) + LEGEND_CHROME_H, 1200))
    _place_legend(palette)
    return {'ok': True, 'width': _legend_size[0], 'height': _legend_size[1]}


class TablePaletteClosedHandler(adsk.core.UserInterfaceGeneralEventHandler):
    """The legend is an accessory to the table, so it goes when the table does.

    A closed palette still exists in Fusion - it is only made invisible - so
    this hides the legend rather than deleting it, and reopening the table
    leaves the Legend button ready to bring it back.
    """

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            legend = _legend_palette()
            if legend and _safe(lambda: legend.isVisible, False):
                legend.isVisible = False
                app.log('{}: table palette closed - legend closed with it.'.format(ADDIN_TITLE))
        except Exception:
            app.log('{}: closing the legend failed:\n{}'.format(
                ADDIN_TITLE, traceback.format_exc()))


class LegendClosedHandler(adsk.core.UserInterfaceGeneralEventHandler):
    """Closing the legend from its own title bar has to reach the table, or the
    Legend button stays lit against a window that is no longer there."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            _push('state', {'legendOpen': False})
        except Exception:
            app.log('{}: legend close notification failed:\n{}'.format(
                ADDIN_TITLE, traceback.format_exc()))


class LegendIncomingHandler(adsk.core.HTMLEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            if args.action == 'legendSize':
                data = json.loads(args.data or '{}')
                result = _resize_legend(data.get('width'), data.get('height'))
            else:
                result = {'ok': False, 'error': 'Unknown action'}
            args.returnData = json.dumps(result)
        except Exception:
            app.log('{}: legend sizing failed:\n{}'.format(ADDIN_TITLE, traceback.format_exc()))
            args.returnData = json.dumps({'ok': False})


def _toggle_legend():
    """Show or hide the legend as its own floating palette.

    A palette rather than a strip inside the table: it is genuinely non-modal,
    can be moved wherever it is useful, and costs the table no vertical space.
    """
    palette = _legend_palette()

    if palette is None:
        here = os.path.dirname(os.path.realpath(__file__))
        path = os.path.join(here, LEGEND_FILE)
        if not os.path.isfile(path):
            raise UserError('Legend page missing.\nExpected: {}'.format(path))
        try:
            palette = ui.palettes.add(
                LEGEND_PALETTE_ID, LEGEND_PALETTE_NAME, path,
                True, True, False, 340, 300)     # visible, closable, NOT resizable
        except Exception:
            palette = ui.palettes.add(
                LEGEND_PALETTE_ID, LEGEND_PALETTE_NAME, './' + LEGEND_FILE,
                True, True, False, 340, 300)
        on_legend_html = LegendIncomingHandler()
        palette.incomingFromHTML.add(on_legend_html)
        handlers.append(on_legend_html)

        on_legend_closed = LegendClosedHandler()
        _safe(lambda: palette.closed.add(on_legend_closed))
        handlers.append(on_legend_closed)

        _place_legend(palette)      # refined once the page reports its size
        _log('Legend opened.', 'info')
        return {'ok': True, 'visible': True}

    visible = not _safe(lambda: palette.isVisible, False)
    palette.isVisible = visible
    if visible:
        _place_legend(palette)      # re-anchor on every open
    _log('Legend ' + ('opened.' if visible else 'closed.'), 'info')
    return {'ok': True, 'visible': visible}


def _legend_open():
    palette = _legend_palette()
    return bool(palette) and bool(_safe(lambda: palette.isVisible, False))


def _save_log(html_body, text_body):
    """Write the log out as a standalone HTML file.

    The clipboard route is at the mercy of whatever converter the destination
    uses - TextEdit's dark-background mode, for one, inverts black and white on
    paste, so a black backdrop arrives white. A file renders exactly as written
    in any browser, so this is the reliable way to keep the colors.
    """
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    folder = os.path.expanduser('~/Desktop')
    if not os.path.isdir(folder):
        folder = os.path.expanduser('~')

    path = os.path.join(folder, 'SelectionInspector-log-{}.html'.format(stamp))
    document = (
        '<!DOCTYPE html>\n<html><head><meta charset="utf-8">'
        '<title>Selection Inspector log {stamp}</title></head>'
        '<body style="margin:0;background-color:#000000;">{body}</body></html>\n'
    ).format(stamp=stamp, body=html_body)

    try:
        with open(path, 'w') as handle:
            handle.write(document)
    except Exception as err:
        raise UserError('Could not write the log file:\n{}'.format(err))

    # A plain-text sibling, for when the colors are beside the point.
    text_path = path[:-5] + '.txt'
    try:
        with open(text_path, 'w') as handle:
            handle.write(text_body or '')
    except Exception:
        text_path = None

    _log('Log saved to {}'.format(path), 'ok')
    return {'ok': True, 'path': path, 'textPath': text_path}


def _apply_visibility_mode(mode):
    """Drive the light bulbs from the Fusion selection.

    all          - everything visible
    selected     - only the selection visible
    notSelected  - only what is NOT selected visible

    This writes real visibility, so it lands in Fusion's browser tree. The
    response is a full rescan, which is what keeps the table's Show column and
    the browser showing the same thing rather than drifting apart.

    Sub-entities are skipped: faces, edges and sketch geometry have no light
    bulb of their own, they follow their owner.
    """
    if mode not in ('all', 'selected', 'notSelected'):
        raise UserError('Unknown visibility mode "{}".'.format(mode))

    rows = _scan()
    chosen = set(_selected_row_ids())

    if mode != 'all' and not chosen:
        raise UserError('Nothing is selected in Fusion, so there is nothing to '
                        'isolate. Pick something first, or choose All.')

    targets = [r for r in rows if r['canToggle']]
    wanted = {}
    for row in targets:
        if mode == 'all':
            wanted[row['id']] = True
        elif mode == 'selected':
            wanted[row['id']] = row['id'] in chosen
        else:
            wanted[row['id']] = row['id'] not in chosen

    changed, failed = 0, []

    # Hide first, then show. Doing it the other way round would let a hide pass
    # switch off an ancestor that a later show pass needs.
    for row in targets:
        if wanted[row['id']]:
            continue
        entity = _entity_map.get(row['id'])
        try:
            if _get_visible(entity):
                _set_visible(entity, False)
                changed += 1
        except Exception as err:
            failed.append('{}: {}'.format(row['name'], err))

    for row in targets:
        if not wanted[row['id']]:
            continue
        entity = _entity_map.get(row['id'])
        try:
            _show_ancestors(row['id'])     # a child cannot show under a hidden parent
            if not _get_visible(entity):
                _set_visible(entity, True)
                changed += 1
        except Exception as err:
            failed.append('{}: {}'.format(row['name'], err))

    _safe(lambda: app.activeViewport.refresh())

    _log('Visibility mode "{}": {} item(s) switched{}.'.format(
        mode, changed, ', {} failed'.format(len(failed)) if failed else ''),
        'err' if failed else 'ok')

    payload = _payload_full()              # rescan: table now mirrors the browser
    payload['mode'] = mode
    payload['changed'] = changed
    payload['failed'] = failed[:20]
    return payload


def _fusion_selection_count():
    """Raw number of entities selected in Fusion - includes faces, edges and
    anything else that has no row of its own."""
    sels = _safe(lambda: ui.activeSelections)
    return _safe(lambda: sels.count, 0) or 0 if sels else 0


EQUALITY_SCAN_LIMIT = 4000   # linear fallback is fine on small models only


def _index_children_of(owner_rid, want=None):
    """Compute the deferred identity keys for one owner's sub-entities.

    Returns whether anything new was indexed, so the caller knows whether a
    second lookup is worth attempting. Idempotent: an owner is only ever
    indexed once per scan.
    """
    if owner_rid is None or owner_rid in _lazy_done:
        return False
    _lazy_done.add(owner_rid)
    kids = _lazy_subs.pop(owner_rid, None)
    if not kids:
        return False
    left = []
    hit = False
    for rid in kids:
        if hit:
            # the row was found, so the rest can stay deferred - a body with
            # thousands of faces should not be indexed in full to answer a
            # pick on its third face
            left.append(rid)
            continue
        entity = _entity_map.get(rid)
        if entity is None:
            continue
        for key in _keys(entity):
            _token_index.setdefault(key, rid)
            if want and key in want:
                hit = True
    if left:
        _lazy_subs[owner_rid] = left
        _lazy_done.discard(owner_rid)
    return True


def _owner_row_id(entity):
    """The row of the body, sketch or component a sub-entity came out of.

    Owners are top-level rows, so they were indexed during the scan - which is
    what makes this the cheap way in to the deferred children.
    """
    for get in (lambda e: e.body,
                lambda e: e.parentSketch,
                lambda e: e.parentComponent):
        owner = _safe(lambda g=get: g(entity))
        if owner is None:
            continue
        for key in _keys(owner):
            rid = _token_index.get(key)
            if rid is not None:
                return rid
    return None


def _row_id_for(entity):
    """Row id for an entity: any matching key, then object equality."""
    keys = _keys(entity)
    for key in keys:
        rid = _token_index.get(key)
        if rid is not None:
            return rid
    # Nothing matched, so this may be a sub-entity whose keys were deferred.
    # Index that owner's children and look again - bounded by one body or
    # sketch, not by the whole model.
    if _index_children_of(_owner_row_id(entity), set(keys)):
        for key in keys:
            rid = _token_index.get(key)
            if rid is not None:
                return rid
    if len(_entity_map) <= EQUALITY_SCAN_LIMIT:
        for other_id, other in _entity_map.items():
            if _safe(lambda a=other, b=entity: a == b, False):
                return other_id
    return None


def _selection_candidates(entity):
    """The entity, then progressively broader stand-ins for it.

    Tried in order, first match wins. So a picked face matches its own row when
    sub-entities are listed, and falls back to its body's row when they aren't.
    """
    out = [entity]

    def add(e):
        if e is not None:
            out.append(e)

    add(_safe(lambda: entity.nativeObject))

    if isinstance(entity, (adsk.fusion.BRepFace, adsk.fusion.BRepEdge,
                           adsk.fusion.BRepVertex)):
        body = _safe(lambda: entity.body)
        add(body)
        if body is not None:
            add(_safe(lambda b=body: b.nativeObject))

    sketch = _safe(lambda: entity.parentSketch)
    if sketch is not None:
        add(sketch)
        add(_safe(lambda s=sketch: s.nativeObject))

    return out


SUB_GROUP_FOR = {
    'BRepFace': 'Face', 'BRepEdge': 'Edge', 'BRepVertex': 'Vertex',
    'SketchPoint': 'Sketch Point',
}


def _sub_group_hint(entity):
    """Which (owner row, group) a picked sub-entity would live in.

    Rows for a group only exist once it has been expanded, so a pick can be for
    something the table has counted but not built. Rather than silently falling
    back to the owner's row, the palette is told where to look - and can load
    that one group if Reveal is on.
    """
    kind = _short_type(entity)
    label = SUB_GROUP_FOR.get(kind)
    if label is None:
        # everything under sketchCurves is declared as one group
        label = 'Sketch Curve' if kind.startswith('Sketch') else None
    if label is None:
        return None
    owner_rid = _owner_row_id(entity)
    if owner_rid is None or owner_rid not in _sub_context:
        return None
    if label not in _sub_context[owner_rid].get('groups', []):
        return None
    return {'ownerId': owner_rid, 'type': label}


def _selection_hints():
    """Group hints for picked entities that have no row yet."""
    hints = []
    index = {}
    sels = _safe(lambda: ui.activeSelections)
    if sels is None:
        return hints
    for i in range(_safe(lambda: sels.count, 0) or 0):
        entity = _safe(lambda idx=i: sels.item(idx).entity)
        if entity is None or _row_id_for(entity) is not None:
            continue
        hint = _sub_group_hint(entity)
        if not hint:
            continue
        # v2.36.5: these used to be deduplicated and nothing else, so thirty
        # picked points in one group reported as "+1 in unopened groups". The
        # number that matters is how many entities are hidden, not how many
        # groups they are spread across.
        key = (hint.get('ownerId'), hint.get('type'))
        if key in index:
            index[key]['count'] += 1
        else:
            hint['count'] = 1
            index[key] = hint
            hints.append(hint)
    return hints


def _selected_row_ids():
    """Row ids for whatever Fusion currently has selected, in pick order.

    The Selected column is a plain reflection of this: selected in Fusion, or
    not. Nothing in the table can change it.
    """
    ids = []
    sels = _safe(lambda: ui.activeSelections)
    if not sels:
        return ids

    for i in range(_safe(lambda: sels.count, 0) or 0):
        entity = _safe(lambda idx=i: sels.item(idx).entity)
        if entity is None:
            continue

        candidates = _selection_candidates(entity)

        for candidate in candidates:
            rid = _row_id_for(candidate)
            if rid is None:
                continue
            if rid not in ids:
                ids.append(rid)
            break
    return ids


# ---------------------------------------------------------------------------
# Palette messaging
# ---------------------------------------------------------------------------
def _palette():
    return ui.palettes.itemById(PALETTE_ID)


def _push(action, payload):
    palette = _palette()
    if palette and _safe(lambda: palette.isVisible, False):
        try:
            palette.sendInfoToHTML(action, json.dumps(payload))
        except Exception:
            app.log('{}: failed to push "{}" to palette:\n{}'.format(
                ADDIN_TITLE, action, traceback.format_exc()))


def _log(message, level='info'):
    """Write to the Text Commands console AND the palette's log pane.

    The palette pane is the one the user can actually see while working; the
    console line survives even when the palette is shut.
    """
    app.log('{}: {}'.format(ADDIN_TITLE, message))
    _push('log', {'message': message, 'level': level})


def _manifest_path():
    here = os.path.dirname(os.path.realpath(__file__))
    stem = os.path.basename(os.path.realpath(__file__)).rsplit('.', 1)[0]
    return os.path.join(here, stem + '.manifest')


def _manifest_version():
    """The version in the manifest sitting next to the running code.

    This is the number Fusion's Scripts and Add-Ins panel reads. If it doesn't
    match VERSION, the files on disk are mismatched - which is a different
    problem from Fusion caching stale metadata, and worth telling them apart.
    """
    try:
        with open(_manifest_path(), 'r') as handle:
            return str(json.load(handle).get('version', '?'))
    except Exception as err:
        return 'unreadable ({})'.format(err)


def _install_banner():
    here = os.path.dirname(os.path.realpath(__file__))
    manifest_version = _manifest_version()
    ui_version = _ui_version[0] or '?'
    bad = (manifest_version != VERSION) or (ui_version not in ('?', VERSION))
    tail = '   <-- MISMATCH' if bad else ''
    return ('Selection Inspector v{} · palette UI v{} · manifest on disk v{}{} · {}'
            .format(VERSION, ui_version, manifest_version, tail, here))


def _banner_level():
    ui_version = _ui_version[0]
    ok = (_manifest_version() == VERSION and
          (ui_version is None or ui_version == VERSION))
    return 'sys' if ok else 'err' 


def _payload_full():
    # a rescan invalidates every row id, and the overlay is keyed to one
    _flash_clear()
    doc_name = _safe(lambda: app.activeDocument.name, 'Untitled')
    _last_marker[0] = _marker_key()
    started = time.time()
    rows = _scan()
    _last_scan_ms[0] = (time.time() - started) * 1000.0
    # Enumerating BRep geometry is the floor on this, so the per-entity rate is
    # the number that decides what the cap can be. Logged whenever the scan is
    # slow enough to be felt.
    if _last_scan_ms[0] > 2000 and rows:
        _log('Scanned {:,} rows in {:.1f} s - {:.2f} ms each. The cap is {:,}; '
             'that rate is what it buys.'
             .format(len(rows), _last_scan_ms[0] / 1000.0,
                     _last_scan_ms[0] / max(1, len(rows)), SUB_ENTITY_CAP), 'warn')
    _last_model[0] = _model_key()
    _stale[0] = False
    return {'ok': True, 'version': VERSION, 'document': doc_name, 'rows': rows,
            'selected': _selected_row_ids(),
            'selCount': _fusion_selection_count(),
            'subEntities': _include_sub,
            'subCount': _scan_stats.get('sub', 0),
            'truncated': _scan_stats.get('truncated', False),
            'subCap': SUB_ENTITY_CAP,
            'sketchState': _sketch_state(),
            'timeline': _timeline_state(),
            'banner': _install_banner(),
            'bannerLevel': _banner_level(),
            # Also here, not only on a selection push: switching Sub-entities
            # on with something already picked produces a full payload, and
            # that is exactly the moment the pick needs its group loaded.
            'hints': _selection_hints(),
            'scanMs': int(_last_scan_ms[0]),
            'payloadKb': _last_payload_kb[0],
            'autoScanMs': AUTO_SCAN_MS,
            'stale': False,
            'legendOpen': _legend_open()}


def _check_ui_version(reported):
    """Python and palette.html are two files, loaded by two different things.

    The title bar and the startup banner both come from this file, so they can
    say v2.31.2 while CEF is still showing a palette.html it cached earlier -
    and every symptom of that looks like "the fix did nothing". Nothing on
    screen could tell the two apart, which is why this exists.

    The page reports its own version on connect. On a mismatch the page is
    reloaded from disk once, which clears it; if it comes back mismatched
    again the log says so plainly rather than pretending.
    """
    _ui_version[0] = reported
    if not reported or reported == VERSION:
        return
    if _ui_reloaded[0]:
        _log('The palette UI is still v{} while the add-in is v{}. Reloading did '
             'not clear it - close the palette and reopen it, or restart Fusion.'
             .format(reported, VERSION), 'err')
        return
    _ui_reloaded[0] = True
    _log('The palette UI is v{} but the add-in is v{} - CEF served a cached page. '
         'Reloading it from disk.'.format(reported, VERSION), 'warn')
    palette = _palette()
    html_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), PALETTE_FILE)
    # Reassigning the URL is what forces CEF to re-fetch the file.
    if palette and not _safe(lambda: setattr(palette, 'htmlFileURL', html_path), True):
        _log('Could not reload the palette automatically - close it and reopen it.',
             'err')


def _handle_message(action, data_str):
    """Returns a JSON-serialisable dict for the palette. Raises UserError for
    expected problems so the boundary can report them without a traceback."""
    data = {}
    if data_str:
        try:
            data = json.loads(data_str)
        except Exception:
            data = {}

    if action in ('ready', 'refresh'):
        global _include_sub
        if 'uiVersion' in data:
            _check_ui_version(str(data.get('uiVersion')))
        if 'subEntities' in data:
            _include_sub = bool(data.get('subEntities'))
        return _payload_full()

    if action == 'loadSub':
        owner_id = data.get('ownerId')
        type_label = data.get('type')
        if owner_id is None or not type_label:
            raise UserError('Nothing to load.')
        return {'ok': True, 'ownerId': owner_id, 'type': type_label,
                'rows': _load_sub_rows(int(owner_id), str(type_label)),
                'selected': _selected_row_ids(),
                'selCount': _fusion_selection_count()}

    if action == 'loadAllSub':
        # The escape hatch. Filtering and sorting only see rows that exist, so
        # there has to be a way to say "actually, all of them" - with the cost
        # stated rather than discovered.
        out = []
        started = time.time()
        for owner_id in list(_sub_context.keys()):
            for group in _sub_context[owner_id].get('groups', []):
                out.extend(_load_sub_rows(owner_id, group))
            if len(out) >= SUB_ENTITY_CAP:
                break
        _log('Loaded {:,} sub-entities in {:.1f} s.'
             .format(len(out), time.time() - started), 'info')
        return {'ok': True, 'rows': out, 'all': True,
                'truncated': len(out) >= SUB_ENTITY_CAP,
                'selected': _selected_row_ids(),
                'selCount': _fusion_selection_count()}

    if action == 'setVisibility':
        ids = data.get('ids') or []
        value = bool(data.get('visible'))
        # Showing something is pointless while an ancestor is switched off, so
        # walk the parents up as well. Opt-out is available from the palette.
        with_parents = value and data.get('withParents', True)
        ok, failed, parents_on = 0, [], 0
        for rid in ids:
            entity = _entity_map.get(int(rid))
            if entity is None:
                failed.append({'id': rid, 'error': 'row is stale - hit Refresh'})
                continue
            try:
                if with_parents:
                    parents_on += _show_ancestors(int(rid))
                _set_visible(entity, value)
                ok += 1
            except Exception as err:
                failed.append({'id': rid,
                               'name': _safe(lambda e=entity: e.name, '?'),
                               'error': str(err)})
        _safe(lambda: app.activeViewport.refresh())
        if failed:
            _log('{} item(s) could not be {}: {}'.format(
                len(failed), 'shown' if value else 'hidden',
                '; '.join(f.get('error', '?') for f in failed[:3])), 'err')
        return {'ok': True, 'changed': ok, 'failed': failed, 'parentsShown': parents_on}

    if action == 'setSelection':
        return _set_selection(data.get('ids') or [])

    # NOTE: row clicks remain inert. The Selected checkbox is the only thing in
    # the table that writes to ui.activeSelections, and it does so by sending
    # the complete desired set rather than a delta.

    if action == 'showIn':
        return _show_in(data.get('id'), data.get('where'))

    if action == 'toggleLegend':
        return _toggle_legend()

    if action == 'saveLog':
        return _save_log(data.get('html', ''), data.get('text', ''))

    if action == 'visibilityMode':
        return _apply_visibility_mode(data.get('mode', 'all'))

    if action == 'textCommand':
        spec = TEXT_COMMANDS.get(data.get('command'))
        if not spec:
            raise UserError('That command is not available from this palette.')

        state = _sketch_state()
        if spec['needsSketch'] and not state['inSketch']:
            raise UserError('"{}" only works while you are editing a sketch.\n'
                            'Double-click a sketch to edit it, then try again.'
                            .format(spec['label']))
        names = spec['command']
        if isinstance(names, str):
            names = [names]
        result, used, errors = None, None, []
        for name in names:
            try:
                result = app.executeTextCommand(name)
                used = name
                break
            except Exception as err:
                # Fusion often raises with no message at all, which is how this
                # arrived as `Fusion refused "sketch.showunderconstrained":`
                # followed by nothing. Say so rather than printing a bare colon.
                errors.append('{} -> {}'.format(name, str(err).strip() or '(no message)'))

        if used is None:
            tl = _timeline_state()
            why = []
            if tl.get('available') and tl.get('position', 0) < tl.get('count', 0):
                # A rolled-back marker is the one cause worth naming: the sketch
                # exists, the button is enabled, and the command still fails.
                why.append('The history marker is rolled back to {} of {}. Fusion '
                           'refuses this command while the timeline is not at the '
                           'end - roll it forward and try again.'
                           .format(tl['position'], tl['count']))
            why.append('Tried: ' + '; '.join(errors))
            raise UserError('"{}" did not run on "{}".\n\n{}'
                            .format(spec['label'], state.get('sketch') or 'the open sketch',
                                    '\n\n'.join(why)))

        _log('Ran {} -> {}'.format(used, str(result).strip() or '(no output)'), 'ok')
        return {'ok': True, 'command': used,
                'result': str(result) if result is not None else '',
                'sketchState': state}

    if action == 'flash':
        how = _flash_set(data.get('id'))
        if not how:
            # a kind with no drawable form is not an error worth a dialog, but
            # it should not look like the overlay simply failed to appear.
            # v2.36.0: say which step gave up - "nothing drawable" was true of
            # a missing design, a refused graphics group and an unrepresentable
            # entity alike, and those need different fixes.
            return {'ok': True, 'flashing': False,
                    'why': _flash.get('why') or 'Nothing drawable for that row.'}
        # which component accepted the group is worth saying: root refused
        # once already, and the next refusal should not need another round
        owner = _flash.get('owner') or ''
        return {'ok': True, 'flashing': True,
                'how': how + (' on ' + owner if owner else '')}

    if action == 'flashPulse':
        return {'ok': True, 'flashing': _flash_pulse(bool(data.get('on', True)))}

    if action == 'flashOff':
        _flash_clear()
        return {'ok': True, 'flashing': False}

    if action == 'fitView':
        _safe(lambda: app.activeViewport.fit())
        return {'ok': True}

    if action == 'log':
        app.log('{}: {}'.format(ADDIN_TITLE, data.get('text', '')))
        return {'ok': True}

    return {'ok': False, 'error': 'Unknown action "{}"'.format(action)}


class PaletteIncomingHandler(adsk.core.HTMLEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            # Logged so "the palette shows nothing" is diagnosable from the
            # Text Commands palette: no lines here means the HTML never reached
            # Python, i.e. the browser-side bridge never came up.
            app.log('{}: <- {}'.format(ADDIN_TITLE, args.action))
            result = _handle_message(args.action, args.data)
        except UserError as err:
            _log(str(err).split('\n')[0], 'warn')
            result = {'ok': False, 'error': str(err)}
        except Exception:
            trace = traceback.format_exc()
            _log('Unexpected error in "{}" - see Text Commands for the traceback.'
                 .format(args.action), 'err')
            app.log('{} error:\n{}'.format(ADDIN_TITLE, trace))
            result = {'ok': False, 'error': 'Unexpected error - see the Text Commands '
                                            'palette for the traceback.',
                      'trace': trace}
        try:
            blob = json.dumps(result)
            # The bridge takes a string, so a big sub-entity scan is a big
            # string. This is what the cap is really buying, so it is measured
            # rather than assumed, and reported once it is large enough to
            # matter.
            if isinstance(result, dict) and result.get('rows') is not None:
                _last_payload_kb[0] = len(blob) // 1024
                if _last_payload_kb[0] > 2048:
                    _log('Payload {:.1f} MB for {:,} rows - if the palette ever '
                         'comes up blank on a scan this size, that is where to '
                         'look.'.format(_last_payload_kb[0] / 1024.0,
                                        len(result['rows'])), 'warn')
            args.returnData = blob
        except Exception:
            args.returnData = json.dumps({'ok': False, 'error': 'Could not serialize result.'})


class SelectionChangedHandler(adsk.core.ActiveSelectionEventHandler):
    """Keeps the table's highlight in sync with the canvas/browser selection."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            if _pushing_selection:
                return          # our own write; the response already carries it
            palette = _palette()
            if not palette or not _safe(lambda: palette.isVisible, False):
                return
            _sel_started = time.time()
            _sel_ids = _selected_row_ids()
            _sel_ms = int((time.time() - _sel_started) * 1000)
            # Matching a picked sub-entity can mean indexing its owner's
            # children for the first time, which is the one place a pick can
            # cost real time. Reported rather than left to be guessed at.
            if _sel_ms > 200:
                _log('Matching the selection took {} ms.'.format(_sel_ms), 'warn')
            _push('selection', {'selected': _sel_ids, 'selMs': _sel_ms,
                                'hints': _selection_hints(),
                                'selCount': _fusion_selection_count(),
                                'sketchState': _sketch_state()})
        except Exception:
            app.log('{}: selection sync failed:\n{}'.format(
                ADDIN_TITLE, traceback.format_exc()))


class CommandTerminatedHandler(adsk.core.ApplicationCommandEventHandler):
    """Entering and leaving sketch edit mode are both commands, so re-reading
    the state after every command keeps the sketch-only buttons honest without
    polling."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            palette = _palette()
            if not palette or not _safe(lambda: palette.isVisible, False):
                return
            _push('state', {'sketchState': _sketch_state()})

            # Fusion has no "marker moved" event, but rolling the history
            # marker terminates a command - so compare the marker after every
            # command and rescan only when it has actually moved.
            marker = _marker_key()
            if marker != _last_marker[0]:
                previous = _last_marker[0]
                _last_marker[0] = marker
                state = _timeline_state()
                if state['available'] and previous is not None:
                    _log('Timeline marker at {} of {} - table refreshed.'
                         .format(state['position'], state['count']), 'info')
                _push('data', _payload_full())
                return

            # Edits that leave the marker alone - a rename, a light bulb
            # toggled in the browser - used to go unnoticed, and nothing told
            # you the table had gone out of date. Now the model is fingerprinted
            # after every command; if it moved, either rescan or say so.
            model = _model_key()
            if model is not None and model != _last_model[0]:
                _last_model[0] = model
                if _last_scan_ms[0] <= AUTO_SCAN_MS:
                    _push('data', _payload_full())
                elif not _stale[0]:
                    _stale[0] = True
                    _log('The model changed. This design takes {} ms to scan, over '
                         'the {} ms auto-refresh limit, so the table is waiting for '
                         'you - press Refresh.'
                         .format(int(_last_scan_ms[0]), AUTO_SCAN_MS), 'warn')
                    _push('state', {'stale': True})
        except Exception:
            app.log('{}: sketch-state push failed:\n{}'.format(
                ADDIN_TITLE, traceback.format_exc()))


class DocumentActivatedHandler(adsk.core.DocumentEventHandler):
    """A different document means a whole new tree - rescan."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            palette = _palette()
            if not palette or not _safe(lambda: palette.isVisible, False):
                return
            _push('data', _payload_full())
        except UserError as err:
            _push('data', {'ok': False, 'error': str(err)})
        except Exception:
            app.log('{}: document rescan failed:\n{}'.format(
                ADDIN_TITLE, traceback.format_exc()))


# ---------------------------------------------------------------------------
# The command that opens the palette
# ---------------------------------------------------------------------------
def _show_palette():
    palette = _palette()
    if not palette:
        html_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), PALETTE_FILE)
        if not os.path.isfile(html_path):
            raise UserError('Palette UI missing.\nExpected: {}'.format(html_path))

        try:
            palette = ui.palettes.add(
                PALETTE_ID, PALETTE_NAME, html_path,
                True,    # isVisible
                True,    # showCloseButton
                True,    # isResizable
                940, 560)
        except Exception:
            # Some builds prefer a path relative to the .py over an absolute one.
            palette = ui.palettes.add(
                PALETTE_ID, PALETTE_NAME, './' + PALETTE_FILE,
                True, True, True, 940, 560)

        _safe(lambda: setattr(palette, 'dockingState',
                              adsk.core.PaletteDockingStates.PaletteDockStateRight))

        on_html = PaletteIncomingHandler()
        palette.incomingFromHTML.add(on_html)
        handlers.append(on_html)

        on_closed = TablePaletteClosedHandler()
        _safe(lambda: palette.closed.add(on_closed))
        handlers.append(on_closed)
    else:
        palette.isVisible = True
        _push('data', _payload_full())


class CommandExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            _show_palette()
        except UserError as err:
            ui.messageBox(str(err), ADDIN_TITLE)
        except Exception:
            ui.messageBox('Unexpected error opening the palette:\n\n{}'.format(
                traceback.format_exc()), ADDIN_TITLE)


class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            # No command inputs: Fusion runs execute immediately and closes the
            # command, so the palette opens with no intermediate dialog.
            on_execute = CommandExecuteHandler()
            args.command.execute.add(on_execute)
            handlers.append(on_execute)
        except Exception:
            ui.messageBox('commandCreated failed:\n\n{}'.format(
                traceback.format_exc()), ADDIN_TITLE)


# ---------------------------------------------------------------------------
# Where the button goes
# ---------------------------------------------------------------------------
def _inspect_panels():
    """Every INSPECT panel Fusion currently exposes, across all context tabs.

    There is no single INSPECT panel - SOLID, SURFACE, MESH, SHEET METAL and the
    rest each own one, with ids that vary by tab and by version. Discovering
    them by walking allToolbarPanels beats hard-coding a guessed list, and keeps
    working when Autodesk adds or renames a tab.
    """
    panels = []
    try:
        all_panels = ui.allToolbarPanels
        for i in range(all_panels.count):
            panel = _safe(lambda idx=i: all_panels.item(idx))
            if panel is None:
                continue
            pid = (_safe(lambda pl=panel: pl.id, '') or '').lower()
            pname = (_safe(lambda pl=panel: pl.name, '') or '').strip().lower()
            if INSPECT_MATCH in pid or pname == INSPECT_MATCH:
                panels.append(panel)
    except Exception:
        app.log('{}: could not enumerate toolbar panels:\n{}'.format(
            ADDIN_TITLE, traceback.format_exc()))
    return panels


def _place_button(cmd_def):
    """Add the button to every INSPECT panel. Returns the panel ids used."""
    placed = []
    panels = _inspect_panels()

    if not panels:
        fallback = ui.allToolbarPanels.itemById(FALLBACK_PANEL_ID)
        if fallback:
            panels = [fallback]
            app.log('{}: no INSPECT panel found, using the ADD-INS panel.'.format(
                ADDIN_TITLE))

    for panel in panels:
        pid = _safe(lambda pl=panel: pl.id, '?')
        try:
            if not panel.controls.itemById(CMD_ID):
                control = panel.controls.addCommand(cmd_def)
                # Sit on the panel itself rather than in its overflow.
                _safe(lambda c=control: setattr(c, 'isPromoted', True))
            placed.append(pid)
        except Exception as err:
            # One awkward panel must not cost us all the others.
            app.log('{}: could not add button to "{}": {}'.format(ADDIN_TITLE, pid, err))
    return placed


def _remove_button_everywhere():
    """Delete our control from every panel that has one. Sweeping all panels
    (rather than only the ones this session placed) also clears leftovers from
    an earlier session that failed to stop cleanly."""
    removed = 0
    try:
        all_panels = ui.allToolbarPanels
        for i in range(all_panels.count):
            panel = _safe(lambda idx=i: all_panels.item(idx))
            if panel is None:
                continue
            control = _safe(lambda pl=panel: pl.controls.itemById(CMD_ID))
            if control:
                _safe(lambda c=control: c.deleteMe())
                removed += 1
    except Exception:
        app.log('{}: teardown sweep failed:\n{}'.format(
            ADDIN_TITLE, traceback.format_exc()))
    return removed


# ---------------------------------------------------------------------------
# run / stop
# ---------------------------------------------------------------------------
def _report_install():
    """Log the running file and the manifest version sitting next to it.

    Fusion's Scripts and Add-Ins panel reads the manifest when it enumerates
    add-ins and caches it for the session, so that panel can show a stale
    version long after the files on disk have moved on. This line is the
    authoritative answer to "what is actually loaded right now".
    """
    here = os.path.dirname(os.path.realpath(__file__))
    app.log('{}: running v{} from {}'.format(ADDIN_TITLE, VERSION, here))

    manifest_path = os.path.join(here, os.path.basename(
        os.path.realpath(__file__)).rsplit('.', 1)[0] + '.manifest')
    try:
        with open(manifest_path, 'r') as handle:
            manifest_version = json.load(handle).get('version', '?')
    except Exception as err:
        app.log('{}: could not read {} ({})'.format(ADDIN_TITLE, manifest_path, err))
        return

    app.log('{}: manifest on disk says v{}'.format(ADDIN_TITLE, manifest_version))
    if manifest_version != VERSION:
        app.log('{}: WARNING - manifest says v{} but the code is v{}. '
                'Looks like a partial copy; reinstall the whole folder.'
                .format(ADDIN_TITLE, manifest_version, VERSION))


def run(context):
    try:
        _report_install()

        # Reuse an existing definition rather than deleting and recreating it.
        # A keyboard shortcut is bound to the command definition, so destroying
        # it throws the user's shortcut away - which is why the binding used to
        # vanish on every reinstall. Reusing keeps the binding intact.
        cmd_def = ui.commandDefinitions.itemById(CMD_ID)
        if cmd_def:
            # Refresh the parts that can go stale between versions.
            _safe(lambda: setattr(cmd_def, 'tooltip', CMD_DESC))
            app.log('{}: reusing the existing command definition '
                    '(keeps any keyboard shortcut)'.format(ADDIN_TITLE))
        else:
            cmd_def = ui.commandDefinitions.addButtonDefinition(
                CMD_ID, CMD_NAME, CMD_DESC, ICON_FOLDER)

        on_created = CommandCreatedHandler()
        cmd_def.commandCreated.add(on_created)
        handlers.append(on_created)

        _placed_panels[:] = _place_button(cmd_def)
        if not _placed_panels:
            ui.messageBox('Could not find a toolbar panel to add the button to.\n'
                          'Open a document and restart the add-in.', ADDIN_TITLE)
            return
        app.log('{}: button added to {} panel(s): {}'.format(
            ADDIN_TITLE, len(_placed_panels), ', '.join(_placed_panels)))

        on_sel = SelectionChangedHandler()
        ui.activeSelectionChanged.add(on_sel)
        handlers.append(on_sel)
        _app_events.append((ui.activeSelectionChanged, on_sel))

        on_cmd = CommandTerminatedHandler()
        ui.commandTerminated.add(on_cmd)
        handlers.append(on_cmd)
        _app_events.append((ui.commandTerminated, on_cmd))

        on_doc = DocumentActivatedHandler()
        app.documentActivated.add(on_doc)
        handlers.append(on_doc)
        _app_events.append((app.documentActivated, on_doc))

    except Exception:
        if ui:
            ui.messageBox('{} failed to start:\n\n{}'.format(
                ADDIN_TITLE, traceback.format_exc()), ADDIN_TITLE)


def stop(context):
    try:
        for event, handler in _app_events:
            try:
                event.remove(handler)
            except Exception:
                pass
        _app_events.clear()

        palette = _palette()
        if palette:
            palette.deleteMe()

        legend = _legend_palette()
        if legend:
            legend.deleteMe()

        _remove_button_everywhere()
        _placed_panels.clear()

        # The command definition is deliberately left registered. Deleting it
        # would take the user's keyboard shortcut with it, and Fusion is happy
        # for it to outlive the add-in: run() reuses it, and the handlers that
        # drive it are released below, so a stopped add-in does nothing.
        handlers.clear()
        _flash_clear()
        _entity_map.clear()
        _token_index.clear()
        _ancestors.clear()

    except Exception:
        if ui:
            ui.messageBox('{} failed to stop cleanly:\n\n{}'.format(
                ADDIN_TITLE, traceback.format_exc()), ADDIN_TITLE)
