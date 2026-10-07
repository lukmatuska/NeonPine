#!/usr/bin/env python3
"""Build NeonPine.kicad_pcb from the schematic netlist: outline, placement, zones.
Usage: python3 tools/pcb.py <netlist.net>   (routing is done afterwards with Freerouting)"""
import sys, math, json, os
import pcbnew
from sx import parse

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.join(HERE, '..')
PCB = os.path.join(PRJ, 'NeonPine.kicad_pcb')
FPL = '/usr/share/kicad/footprints/'
OX, OY = 100.0, 40.0          # board origin offset (mm); design coords: x right, y down, (0,0) = star tip
MM = pcbnew.FromMM
# Scale of the whole tree (outline, lamps, holes, art, fixed and start positions). 1.0 = rev B size (54.8 x 69.1 mm).
# Part-to-part offsets inside a lamp's switch stack are not scaled.
SC = 1.0
sc = lambda *v: tuple(round(a * SC, 3) for a in v)

# ---------------- net classes (written to the project file before the board is created)
HV_PAT = ['Net-(LA*', 'Net-(Q???-C?)', 'Net-(R5-Pad2)']          # lamp nets: behind 150k, may use both layers
HVBUS_PAT = ['/HV+', '/SW', 'Net-(C8-Pad1)']                            # unlimited 105 V source: never as tracks on F.Cu (route.py)
PWR_PAT = ['/VBUS', '/VBUS_F', '+5V', 'GND']
def write_project():
    def cls(name, clr, tw, vd=0.6, vdr=0.3, prio=0):
        return dict(name=name, clearance=clr, track_width=tw, via_diameter=vd, via_drill=vdr,
                    microvia_diameter=0.3, microvia_drill=0.1, diff_pair_width=0.2, diff_pair_gap=0.25,
                    diff_pair_via_gap=0.25, wire_width=6, bus_width=12, line_style=0, priority=prio,
                    schematic_color='rgba(0, 0, 0, 0.000)', pcb_color='rgba(0, 0, 0, 0.000)')
    prj = {"meta": {"filename": "NeonPine.kicad_pro", "version": 3},
           "board": {"design_settings": {"rules": {"min_clearance": 0.15, "min_track_width": 0.15,
                     "min_via_diameter": 0.5, "min_through_hole_diameter": 0.3, "min_copper_edge_clearance": 0.3,
                     "min_hole_clearance": 0.25, "min_hole_to_hole": 0.25}}},
           "net_settings": {"meta": {"version": 4},
                            "classes": [cls('Default', 0.15, 0.15), cls('HV', 0.5, 0.3, 0.7, 0.35, 1),
                                        cls('PWR', 0.15, 0.4, 0.7, 0.35, 2),
                                        cls('HVBUS', 0.5, 0.3, 0.7, 0.35, 3)],
                            "netclass_patterns": [{"netclass": "HV", "pattern": p} for p in HV_PAT] +
                                                 [{"netclass": "PWR", "pattern": p} for p in PWR_PAT] +
                                                 [{"netclass": "HVBUS", "pattern": p} for p in HVBUS_PAT]}}
    fn = os.path.join(PRJ, 'NeonPine.kicad_pro')
    old = json.load(open(fn)) if os.path.exists(fn) else {}   # keep everything else KiCad stored in the project
    def merge(dst, src):
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict): merge(dst[k], v)
            else: dst[k] = v
    merge(old, prj)
    json.dump(old, open(fn, 'w'), indent=2)

# ---------------- outline: star + 3 tiers + pot
def P(x, y): return pcbnew.VECTOR2I(MM(OX + x), MM(OY + y))
def poly(pts):
    s = pcbnew.SHAPE_POLY_SET(); s.NewOutline()
    for x, y in pts: s.Append(MM(OX + x), MM(OY + y))
    return s
def outline():
    star = [(r * math.cos(math.radians(a)), 10.5 * SC - r * math.sin(math.radians(a)))
            for k in range(10) for a, r in [(90 + 36 * k, (10.5 if k % 2 == 0 else 4.4) * SC)]]
    shapes = [star,
              [(0, 12), (14, 30), (-14, 30)],
              [(0, 22), (20, 44), (-20, 44)],
              [(0, 31), (30, 56), (-30, 56)],
              [(-21, 55.5), (21, 55.5), (21, 59.5), (18, 59.5), (18, 68.5), (16.5, 70), (-16.5, 70), (-18, 68.5), (-18, 59.5), (-21, 59.5)]]
    shapes = [shapes[0]] + [[sc(x, y) for x, y in sh] for sh in shapes[1:]]
    u = poly(shapes[0])
    for s in shapes[1:]: u.BooleanAdd(poly(s))
    u.Simplify()
    u = u.Fillet(MM(1.5), MM(0.01))   # rounded corners all round
    # stand tabs on the pot bottom edge (plug into the base plate made by tools/cover.py)
    for tx, tw in TABS:
        u.BooleanAdd(poly([(tx - tw / 2, 70 * SC - 0.5), (tx + tw / 2, 70 * SC - 0.5), (tx + tw / 2, 70 * SC + TAB_H), (tx - tw / 2, 70 * SC + TAB_H)]))
    u.Simplify()
    return u

TABS = [(-11.0 * SC, 4.0), (11.0 * SC, 4.0)]   # stand tabs under the pot: centre x, width
TAB_H = 1.6                           # = base plate thickness
# M2 holes for the rear cover standoffs (cover = blank FR-4 plate, see tools/cover.py); keep-out radius on the back
HOLES = [sc(-13.0, 40.5), sc(13.0, 40.5), sc(-14.6, 67.6)]   # 3-point fixing; the bottom-right corner belongs to USB-C + input protection
HOLE_KEEP = 2.5               # standoff Ø4 hex + margin

# ---------------- fixed parts (design coords, rotation, side)
LAMPS = {1: (0, 8.0), 2: (-4.5, 21.5), 3: (4.5, 21.5), 4: (-7.99, 34.0), 5: (0, 34.0), 6: (7.99, 34.0),
         7: (-14, 46.3), 8: (-5.0, 46.3), 9: (5.0, 46.3), 10: (14, 46.3)}   # centre of each lamp's 3 mm pad pair
# Spacing rules behind these numbers: each lamp's glass (courtyard to ya + 11.3) must end above the next tier's pads, the
# outer lamps' pads keep >= 0.3 mm to the board edge, and the 8 mm tier-2 pitch leaves routing room between the switch stacks.
LAMPS = {n: sc(*p) for n, p in LAMPS.items()}
FIXED = {
    'TP2': (*sc(-8.6, 66.4), 0, 'F'),          # pot touch pad (front)
    'Q2': (*sc(-21.2, 52.5), 0, 'F'),          # ambient-light phototransistor = ornament in the left wing
    'J1': (18 * SC - 3.4, 63.5 * SC, 270, 'B'),  # USB-C, mouth flush with the right pot edge
    # the three big parts fill the pot: boost switch + inductor on the left, MCU next to the USB connector
    'L11': (*sc(-10.5, 61.2), 180, 'B'), 'Q1': (*sc(-1.5, 62.0), 90, 'B'), 'U1': (*sc(6.3, 62.5), 90, 'B'),
    # USB input protection in the strip right above the connector: TVS first, then the PTC
    'D3': (*sc(12.6, 56.8), 0, 'B'), 'F1': (*sc(17.6, 56.9), 0, 'B'),
    # lamp-drive shift register U3 sits in the right wing next to lamps 9/10 (the only free spot in the tree besides the
    # centre of tier 3, which U2 gets from the optimiser); pinswap.py then gives it the lamps closest to it
    'U3': (*sc(19.4, 51.8), 180, 'B'),
}
# every lamp hangs down from its pad pair (pad 1 = K on the left, pad 2 = A on the right). On the back under the lamp body
# sits one stack per lamp, 5.4 mm wide and 6.3 mm tall:
#   * pull-ups R3n (K, left) and R2n (A, right): 0603 HV types standing vertical (rot 270: HV+ pad on top, 0.5 mm below the
#     lamp pad; lamp-node pad at the bottom),
#   * Q1n = MMDT5551 (SOT-363) centred below them. Seen on the back at rot 0 its left pin column is C1 (K collector, top-left,
#     right under R3n), B2, E2 and its right column E1, B1, C2 (A collector, bottom-right: reaches the A node through a via),
#   * base resistors 0402 standing beside the transistor, each level with its base pin: R5n (A side, B2) on the left,
#     R4n (K side, B1) on the right (base pad on top, drive line at the bottom).
# SOT-363 pins are 0.3 mm apart, so the HV clearance is relaxed inside the transistor courtyards (NeonPine.kicad_dru).
SX, SB = 1.6, 2.2           # pull-up / base-resistor column offset from the lamp centre
YR, YQ = 2.5, 5.2           # pull-up / transistor centre below the lamp pads
for n, (x, ya) in LAMPS.items():
    FIXED[f'LA{n}'] = (x, ya, 0, 'F')
    FIXED[f'R{30 + n}'] = (x - SX, ya + YR, 270, 'B')
    FIXED[f'R{20 + n}'] = (x + SX, ya + YR, 270, 'B')
    FIXED[f'Q{10 + n}'] = (x, ya + YQ, 0, 'B')
    FIXED[f'R{50 + n}'] = (x - SB, ya + YQ, 90, 'B')
    FIXED[f'R{40 + n}'] = (x + SB, ya + YQ, 90, 'B')
# everything else is placed by the optimiser (optimise()), starting from these rough positions (all on the back)
START = {r: (*sc(x, y), rot) for r, (x, y, rot) in {
    'D1': (-8.75, 50.5, 90), 'C4': (0, 47.6, 0), 'D2': (0, 52.85, 90),
    'C3': (0, 57.6, 0), 'R1': (-7.0, 57.0, 90), 'R2': (-9.6, 56.9, 90),
    'R5': (9.5, 48.0, 90), 'R6': (9.5, 51.5, 90), 'R7': (7.2, 57.0, 90), 'C6': (9.0, 57.0, 90),
    'R11': (6.0, 67.7, 0), 'C7': (-5.6, 67.9, 90), 'TP3': (-8.5, 68.0, 0),
    'C5': (-23, 55.0, 0), 'R9': (-17.0, 48.4, 0),
    'C1': (17.2, 56.8, 0), 'C2': (17.2, 54.6, 0),
    'R3': (17.2, 52.4, 0), 'R4': (17.2, 50.2, 0),
    'FB1': (15.0, 53.0, 0), 'R12': (-10.0, 57.5, 0), 'C8': (-12.0, 57.5, 0),
    'J2': (2.0, 67.0, 90),     # SWD pogo pads (production programming, before the cover goes on)
    'U2': (0.0, 46.4, 180),    # lamp-drive shift register (74HC595BQ, DHVQFN-16), centre of tier 3; U3 is fixed (FIXED)
    'C9': (-3.7, 44.1, 180), 'C10': (17.0, 49.0, 0),
}.items()}
GAP = 0.1   # extra spacing around each optimised part (0.2 mm on top of the courtyards)
# airwire weights: short, fat switching loops first, then decoupling and the sensitive ADC node
NET_W = {'/SW': 8, '/GATE': 4, '/GATE_DRV': 2, '/HV+': 1.5, '/VFB': 2, '/FB_MID': 1.5, 'GND': 0.0}
PAIR_W = [(('C6', '1'), ('U1', '9'), 6), (('C6', '2'), ('U1', '7'), 4),        # MCU decoupling
          (('C3', '1'), ('L11', '1'), 6), (('C3', '2'), ('Q1', '3'), 5),        # boost input loop
          (('C4', '2'), ('Q1', '3'), 3), (('C5', '1'), ('U1', '20'), 4),        # output loop, ADC filter
          (('C7', '1'), ('U1', '4'), 3), (('C2', '1'), ('FB1', '2'), 3), (('C1', '1'), ('FB1', '2'), 4),
          (('FB1', '1'), ('F1', '1'), 4), (('D3', '1'), ('J1', 'A9'), 15),           # input filter, TVS at the connector
          (('R3', '1'), ('J1', 'A5'), 4), (('R4', '1'), ('J1', 'B5'), 4), (('D3', '2'), ('J1', 'A12'), 6),
          (('R12', '1'), ('Q1', '2'), 5), (('C8', '2'), ('Q1', '3'), 4),             # optional snubber at Q1
          (('D1', '2'), ('Q1', '2'), 12),                                            # SW node: diode right at the drain tab
          (('R2', '1'), ('Q1', '1'), 3), (('D1', '1'), ('C4', '1'), 10), (('D2', '1'), ('C4', '1'), 4),
          (('F1', '2'), ('J1', 'A9'), 8),
          (('C9', '1'), ('U2', '16'), 6), (('C9', '2'), ('U2', '8'), 3), (('C10', '1'), ('U3', '16'), 6), (('C10', '2'), ('U3', '8'), 3)]

# ---------------- front silkscreen art: rim line, a string of light beads along the branches, snowflakes, little stars.
# Everything is clipped automatically around pads, front parts (lamp bodies, LDR, touch pads), text and the board edge.
FLAKES = [(*sc(9.4, 27.4), 1.4), (*sc(-9.4, 27.4), 1.4), (*sc(21.8, 53.4), 1.8)]  # x, y, radius
STARS = [(*sc(-17.5, 47.4), 0.7), (*sc(17.0, 47.0), 0.7), (*sc(-25.0, 54.3), 0.65), (*sc(-9.8, 62.5), 0.8), (*sc(9.8, 62.5), 0.8)]
def art(board, ol, fps):
    pads = []
    for fp in fps.values():
        for pad in fp.Pads():
            if pad.HasHole() or not fp.IsFlipped():
                sz = pad.GetSize(pcbnew.F_Cu)
                pads.append((pad.GetPosition().x / 1e6 - OX, pad.GetPosition().y / 1e6 - OY, max(sz.x, sz.y) / 2e6 + 0.35))
    boxes = []
    for fp in fps.values():
        if fp.IsFlipped(): continue
        c = fp.GetCourtyard(pcbnew.F_CrtYd)
        if c.OutlineCount():
            bb = c.BBox(); boxes.append((bb.GetLeft() / 1e6 - OX - 0.2, bb.GetTop() / 1e6 - OY - 0.2,
                                         bb.GetRight() / 1e6 - OX + 0.2, bb.GetBottom() / 1e6 - OY + 0.2))
    dr = board.Drawings()
    for t in (dr[i].Cast() for i in range(len(dr))):   # SWIG iterators are broken on Python 3.14
        if isinstance(t, pcbnew.PCB_TEXT) and t.GetLayer() == pcbnew.F_SilkS:
            bb = t.GetBoundingBox(); boxes.append((bb.GetLeft() / 1e6 - OX - 0.4, bb.GetTop() / 1e6 - OY - 0.4,
                                                   bb.GetRight() / 1e6 - OX + 0.4, bb.GetBottom() / 1e6 - OY + 0.4))
    safe = pcbnew.SHAPE_POLY_SET(ol); safe.Inflate(-MM(0.55), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, MM(0.01))
    def ok(x, y, use_boxes=True, m=0.0):
        if not safe.Contains(P(x, y)): return False
        if any((x - px) ** 2 + (y - py) ** 2 < (r + m) ** 2 for px, py, r in pads): return False
        return not (use_boxes and any(b[0] - m < x < b[2] + m and b[1] - m < y < b[3] + m for b in boxes))
    def seg(a, b, w):
        s = pcbnew.PCB_SHAPE(board); s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetLayer(pcbnew.F_SilkS)
        s.SetStart(P(*a)); s.SetEnd(P(*b)); s.SetWidth(MM(w)); board.Add(s)
    def dot(x, y, r):
        s = pcbnew.PCB_SHAPE(board); s.SetShape(pcbnew.SHAPE_T_CIRCLE); s.SetLayer(pcbnew.F_SilkS)
        s.SetStart(P(x, y)); s.SetEnd(P(x + r, y)); s.SetFilled(True); s.SetWidth(0); board.Add(s)
    def path(pts, w, use_boxes=True, step=0.2, emit=0.6):
        """Draw a polyline, leaving gaps wherever it would hit something."""
        sm = []
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            n = max(1, int(math.hypot(x1 - x0, y1 - y0) / step))
            sm += [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(n)]
        sm.append(pts[-1])
        run = []
        for p in sm + [None]:
            if p is not None and ok(*p, use_boxes, w / 2):
                run.append(p); continue
            k = max(1, int(emit / step))
            pick = run[::k] + ([run[-1]] if run and (len(run) - 1) % k else [])
            for a, b in zip(pick, pick[1:]): seg(a, b, w)
            run = []
        return sm
    # 1. rim: a thin line tracing the whole outline just inside the edge
    rim = pcbnew.SHAPE_POLY_SET(ol); rim.Inflate(-MM(0.9), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, MM(0.01))
    o = rim.Outline(0)
    pts = [(o.CPoint(i).x / 1e6 - OX, o.CPoint(i).y / 1e6 - OY) for i in range(o.PointCount())]
    path(pts + pts[:1], 0.15)
    # 2. string of light beads along the slanted branch edges, one step further in than the rim
    bead = pcbnew.SHAPE_POLY_SET(ol); bead.Inflate(-MM(1.9), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, MM(0.01))
    o = bead.Outline(0)
    bp = [(o.CPoint(i).x / 1e6 - OX, o.CPoint(i).y / 1e6 - OY) for i in range(o.PointCount())]
    acc = 0.0
    for (x0, y0), (x1, y1) in zip(bp, bp[1:] + bp[:1]):
        L = math.hypot(x1 - x0, y1 - y0)
        slanted = L > 0 and 0.3 < abs(y1 - y0) / L < 0.95 and 12.5 * SC < y0 < 54.5 * SC  # branch sides only (not the star, not flats)
        n = max(1, int(L / 0.1))
        for i in range(n):
            acc += L / n
            if acc >= 2.0:
                x, y = x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n
                if slanted and ok(x, y, True, 0.5): dot(x, y, 0.28); acc = 0.0
    # 3. snowflakes: 6 arms with two side ticks each (drawn only if they fit completely)
    def flake(cx, cy, r):
        lines = []
        for k in range(6):
            a = math.radians(90 + 60 * k); ux, uy = math.cos(a), -math.sin(a)
            lines.append(((cx, cy), (cx + ux * r, cy + uy * r)))
            for f, l in ((0.55, 0.35), (0.8, 0.22)):
                bx, by = cx + ux * r * f, cy + uy * r * f
                for s in (-1, 1):
                    b = a + s * math.radians(50)
                    lines.append(((bx, by), (bx + math.cos(b) * r * l, by - math.sin(b) * r * l)))
        if all(ok(*p, True, 0.1) for ln in lines for p in ln):
            for a, b in lines: seg(a, b, 0.12)
        else: print('   (snowflake at %.1f,%.1f skipped: no room)' % (cx, cy))
    for f in FLAKES: flake(*f)
    # 4. little five-pointed stars
    for cx, cy, r in STARS:
        p = [(cx + (r if k % 2 == 0 else r * 0.42) * math.cos(math.radians(90 + 36 * k)),
              cy - (r if k % 2 == 0 else r * 0.42) * math.sin(math.radians(90 + 36 * k))) for k in range(10)]
        if all(ok(*q, True, 0.1) for q in p):
            for a, b in zip(p, p[1:] + p[:1]): seg(a, b, 0.12)
        else: print('   (star at %.1f,%.1f skipped: no room)' % (cx, cy))

SEEDS = 4
def optimise(comps, make, put, crt, inner, blocked, iters=250000):
    """Simulated annealing of the START parts on the back: minimise weighted airwire length (MST per net plus
    explicit pad-pair pulls), keeping every part inside the board, off the fixed parts and THT keepouts, and
    GAP apart from each other. Moves: shift, rotate, swap two parts."""
    import random
    STEP = 0.25
    X0, Y0, NX, NY = -32.0 * SC, -2.0, int(64 * SC / STEP), int((72 * SC + 2) / STEP)
    # static obstacle grid -> 2D prefix sums for O(1) "is this rectangle free" checks
    bad = [[0] * NX for _ in range(NY)]
    for j in range(NY):
        for i in range(NX):
            x, y = X0 + (i + 0.5) * STEP, Y0 + (j + 0.5) * STEP
            if not inner.Contains(P(x, y)) or any(r[0] < x < r[2] and r[1] < y < r[3] for r in blocked): bad[j][i] = 1
    if os.environ.get('NP_MAP'):
        for j in range(0, NY, 4): print(''.join('#' if any(bad[jj][ii] for jj in range(j, min(NY, j + 4)) for ii in range(i, min(NX, i + 2))) else '.' for i in range(0, NX, 2)))
    S = [[0] * (NX + 1) for _ in range(NY + 1)]
    for j in range(NY):
        row = 0
        for i in range(NX):
            row += bad[j][i]; S[j + 1][i + 1] = S[j][i + 1] + row
    def blocked_area(r):
        """mm^2 of static obstacles (or off-board) under rectangle r"""
        i0, j0 = int((r[0] - X0) / STEP), int((r[1] - Y0) / STEP)
        i1, j1 = int(math.ceil((r[2] - X0) / STEP)), int(math.ceil((r[3] - Y0) / STEP))
        if i0 < 0 or j0 < 0 or i1 > NX or j1 > NY: return 1e3
        return (S[j1][i1] - S[j0][i1] - S[j1][i0] + S[j0][i0]) * STEP * STEP
    free = lambda r: blocked_area(r) == 0
    # per-part geometry for each rotation (pad offsets, courtyard incl. GAP), measured on the back side
    geo, fps = {}, {}
    for ref in START:
        fp = make(ref); fps[ref] = fp; geo[ref] = {}
        for rot in (0, 90, 180, 270):
            put(fp, 0, 0, rot, 'B'); c = crt(fp)
            geo[ref][rot] = ({p.GetNumber(): (p.GetPosition().x / 1e6 - OX, p.GetPosition().y / 1e6 - OY) for p in fp.Pads()},
                             (c[0] - GAP, c[1] - GAP, c[2] + GAP, c[3] + GAP))
    # fixed pad positions of every other part
    fixed_pads = {}
    for ref, c in comps.items():
        if ref in START: continue
        for fp in [f for f in pcbnew_board_footprints(fps) if f.GetReference() == ref]:
            for p in fp.Pads(): fixed_pads[(ref, p.GetNumber())] = (p.GetPosition().x / 1e6 - OX, p.GetPosition().y / 1e6 - OY)
    nets = {}
    for ref, c in comps.items():
        for pin, n in c['pins'].items(): nets.setdefault(n, []).append((ref, pin))
    nets = {n: v for n, v in nets.items() if NET_W.get(n, 1) > 0 and any(r in START for r, _ in v) and len(v) > 1}
    part_nets = {ref: [n for n, v in nets.items() if any(r == ref for r, _ in v)] for ref in START}
    part_pairs = {ref: [k for k, pr in enumerate(PAIR_W) if pr[0][0] == ref or pr[1][0] == ref] for ref in START}
    state = {ref: list(v) for ref, v in START.items()}
    def pad(ref, pin):
        if ref in state:
            x, y, rot = state[ref]; dx, dy = geo[ref][rot][0][pin]; return (x + dx, y + dy)
        return fixed_pads.get((ref, pin))
    def rect(ref):
        x, y, rot = state[ref]; r = geo[ref][rot][1]; return (r[0] + x, r[1] + y, r[2] + x, r[3] + y)
    def mst(pts):
        pts = [p for p in pts if p]
        if len(pts) < 2: return 0.0
        d = [math.dist(pts[0], q) for q in pts]; used = [False] * len(pts); used[0] = True; L = 0.0
        for _ in range(len(pts) - 1):
            k = min((i for i in range(len(pts)) if not used[i]), key=lambda i: d[i]); L += d[k]; used[k] = True
            for i in range(len(pts)):
                if not used[i]: d[i] = min(d[i], math.dist(pts[k], pts[i]))
        return L
    netc = lambda n: NET_W.get(n, 1) * mst([pad(r, p) for r, p in nets[n]])
    pairc = lambda k: PAIR_W[k][2] * math.dist(pad(*PAIR_W[k][0]), pad(*PAIR_W[k][1]))
    def overlaps(ref, among=None):
        """overlap area (mm^2) with obstacles and with the other optimised parts"""
        r = rect(ref); a = blocked_area(r)
        for o in (state if among is None else among):
            if o == ref: continue
            q = rect(o); w, h = min(r[2], q[2]) - max(r[0], q[0]), min(r[3], q[3]) - max(r[1], q[1])
            if w > 0 and h > 0: a += w * h
        return a
    def local(refs):
        ns = set(n for r in refs for n in part_nets[r]); ks = set(k for r in refs for k in part_pairs[r])
        return sum(netc(n) for n in ns) + sum(pairc(k) for k in ks)
    total = lambda: sum(netc(n) for n in nets) + sum(pairc(k) for k in range(len(PAIR_W)))
    offs = sorted(((dx * 0.25, dy * 0.25) for dx in range(-120, 121) for dy in range(-120, 121)), key=lambda d: d[0] ** 2 + d[1] ** 2)
    def legalise(order, among):
        """move each part in turn to the nearest spot (any rotation) free of obstacles and of the parts in `among`"""
        for ref in order:
            x0, y0, r0 = state[ref]
            if overlaps(ref, among) == 0: among.append(ref); continue
            for dx, dy in offs:
                done = False
                for rot in (r0, (r0 + 90) % 360, (r0 + 180) % 360, (r0 + 270) % 360):
                    state[ref] = [x0 + dx, y0 + dy, rot]
                    if overlaps(ref, among) == 0: done = True; break
                if done: break
            else: print('!! could not legalise', ref); state[ref] = [x0, y0, r0]
            among.append(ref)
    area = lambda ref: (lambda r: (r[2] - r[0]) * (r[3] - r[1]))(geo[ref][0][1])
    refs = list(state)
    def anneal(seed):
        rnd = random.Random(seed)
        for ref, v in START.items(): state[ref] = list(v)
        legalise(sorted(refs, key=area, reverse=True), [])
        # penalty continuation: overlaps are cheap at first (parts can slide past each other), then prohibitive
        for it in range(iters):
            f = it / iters
            T = 20.0 * (0.002 / 20.0) ** f
            lam = 2.0 * (20000.0 / 2.0) ** min(1.0, f / 0.8)
            m = rnd.random()
            if m < 0.15:
                a, b = rnd.sample(refs, 2); moved = (a, b); old = {a: state[a][:], b: state[b][:]}
                before = local(moved) + lam * sum(overlaps(r) for r in moved)
                state[a][0], state[b][0] = old[b][0], old[a][0]; state[a][1], state[b][1] = old[b][1], old[a][1]
            else:
                a = rnd.choice(refs); moved = (a,); old = {a: state[a][:]}
                before = local(moved) + lam * overlaps(a)
                if m < 0.3: state[a][2] = rnd.choice((0, 90, 180, 270))
                else:
                    sig = 0.25 + 6.0 * T / 20.0
                    state[a][0] = round((state[a][0] + rnd.gauss(0, sig)) / 0.05) * 0.05
                    state[a][1] = round((state[a][1] + rnd.gauss(0, sig)) / 0.05) * 0.05
            delta = local(moved) + lam * sum(overlaps(r) for r in moved) - before
            if delta > 0 and rnd.random() >= math.exp(-delta / max(T, 1e-9)):
                for r, v in old.items(): state[r] = v
        legalise(sorted(refs, key=area, reverse=True), [])       # big parts keep their spot, small ones make way
        polish(rnd, iters // 8)
        return total(), {r: v[:] for r, v in state.items()}
    def polish(rnd, n):
        """low-temperature anneal that only accepts legal states"""
        for it in range(n):
            T = 0.5 * (0.002 / 0.5) ** (it / n)
            a = rnd.choice(refs); old = state[a][:]; before = local((a,))
            if rnd.random() < 0.2: state[a][2] = rnd.choice((0, 90, 180, 270))
            else:
                state[a][0] = round((state[a][0] + rnd.gauss(0, 0.4)) / 0.05) * 0.05
                state[a][1] = round((state[a][1] + rnd.gauss(0, 0.4)) / 0.05) * 0.05
            if overlaps(a): state[a] = old; continue
            d = local((a,)) - before
            if d > 0 and rnd.random() >= math.exp(-d / T): state[a] = old
    start_cost = total()
    results = sorted((anneal(seed) for seed in range(SEEDS)), key=lambda t: t[0])
    print('placement seeds:', ' '.join('%.0f' % c for c, _ in results))
    for r, v in results[0][1].items(): state[r] = v
    # greedy clean-up: move each part to its best legal spot anywhere on a 1 mm grid (two rounds), then polish
    grid = [(x * 0.5, y * 0.5) for x in range(-int(60 * SC), int(60 * SC) + 1, 2) for y in range(0, int(140 * SC) + 1, 2)]
    for _ in range(2):
        for ref in refs:
            best = (local((ref,)), state[ref][:])
            for x, y in grid:
                for rot in (0, 90, 180, 270):
                    state[ref] = [x, y, rot]
                    if not free(rect(ref)) or overlaps(ref): continue
                    c = local((ref,))
                    if c < best[0] - 1e-6: best = (c, [x, y, rot])
            state[ref] = best[1]
    polish(random.Random(99), iters // 8)
    bad_parts = [r for r in state if overlaps(r)]
    for r in bad_parts:
        print('   %s at %s rect %s free=%s with %s' % (r, state[r], tuple(round(v, 2) for v in rect(r)), free(rect(r)),
              [o for o in state if o != r and rect(r)[0] < rect(o)[2] and rect(o)[0] < rect(r)[2] and rect(r)[1] < rect(o)[3] and rect(o)[1] < rect(r)[3]]))
    print('placement: cost %.0f -> %.0f%s' % (start_cost, total(), ('  !! overlaps: ' + ' '.join(bad_parts)) if bad_parts else ''))
    for ref, (x, y, rot) in state.items(): put(fps[ref], x, y, rot, 'B')

def pcbnew_board_footprints(fps):
    b = next(iter(fps.values())).GetBoard(); f = b.Footprints()
    return [f[i] for i in range(len(f))]

def free_spot(board, fps, ol, near, w, h):
    """Nearest point to `near` where a w x h back-side silkscreen box clears every back pad/courtyard and THT pad."""
    boxes = []
    for fp in fps.values():
        for p in fp.Pads():
            if p.HasHole() or fp.IsFlipped():
                b = p.GetBoundingBox(); boxes.append((b.GetLeft() / 1e6 - OX, b.GetTop() / 1e6 - OY, b.GetRight() / 1e6 - OX, b.GetBottom() / 1e6 - OY))
        if fp.IsFlipped():
            c = fp.GetCourtyard(pcbnew.B_CrtYd)
            if c.OutlineCount():
                b = c.BBox(); boxes.append((b.GetLeft() / 1e6 - OX, b.GetTop() / 1e6 - OY, b.GetRight() / 1e6 - OX, b.GetBottom() / 1e6 - OY))
    inner = pcbnew.SHAPE_POLY_SET(ol); inner.Inflate(-MM(0.8), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, MM(0.01))
    best = None
    for xi in range(-int(280 * SC), int(280 * SC) + 1, 5):
        for yi in range(50, int(700 * SC), 5):
            x, y = xi / 10, yi / 10
            r = (x - w / 2 - 0.25, y - h / 2 - 0.25, x + w / 2 + 0.25, y + h / 2 + 0.25)
            if any(r[0] < q[2] and q[0] < r[2] and r[1] < q[3] and q[1] < r[3] for q in boxes): continue
            if not all(inner.Contains(P(px, py)) for px in (r[0], r[2]) for py in (r[1], r[3])): continue
            d = (x - near[0]) ** 2 + (y - near[1]) ** 2
            if best is None or d < best[0]: best = (d, x, y)
    return best[1:] if best else near

def load_netlist(path):
    e = parse(open(path).read())[0]
    g = lambda l, k: next(x for x in l if isinstance(x, list) and x[0] == k)
    comps = {}
    for c in g(e, 'components')[1:]:
        ref = g(c, 'ref')[1].strip('"')
        ts = [x for x in c if isinstance(x, list) and x[0] == 'tstamps'][-1][1].strip('"')
        dnp = any(isinstance(x, list) and x[0] == 'property' and any(isinstance(y, list) and y[:2] == ['name', '"dnp"'] for y in x)
                  for x in c)
        comps[ref] = dict(val=g(c, 'value')[1].strip('"'), fp=g(c, 'footprint')[1].strip('"'), ts=ts, pins={}, dnp=dnp)
    for n in g(e, 'nets')[1:]:
        name = g(n, 'name')[1].strip('"')
        for nd in [x for x in n if isinstance(x, list) and x[0] == 'node']:
            comps[g(nd, 'ref')[1].strip('"')]['pins'][g(nd, 'pin')[1].strip('"')] = name
    return comps

def main(netfile):
    write_project()
    comps = load_netlist(netfile)
    board = pcbnew.NewBoard(PCB)
    board.SetCopperLayerCount(2)        # F.Cu / B.Cu (all SMD parts); 2 layers to save cost
    ol = outline()
    # edge cuts
    o = ol.Outline(0)
    for i in range(o.PointCount()):
        a, b = o.CPoint(i), o.CPoint((i + 1) % o.PointCount())
        s = pcbnew.PCB_SHAPE(board); s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetLayer(pcbnew.Edge_Cuts)
        s.SetStart(a); s.SetEnd(b); s.SetWidth(MM(0.1)); board.Add(s)
    inner = pcbnew.SHAPE_POLY_SET(ol); inner.Inflate(-MM(0.35), pcbnew.CORNER_STRATEGY_CHAMFER_ALL_CORNERS, MM(0.01))
    # nets
    nets = {}
    for c in comps.values():
        for n in c['pins'].values():
            if n not in nets:
                nets[n] = pcbnew.NETINFO_ITEM(board, n); board.Add(nets[n])
    fps = {}
    def make(ref):
        c = comps[ref]; lib, name = c['fp'].split(':')
        fp = pcbnew.FootprintLoad((PRJ + '/' if lib == 'NeonPine' else FPL) + lib + '.pretty', name)
        fp.SetFPID(pcbnew.LIB_ID(lib, name)); fp.SetReference(ref); fp.SetValue(c['val'])
        fp.SetPath(pcbnew.KIID_PATH('/' + c['ts']))
        fp.Reference().SetLayer(pcbnew.F_Fab)   # keep silkscreen for art only
        fp.SetDNP(c['dnp'])
        for pad in fp.Pads():
            if pad.GetNumber() in c['pins']: pad.SetNet(nets[c['pins'][pad.GetNumber()]])
            if ref == 'J1' and pad.GetNumber() == 'SH':
                pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)   # shell pins: solid to GND (ESD return)
        board.Add(fp); fps[ref] = fp
        return fp
    def put(fp, x, y, rot, side):
        if fp.IsFlipped(): fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        fp.SetOrientationDegrees(0); fp.SetPosition(P(x, y)); fp.SetOrientationDegrees(rot)
        if side == 'B': fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    def crt(fp):
        lay = pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd
        c = fp.GetCourtyard(lay)
        bb = c.BBox() if c.OutlineCount() else fp.GetBoundingBox(False)
        return [bb.GetLeft() / 1e6 - OX, bb.GetTop() / 1e6 - OY, bb.GetRight() / 1e6 - OX, bb.GetBottom() / 1e6 - OY]
    rects = {'F': [], 'B': []}; keep = []   # keep: THT pad keepouts (both sides)
    for ref, (x, y, rot, side) in FIXED.items():
        fp = make(ref); put(fp, x, y, rot, side); rects[side].append(crt(fp))
        for pad in fp.Pads():
            if pad.HasHole():
                px, py = pad.GetPosition().x / 1e6 - OX, pad.GetPosition().y / 1e6 - OY
                r = max(pad.GetSize(pcbnew.F_Cu).x, pad.GetSize(pcbnew.F_Cu).y) / 2e6 + 0.6
                keep.append([px - r, py - r, px + r, py + r])
    for i, (hx, hy) in enumerate(HOLES):
        h = pcbnew.FootprintLoad(FPL + 'MountingHole.pretty', 'MountingHole_2.2mm_M2')
        h.SetReference('H%d' % (i + 1)); h.SetValue('M2 cover standoff'); h.Reference().SetLayer(pcbnew.F_Fab)
        h.SetBoardOnly(True); h.SetExcludedFromBOM(True); h.SetExcludedFromPosFiles(True)
        h.SetPosition(P(hx, hy)); board.Add(h); fps[h.GetReference()] = h
        keep.append([hx - HOLE_KEEP, hy - HOLE_KEEP, hx + HOLE_KEEP, hy + HOLE_KEEP])
    hit = lambda a, b: a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
    def inside(r):
        x0, y0, x1, y1 = r
        nx, ny = max(2, int((x1 - x0) / 0.5) + 1), max(2, int((y1 - y0) / 0.5) + 1)
        pts = [(x0 + (x1 - x0) * i / (nx - 1), y) for i in range(nx) for y in (y0, y1)] + \
              [(x, y0 + (y1 - y0) * j / (ny - 1)) for j in range(ny) for x in (x0, x1)]
        return all(inner.Contains(P(x, y)) for x, y in pts)
    optimise(comps, make, put, crt, inner, rects['B'] + keep)
    # silkscreen art on the front
    def text(t, x, y, h, layer=pcbnew.F_SilkS):
        s = pcbnew.PCB_TEXT(board); s.SetText(t); s.SetPosition(P(x, y)); s.SetLayer(layer)
        s.SetTextSize(pcbnew.VECTOR2I(MM(h), MM(h))); s.SetTextThickness(MM(h * 0.15))
        s.SetMirrored(layer == pcbnew.B_SilkS); board.Add(s)
    text('NEON PINE', 0, 62.6 * SC, 2.2)
    # HV warning on the back: nearest free spot to the HV output cap C4
    c4 = fps['C4'].GetPosition(); tx, ty = free_spot(board, fps, ol, (c4.x / 1e6 - OX, c4.y / 1e6 - OY), 4.4, 1.4)
    text('100 V!', tx, ty, 0.8, pcbnew.B_SilkS)
    art(board, ol, fps)
    # GND pours on the outer layers only; both inner layers are kept free for routing (EMC is not critical here)
    for lay in (pcbnew.F_Cu, pcbnew.B_Cu):
        z = pcbnew.ZONE(board); z.SetLayer(lay); z.SetNet(nets['GND'])
        z.Outline().AddOutline(ol.Outline(0)); z.SetLocalClearance(MM(0.3))
        z.SetMinThickness(MM(0.25)); z.SetThermalReliefGap(MM(0.3)); z.SetThermalReliefSpokeWidth(MM(0.4))
        z.SetAssignedPriority(0); z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)   # SMD pads solid, THT (hand-soldered) with spokes
        board.Add(z)
    board.GetDesignSettings().SetBoardThickness(MM(1.6))
    pcbnew.SaveBoard(PCB, board)
    print('placed', len(fps), 'footprints')

if __name__ == '__main__':
    main(sys.argv[1])
