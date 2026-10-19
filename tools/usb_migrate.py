#!/usr/bin/env python3
"""USB branch: apply the new netlist to the existing, hand-finished NeonPine.kicad_pcb in place
(pcb.py would rebuild the board from scratch and lose the hand routing).
  * J1 -> 16-pin USB4105 (same mouth position), new parts placed at free spots (PLACE below),
  * pad nets updated from the netlist,
  * nets whose pad set changed are ripped up completely; tracks of other nets that collide with the new parts are cut
    (only the colliding items), and dangling track ends are trimmed.
Then finish with:  python3 tools/route.py <freerouting-2.4.1.jar> --keep ; python3 tools/fixup.py
Usage: python3 tools/usb_migrate.py <netlist.net> [--dry]"""
import sys, os, math
import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pcb import load_netlist, FPL, PRJ, PCB, OX, OY, HOLES, HOLE_KEEP, P, MM

seq = lambda c: [c[i] for i in range(len(c))]
comps = load_netlist(sys.argv[1]); dry = '--dry' in sys.argv
b = pcbnew.LoadBoard(PCB)
nets = {}
def net(n):
    if n not in nets:
        ni = b.FindNet(n)
        if ni is None: b.Add(pcbnew.NETINFO_ITEM(b, n)); ni = b.FindNet(n)   # re-fetch: the netcode is assigned by Add()
        nets[n] = ni
    return nets[n]
def put(fp, x, y, rot):
    if fp.IsFlipped(): fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    fp.SetOrientationDegrees(0); fp.SetPosition(P(x, y)); fp.SetOrientationDegrees(rot)
    fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)   # all new parts on the back
def load(ref):
    lib, name = comps[ref]['fp'].split(':')
    return pcbnew.FootprintLoad((PRJ + '/' if lib == 'NeonPine' else FPL) + lib + '.pretty', name)
def make(ref):
    c = comps[ref]; lib, name = c['fp'].split(':')
    fp = LOADED[ref]
    if fp.GetReference() == ref: return fp
    fp.SetFPID(pcbnew.LIB_ID(lib, name)); fp.SetReference(ref); fp.SetValue(c['val'])
    fp.SetPath(pcbnew.KIID_PATH('/' + c['ts'])); fp.Reference().SetLayer(pcbnew.F_Fab)   # B.Fab once put() flips it
    fp.SetField('Datasheet', '~')                                                              # as the schematic has it
    return fp

# new-part positions (design coords, rotation; all on the back). J1: mouth (Dwgs line at y 3.675) on the pot edge x = 18.
PLACE = {'J1': (18 - 3.675, 63.5, 270)}
NEW_AT = {
    'U4': (-18.4, 56.7, 180),   # 3.3 V LDO in the free left wing, next to L11's +5V pad; VI faces L11
    'U5': (1.2, 56.3, 0),       # gate buffer above the MCU's PC end: A (pin 2) faces PD2, Y (pin 4) drops past Q1 to R1
    'R13': (4.0, 57.75, 180),   # 1.5k right above PC2 (pin 12, D-) and PC4 (pin 14, DPU)
}
AUTO = {'C11': ('U4', '2'), 'C12': ('U5', '5'),   # decoupling: nearest free spot to that pad (after the parts above are placed)
        'C5': ('U1', '20')}                       # ADC filter cap, pushed out of the wider J1 courtyard (also in MOVE)
MOVE = {   # existing parts pushed aside for the wider 16-pin J1 courtyard
    'C7': (5.7, 68.35, 0), 'R3': (8.5, 67.15, 180), 'R4': (8.5, 68.45, 180), 'C5': (9.6, 57.1, 90),
}

fps = {f.GetReference(): f for f in seq(b.Footprints())}
assert 'J1_OLD' not in fps, 'board already migrated'
fps_old = set(fps)
# Nothing is removed from the board until the very end (dead / remove_all()): after a few b.Remove() calls SWIG returns
# bare SwigPyObjects for every new wrapper (KiCad 10 / Python 3.14), so FootprintLoad(), fp.Pads() etc. fail.
LOADED = {r: load(r) for r in comps if r not in fps or r == 'J1'}
for r in LOADED: make(r)
changed = set()
dead = set()                     # m_Uuid of the tracks/vias to delete
kid = lambda t: t.m_Uuid.AsString()
live_tracks = lambda: [t for t in seq(b.Tracks()) if kid(t) not in dead]
def remove_all():
    for t in seq(b.Tracks()):
        if kid(t) in dead: b.Remove(t)
# 1. J1 swap
old = fps['J1']
for t in seq(b.Tracks()):   # tracks that ended on the old J1 pads (GND stubs): cut
    if any(p.GetNetname() == t.GetNetname() and (p.HitTest(t.GetStart()) or p.HitTest(t.GetEnd())) for p in old.Pads()):
        dead.add(kid(t))
old.SetReference('J1_OLD')
j1 = make('J1'); b.Add(j1); put(j1, *PLACE['J1']); fps['J1'] = j1
for p in j1.Pads():
    if p.GetNumber() == 'SH': p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
changed |= {'/VBUS', '/CC1', '/CC2'}
# 2. new parts; moved parts lose the tracks that ended on their pads
for ref in comps:
    if ref not in fps:
        fp = make(ref); b.Add(fp); fps[ref] = fp
        x, y, r = NEW_AT.get(ref, (0, 0, 0)); put(fp, x, y, r)
for ref, (x, y, r) in MOVE.items():
    fp = fps[ref]
    for t in seq(b.Tracks()):
        if any(p.GetNetname() == t.GetNetname() and (p.HitTest(t.GetStart()) or p.HitTest(t.GetEnd())) for p in fp.Pads()):
            dead.add(kid(t))
    put(fp, x, y, r)
    changed |= {p.GetNetname() for p in fp.Pads()}
# 3. pad nets
for ref, fp in fps.items():
    if ref.startswith('H') or ref == 'J1_OLD': continue
    assert ref in comps, ref
    for p in fp.Pads():
        if not p.GetNumber(): continue
        new = comps[ref]['pins'].get(p.GetNumber(), '')
        if p.GetNetname() != new:
            changed |= {p.GetNetname(), new} - {''}
            if new: p.SetNet(net(new))
            else: p.SetNetCode(0)
changed.discard('GND')
print('changed nets:', ' '.join(sorted(changed)))
for t in seq(b.Tracks()):
    if t.GetNetname() in changed: dead.add(kid(t))
fps_old.discard('J1')

# 4. free-space map of the back (0.1 mm grid): courtyards, THT pads, remaining B.Cu copper, holes, board edge
X0, Y0, X1, Y1, G = -30.0, 38.0, 30.0, 72.0, 0.1
NX, NY = int((X1 - X0) / G), int((Y1 - Y0) / G)
occ = [[False] * NX for _ in range(NY)]
def block(x0, y0, x1, y1):
    for j in range(max(0, int((y0 - Y0) / G)), min(NY, int((y1 - Y0) / G) + 1)):
        row = occ[j]
        for i in range(max(0, int((x0 - X0) / G)), min(NX, int((x1 - X0) / G) + 1)): row[i] = True
bb = lambda r: (r.GetLeft() / 1e6 - OX, r.GetTop() / 1e6 - OY, r.GetRight() / 1e6 - OX, r.GetBottom() / 1e6 - OY)
def crt(fp):
    c = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd)
    return bb(c.BBox()) if c.OutlineCount() else bb(fp.GetBoundingBox(False))
def obstacles(skip=()):
    for j in range(NY):
        for i in range(NX): occ[j][i] = False
    for ref, fp in fps.items():
        if ref in skip or ref == 'J1_OLD': continue
        if fp.IsFlipped():
            x0, y0, x1, y1 = crt(fp); block(x0 - 0.05, y0 - 0.05, x1 + 0.05, y1 + 0.05)
        for p in fp.Pads():
            if p.HasHole(): x0, y0, x1, y1 = bb(p.GetBoundingBox()); block(x0 - 0.3, y0 - 0.3, x1 + 0.3, y1 + 0.3)
    for t in live_tracks():
        if not t.IsOnLayer(pcbnew.B_Cu): continue
        if t.GetClass() == 'PCB_VIA':
            m = t.Cast().GetWidth(pcbnew.B_Cu) / 2e6 + 0.2
            q = t.GetPosition(); x, y = q.x / 1e6 - OX, q.y / 1e6 - OY; block(x - m, y - m, x + m, y + m); continue
        m = t.GetWidth() / 2e6 + 0.2
        a, c = t.GetStart(), t.GetEnd(); ax, ay, cx, cy = a.x / 1e6 - OX, a.y / 1e6 - OY, c.x / 1e6 - OX, c.y / 1e6 - OY
        n = max(1, int(math.hypot(cx - ax, cy - ay) / 0.1))
        for k in range(n + 1):
            x, y = ax + (cx - ax) * k / n, ay + (cy - ay) * k / n; block(x - m, y - m, x + m, y + m)
    for hx, hy in HOLES: block(hx - HOLE_KEEP, hy - HOLE_KEEP, hx + HOLE_KEEP, hy + HOLE_KEEP)
    inner = pcbnew.SHAPE_POLY_SET(); b.GetBoardPolygonOutlines(inner, True); inner.Inflate(-MM(0.5), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, MM(0.01))
    for j in range(NY):
        for i in range(NX):
            if not occ[j][i] and not inner.Contains(P(X0 + i * G, Y0 + j * G)): occ[j][i] = True
def search(ref, near, rots=(0, 90), n=6):
    """n best free spots for ref's courtyard nearest to `near` (summed-area table over the occupancy grid)."""
    import numpy as np   # imported late: importing numpy before the first FootprintLoad breaks pcbnew's SWIG plugin lookup
    o = np.array(occ, dtype=np.int32); S = np.zeros((NY + 1, NX + 1), np.int32); S[1:, 1:] = o.cumsum(0).cumsum(1)
    fp = fps[ref]; pos = fp.GetPosition(); flip = fp.IsFlipped(); rot0 = fp.GetOrientationDegrees(); out = []
    for r in rots:
        put(fp, 0, 0, r); x0, y0, x1, y1 = crt(fp); w, h = int(math.ceil((x1 - x0) / G)) + 1, int(math.ceil((y1 - y0) / G)) + 1
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2          # courtyard centre relative to the footprint origin
        tot = S[h:, w:] - S[:-h, w:] - S[h:, :-w] + S[:-h, :-w]
        for j, i in zip(*np.nonzero(tot == 0)):
            x, y = X0 + (i + w / 2) * G - cx, Y0 + (j + h / 2) * G - cy
            out.append((round(math.dist((x, y), near), 2), round(float(x), 2), round(float(y), 2), r))
    out.sort(); best = []
    for c in out:
        if all(math.dist(c[1:3], q[1:3]) > 1.0 for q in best): best.append(c)
        if len(best) == n: break
    return best
def pad_xy(ref, num):
    q = fps[ref].FindPadByNumber(num).GetPosition(); return (q.x / 1e6 - OX, q.y / 1e6 - OY)
if dry and '--search' in sys.argv:
    TARGET = {'U4': ('FB1', '2', 'U1', '9'), 'C11': ('U1', '9', 'U1', '9'), 'U5': ('U1', '19', 'R1', '1'), 'C12': ('U1', '19', 'R1', '1'),
              'R14': ('J1', 'A6', 'U1', '11'), 'R15': ('J1', 'A7', 'U1', '12'), 'R13': ('J1', 'A7', 'U1', '14')}
    obstacles(skip=[r for r in LOADED if r != 'J1' and r not in NEW_AT])
    for ref, (r1, p1, r2, p2) in TARGET.items():
        a, c = pad_xy(r1, p1), pad_xy(r2, p2); near = ((a[0] + c[0]) / 2, (a[1] + c[1]) / 2)
        print(ref, 'near (%.1f, %.1f):' % near, search(ref, near))
# 5b. cut other-net copper that the new / moved pads now sit on
def cut_under(refs):
    clr = lambda t: 0.5 if t.GetNetClassName() in ('HV', 'HVBUS') else 0.2
    def rect_dist(px, py, r):
        dx = max(r[0] - px, 0, px - r[2]); dy = max(r[1] - py, 0, py - r[3]); return math.hypot(dx, dy)
    pads = []
    for ref in refs:
        for p in fps[ref].Pads():
            q = p.GetBoundingBox(); pads.append((p.GetNetname(), p.HasHole(), p.IsOnLayer(pcbnew.B_Cu), p.IsOnLayer(pcbnew.F_Cu),
                                                 (q.GetLeft(), q.GetTop(), q.GetRight(), q.GetBottom())))
    n = 0
    for t in live_tracks():
        via = t.GetClass() == 'PCB_VIA'
        for net_, hole, onb, onf, r in pads:
            if t.GetNetname() == net_ and net_: continue
            if not via and not ((t.GetLayer() == pcbnew.B_Cu and onb) or (t.GetLayer() == pcbnew.F_Cu and onf)): continue
            if via:
                q = t.GetPosition(); hit = rect_dist(q.x, q.y, r) < (t.Cast().GetWidth(pcbnew.B_Cu) / 2 + MM(clr(t)))
            else:
                a_, c_ = t.GetStart(), t.GetEnd(); k = max(1, int(math.hypot(c_.x - a_.x, c_.y - a_.y) / MM(0.05)))
                hit = any(rect_dist(a_.x + (c_.x - a_.x) * i / k, a_.y + (c_.y - a_.y) * i / k, r) < t.GetWidth() / 2 + MM(clr(t))
                          for i in range(k + 1))
            if hit: dead.add(kid(t)); n += 1; break
    print('cut', n, 'other-net track items under the new / moved pads')
# 5. decoupling caps next to their pins
pad_xy = lambda ref, num: (lambda q: (q.x / 1e6 - OX, q.y / 1e6 - OY))(fps[ref].FindPadByNumber(num).GetPosition())
placed = set()
for ref, (r, pn) in AUTO.items():
    obstacles(skip=[k for k in AUTO if k not in placed])
    c = search(ref, pad_xy(r, pn), rots=(0, 90, 180, 270), n=1)
    assert c, ref
    _, x, y, rot = c[0]; put(fps[ref], x, y, rot); placed.add(ref)
    print('%s at (%.2f, %.2f) rot %d, %.2f mm from %s.%s' % (ref, x, y, rot, c[0][0], r, pn))
cut_under(['J1'] + list(NEW_AT) + list(AUTO) + list(MOVE))
obstacles()
for ref in list(NEW_AT) + list(AUTO) + list(MOVE):   # every new / moved courtyard must be clear of everything else
    fp = fps[ref]; x0, y0, x1, y1 = crt(fp)
    others = [k for k, f in fps.items() if k not in (ref, 'J1_OLD') and f.IsFlipped() and
              (lambda o: o[0] < x1 and x0 < o[2] and o[1] < y1 and y0 < o[3])(crt(f))]
    print(ref, 'courtyard overlaps:', others or 'none')
# 6. trim dangling track ends left by the cuts (pure-Python graph first, then one removal pass - see `dead`)
def trim():
    items = []
    for t in seq(b.Tracks()):
        if kid(t) in dead: continue
        if t.GetClass() == 'PCB_VIA':
            q = t.GetPosition(); items.append((kid(t), t.GetNetname(), 'via', (q.x, q.y), None, None))
        else:
            a_, c_ = t.GetStart(), t.GetEnd(); items.append((kid(t), t.GetNetname(), t.GetLayer(), (a_.x, a_.y), (c_.x, c_.y), t.GetWidth()))
    padhit = {}
    def on_pad(net_, xy, layer):
        k = (net_, xy, layer)
        if k not in padhit:
            v = pcbnew.VECTOR2I(*xy)
            padhit[k] = any(p.GetNetname() == net_ and p.HitTest(v) and (layer == 'via' or p.IsOnLayer(layer))
                            for f in fps.values() if f.GetReference() != 'J1_OLD' for p in f.Pads())
        return padhit[k]
    def on_seg(xy, s_, tol):
        (ax, ay), (cx, cy) = s_[3], s_[4]; dx, dy = cx - ax, cy - ay; L2 = dx * dx + dy * dy
        u = 0 if L2 == 0 else max(0, min(1, ((xy[0] - ax) * dx + (xy[1] - ay) * dy) / L2))
        return math.hypot(ax + u * dx - xy[0], ay + u * dy - xy[1]) <= tol
    gone = set(); n0 = len(dead)
    while True:
        alive = [i for i in items if i[0] not in gone]; drop = set()
        for it in alive:
            ends = [it[3]] if it[2] == 'via' else [it[3], it[4]]
            for xy in ends:
                tol = 1000 if it[2] == 'via' else it[5] / 2
                ok = on_pad(it[1], xy, it[2]); lay = set()
                if not ok:
                    for o in alive:
                        if o is it or o[1] != it[1]: continue
                        if it[2] == 'via':   # a via needs tracks on two layers (or a pad); GND vias also reach the pours
                            if it[1] == 'GND': ok = True
                            elif o[2] != 'via' and (math.dist(o[3], xy) < o[5] / 2 or math.dist(o[4], xy) < o[5] / 2):
                                lay.add(o[2]); ok = len(lay) >= 2
                        elif o[2] == 'via':
                            if math.dist(o[3], xy) <= tol + 200000: ok = True
                        elif o[2] == it[2] and on_seg(xy, o, tol): ok = True
                        if ok: break
                if not ok: drop.add(it[0]); break
        if not drop: break
        gone |= drop
    dead.update(gone)
    print('trimmed', len(gone), 'dangling items;', len(dead), 'track items removed in total')
if not dry:
    trim(); remove_all(); b.Remove(old)
    pcbnew.SaveBoard(PCB, b); print('saved', PCB)
if dry and '--map' in sys.argv:
    import numpy as np, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(16, 9.5))
    ax.imshow(np.array(occ), extent=(X0, X1, Y1, Y0), cmap='Greys', alpha=0.35, interpolation='nearest')
    for ref, fp in fps.items():
        if ref == 'J1_OLD' or not fp.IsFlipped(): continue
        x0, y0, x1, y1 = crt(fp)
        if y1 < Y0 + 8: continue
        ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec='b', lw=0.6)); ax.text((x0 + x1) / 2, (y0 + y1) / 2, ref, ha='center', va='center', fontsize=6, color='b')
    for t in live_tracks():
        if t.IsOnLayer(pcbnew.B_Cu) and t.GetClass() != 'PCB_VIA':
            a, c = t.GetStart(), t.GetEnd(); ax.plot([a.x / 1e6 - OX, c.x / 1e6 - OX], [a.y / 1e6 - OY, c.y / 1e6 - OY], 'r-', lw=0.5)
    ax.set_xlim(-26, 24); ax.set_ylim(72, 46); ax.set_xticks(range(-26, 25, 1), minor=True); ax.set_yticks(range(46, 73, 1), minor=True); ax.grid(which='both', lw=0.2)
    ax.set_title('back side seen from the FRONT (design coords, x right)'); fig.savefig(sys.argv[sys.argv.index('--map') + 1], dpi=110, bbox_inches='tight')
if dry and '--crt' in sys.argv:
    for r in sys.argv[sys.argv.index('--crt') + 1].split(','): print(r, [round(v, 2) for v in crt(fps[r])], [(p.GetNumber(), p.GetNetname()) for p in fps[r].Pads()][:20])
