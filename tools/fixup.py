#!/usr/bin/env python3
"""Finish the last few connections Freerouting leaves open.
For every net (except GND, which the pours connect) that is still split into several copper islands, try short
candidate links between the islands, shortest first:
  * a straight segment or a 45-degree dog-leg on a layer both ends share, or
  * via - segment(s) on the other layer - via, with the vias sitting on the net's existing tracks.
Each candidate is checked with KiCad's own shape collision against every other-net item on the layer, using the larger
of the two items' clearances, plus the board edge and NPTH holes. HVBUS nets (HV+, SW, SNUB) stay on B.Cu.
Usage: python3 tools/fixup.py          (edits NeonPine.kicad_pcb in place, refills the zones)"""
import os, math, itertools
import pcbnew

PCB = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'NeonPine.kicad_pcb')
MM = pcbnew.FromMM
BACK_ONLY = {'/HV+', '/SW', '/SNUB'}
CLS = {'HV': (0.3, 0.5, 0.7, 0.35), 'HVBUS': (0.3, 0.5, 0.7, 0.35), 'PWR': (0.4, 0.15, 0.7, 0.35), 'Default': (0.2, 0.15, 0.6, 0.3)}
LAYERS = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
HV_FORBIDDEN = (pcbnew.F_Cu,)   # HVBUS: no tracks on the front copper (vias through it are allowed)
seq = lambda c: [c[i] for i in range(len(c))]
V = lambda x, y: pcbnew.VECTOR2I(int(x), int(y))

b = pcbnew.LoadBoard(PCB)
b.SynchronizeNetsAndNetClasses(True)

def items_of(netname):
    out = []
    for t in seq(b.Tracks()):
        if t.GetNetname() == netname: out.append(t)
    for f in seq(b.Footprints()):
        for p in f.Pads():
            if p.GetNetname() == netname: out.append(p)
    return out

def layers_of(it):
    if isinstance(it, pcbnew.PAD):
        return [l for l in LAYERS if it.IsOnLayer(l)]
    if it.GetClass() == 'PCB_VIA': return list(LAYERS)
    return [it.GetLayer()]

def touching(a, c):
    for l in set(layers_of(a)) & set(layers_of(c)):
        if a.GetEffectiveShape(l).Collide(c.GetEffectiveShape(l), 0): return True
    return False

def islands(netname):
    its = items_of(netname); parent = list(range(len(its)))
    def find(i):
        while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i, j in itertools.combinations(range(len(its)), 2):
        if find(i) != find(j) and touching(its[i], its[j]): parent[find(i)] = find(j)
    groups = {}
    for i, it in enumerate(its): groups.setdefault(find(i), []).append(it)
    return list(groups.values())

def anchors(group):
    """(x, y, layers, via_ok, stub) points where a new link may start. stub = (x0, y0, layer): the point is reached by a
    short extra segment from an SMD pad centre, so a via may sit there (vias never go into SMD pads)."""
    pts = []
    for it in group:
        if isinstance(it, pcbnew.PAD):
            p = it.GetPosition(); pts.append((p.x, p.y, layers_of(it), it.HasHole(), None))
            if not it.HasHole():
                l = layers_of(it)[0]
                for r in (1.0, 1.5, 2.2):
                    for ang in range(0, 360, 45):
                        pts.append((p.x + MM(r) * math.cos(math.radians(ang)), p.y + MM(r) * math.sin(math.radians(ang)), [l], True, (p.x, p.y, l)))
        elif it.GetClass() == 'PCB_VIA':
            p = it.GetPosition(); pts.append((p.x, p.y, list(LAYERS), True, None))
        else:
            a, c = it.GetStart(), it.GetEnd(); n = max(1, int(math.hypot(c.x - a.x, c.y - a.y) / MM(0.5)))
            for k in range(n + 1):
                pts.append((a.x + (c.x - a.x) * k / n, a.y + (c.y - a.y) * k / n, [it.GetLayer()], True, None))
    return pts

edge = [d for d in seq(b.Drawings()) if d.GetLayer() == pcbnew.Edge_Cuts]
npth = [p for f in seq(b.Footprints()) for p in f.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH]

def legal(new, netname):
    """new: list of PCB_TRACK / PCB_VIA not yet on the board"""
    others = [t for t in seq(b.Tracks()) if t.GetNetname() != netname] + \
             [p for f in seq(b.Footprints()) for p in f.Pads() if p.GetNetname() != netname and p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH]
    # items not on the board yet do not resolve their netclass clearance: take it from the class table
    own = MM(CLS.get(b.FindNet(netname).GetNetClassName(), CLS['Default'])[1])
    for it in new:
        for l in layers_of(it):
            if netname in BACK_ONLY and l in HV_FORBIDDEN and it.GetClass() != 'PCB_VIA': return False
            # a via that is not on the board yet reports no copper ring on the inner layers; use its (full) start-layer ring
            s = it.GetEffectiveShape(pcbnew.F_Cu) if it.GetClass() == 'PCB_VIA' else it.GetEffectiveShape(l)
            for o in others:
                if l not in layers_of(o): continue
                clr = max(own, it.GetOwnClearance(l), o.GetOwnClearance(l))
                if s.Collide(o.GetEffectiveShape(l), clr): return False
            for e in edge:
                if s.Collide(e.GetEffectiveShape(), MM(0.3)): return False
            for h in npth:
                if s.Collide(h.GetEffectiveShape(l), MM(0.3)): return False
    return True

def make_track(net, layer, a, c, w):
    t = pcbnew.PCB_TRACK(b); t.SetStart(V(*a)); t.SetEnd(V(*c)); t.SetWidth(MM(w)); t.SetLayer(layer); t.SetNet(net); return t

def make_via(net, p, d, drill):
    v = pcbnew.PCB_VIA(b); v.SetPosition(V(*p)); v.SetWidth(MM(d)); v.SetDrill(MM(drill)); v.SetNet(net); return v

def doglegs(a, c):
    dx, dy = c[0] - a[0], c[1] - a[1]
    if dx == 0 and dy == 0: return [[a, c]]
    if dx == 0 or dy == 0 or abs(abs(dx) - abs(dy)) < 1: dx, dy = dx or 1, dy or 1
    m = min(abs(dx), abs(dy))
    p1 = (a[0] + math.copysign(m, dx), a[1] + math.copysign(m, dy))
    p2 = (c[0] - math.copysign(m, dx), c[1] - math.copysign(m, dy))
    out = [[a, c], [a, p1, c], [a, p2, c]]
    L = math.hypot(dx, dy); nx, ny = -dy / L, dx / L                      # detours around an obstacle
    for off in (1.0, -1.0, 2.0, -2.0, 3.0, -3.0):
        m = ((a[0] + c[0]) / 2 + nx * MM(off), (a[1] + c[1]) / 2 + ny * MM(off)); out.append([a, m, c])
    return out

def try_connect(netname, g0, g1):
    net = b.FindNet(netname)
    cls = net.GetNetClassName()
    w, _, vd, vdr = CLS.get(cls, CLS['Default'])
    pairs = sorted(((math.hypot(p[0] - q[0], p[1] - q[1]), p, q) for p in anchors(g0) for q in anchors(g1)), key=lambda t: t[0])
    for dist, p, q in pairs[:600]:
        if dist > MM(25): break
        a, c = (p[0], p[1]), (q[0], q[1])
        stubs = [make_track(net, e[4][2], (e[4][0], e[4][1]), (e[0], e[1]), w) for e in (p, q) if e[4]]
        cands = []
        for l in set(p[2]) & set(q[2]):                                  # same layer
            for path in doglegs(a, c):
                cands.append([make_track(net, l, u, v, w) for u, v in zip(path, path[1:])])
        for l in LAYERS:                                                # via - other layer - via
            if netname in BACK_ONLY and l in HV_FORBIDDEN: continue
            if not (p[3] and q[3]): continue
            for path in doglegs(a, c):
                cand = [make_track(net, l, u, v, w) for u, v in zip(path, path[1:])]
                if l not in p[2]: cand.append(make_via(net, a, vd, vdr))
                if l not in q[2]: cand.append(make_via(net, c, vd, vdr))
                cands.append(cand)
        for cand in sorted(cands, key=len):
            cand = cand + stubs
            if legal(cand, netname):
                for it in cand: b.Add(it)
                return dist / 1e6, len(cand)
    return None

fixed = 0
nets = sorted({t.GetNetname() for t in seq(b.Tracks())} | {p.GetNetname() for f in seq(b.Footprints()) for p in f.Pads()})
for n in nets:
    if not n or n == 'GND': continue
    for _ in range(5):
        g = islands(n)
        if len(g) < 2: break
        g.sort(key=len, reverse=True)
        r = try_connect(n, g[0], g[1])
        print('%-16s %d islands -> %s' % (n, len(g), ('linked %.1f mm with %d items' % r) if r else 'NO LEGAL LINK FOUND'))
        if not r: break
        fixed += 1
pcbnew.SaveBoard(PCB, b)
# refill on a fresh load so the new items' netclass clearances are used by the filler
b = pcbnew.LoadBoard(PCB); b.SynchronizeNetsAndNetClasses(True); b.BuildConnectivity()
pcbnew.ZONE_FILLER(b).Fill(seq(b.Zones()))
pcbnew.SaveBoard(PCB, b)
print('added', fixed, 'links')
