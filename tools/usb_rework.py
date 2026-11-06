#!/usr/bin/env python3
"""One-off board update for the USB rework (branch USB). Applies the new netlist to the *existing* board without touching
the rest of the routing:
  * J1: USB4125 (power-only, 6P) -> USB4105-GF-A (USB 2.0, 16P, same GCT family and shell pattern), PCB-edge line kept at x 118.
  * C7 (NRST cap) removed: PD7 is SR_DATA now.
  * new parts R13/R14 (68R series), D4/D5 (3.6 V zeners, SOD-882), R15 (1k5 D- pull-up); R3/R4 (CC) moved to the strip below J1.
  * every pad gets its net (and every footprint its symbol path) from the netlist.
  * rip-up: only the copper of the nets whose MCU pin moved, inside the U1 / J1 window (SR_*, LDR, GATE_DRV, CC, VBUS/GND at
    J1), the old LAMP10 route and NRST. LAMP10 / LAMPA10 at U3 are re-drawn here (U3 QE / QD).
The open connections are then routed by tools/route_local.py (Freerouting with every other track locked).
Usage: kicad-cli sch export netlist --format kicadsexpr -o np.net NeonPine.kicad_sch
       python3 tools/usb_rework.py np.net"""
import os, sys
import pcbnew
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from sx import parse

PCB = os.path.join(HERE, '..', 'NeonPine.kicad_pcb')
FP = '/usr/share/kicad/footprints/'
MM = pcbnew.FromMM
seq = lambda c: [c[i] for i in range(len(c))]
V = lambda x, y: pcbnew.VECTOR2I(MM(x), MM(y))
mm = pcbnew.ToMM

# ---- netlist
t = parse(open(sys.argv[1]).read())[0]
g = lambda e, k: [x for x in e if isinstance(x, list) and x[0] == k]
comps = {}
for c in g(t, 'components')[0][1:]:
    ref = g(c, 'ref')[0][1].strip('"')
    comps[ref] = dict(value=g(c, 'value')[0][1].strip('"'), fp=g(c, 'footprint')[0][1].strip('"'),
                      uuid=g(c, 'tstamps')[0][1].strip('"'))
pinnet = {}
for n in g(t, 'nets')[0][1:]:
    name = g(n, 'name')[0][1].strip('"')
    for nd in g(n, 'node'):
        pinnet[(g(nd, 'ref')[0][1].strip('"'), g(nd, 'pin')[0][1].strip('"'))] = name

b = pcbnew.LoadBoard(PCB)

def load(fpid):
    """pcbnew.FootprintLoad() is broken in this KiCad 10 build (plugin lookup); the S-expression IO class works"""
    lib, name = fpid.split(':')
    f = pcbnew.PCB_IO_KICAD_SEXPR().FootprintLoad(FP + lib + '.pretty', name)
    f.SetFPID(pcbnew.LIB_ID(lib, name))
    return f

# after any BOARD.Remove() this build's SWIG layer hands back untyped objects from every call that returns a FOOTPRINT
# (FootprintLoad, FindFootprintByReference, ...): load / look up everything first and remove items only at the very end
NEW = {ref: load(comps[ref]['fp']) for ref in ('J1', 'R13', 'R14', 'D4', 'D5', 'R15')}
FPS = {f.GetReference(): f for f in seq(b.Footprints())}
OLD = [FPS.pop('C7'), FPS.pop('J1')]

def place(ref, x, y, rot, pad1=None):
    """put footprint ref on B.Cu at (x, y) with orientation rot; pad1 = 'top'/'bottom'/'left'/'right' (board view) flips it 180
    if pad 1 ends up on the wrong side"""
    f = FPS.get(ref)
    if f is None:
        f = FPS[ref] = NEW[ref]; f.SetReference(ref); f.GetField(pcbnew.FIELD_T_DATASHEET).SetText('~'); b.Add(f)
    if not f.IsFlipped():
        f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    f.SetPosition(V(x, y)); f.SetOrientationDegrees(rot)
    if pad1:
        p = f.FindPadByNumber('1').GetPosition(); c = f.GetPosition()
        ok = {'top': p.y < c.y, 'bottom': p.y > c.y, 'left': p.x < c.x, 'right': p.x > c.x}[pad1]
        if not ok: f.SetOrientationDegrees(rot + 180)
    return f

# ---- footprints
j1 = NEW['J1']
# USB4125 footprint had its PCB-edge line at local y 3.4 (board x 118.0); USB4105 has it at 3.675 -> centre x 114.325
place('J1', 118.0 - 3.675, 103.5, -90)
place('R13', 107.45, 107.65, 90, 'top')      # D+ series, MCU side (pad 1) up
place('R14', 108.45, 107.65, 90, 'top')      # D- series, pad 1 up under U1 pin 1
place('D4', 107.10, 109.25, 0, 'right')      # D+ zener, cathode (pad 1) right
place('D5', 108.75, 109.25, 0, 'right')      # D- zener
place('R4', 110.60, 109.37, 0, 'left')       # CC2 (pad 1) left
place('R15', 112.50, 109.37, 0, 'right')     # VBUS (pad 1) right
place('R3', 114.45, 109.37, 0, 'left')       # CC1

def drag(ref, dx, dy):
    """move a placed footprint and the track ends sitting on its pads"""
    f = FPS[ref]; d = V(dx, dy)
    on = lambda q: any(p.HitTest(q) and p.IsOnLayer(tr.GetLayer()) for p in f.Pads())
    for tr in [x.Cast() for x in seq(b.Tracks())]:
        if tr.GetClass() == 'PCB_VIA': continue
        a0, a1 = on(tr.GetStart()), on(tr.GetEnd())
        if a0: tr.SetStart(tr.GetStart() + d)
        if a1: tr.SetEnd(tr.GetEnd() + d)
    f.SetPosition(f.GetPosition() + d)
drag('C5', 0, -0.16)    # J1's (longer) courtyard reaches y 98.18

for ref, f in FPS.items():
    if ref not in comps: continue
    f.SetValue(comps[ref]['value'])
    f.SetPath(pcbnew.KIID_PATH('/' + comps[ref]['uuid']))
    for p in f.Pads():
        if not p.GetNumber(): continue
        name = pinnet.get((ref, p.GetNumber()))
        if name is None: p.SetNetCode(0); continue
        net = b.FindNet(name)
        if net is None:
            net = pcbnew.NETINFO_ITEM(b, name); b.Add(net)
        p.SetNet(net)
missing = set(comps) - set(FPS)
assert not missing, missing

# ---- rip-up
def inside(p, w): return w[0] <= mm(p.x) <= w[2] and w[1] <= mm(p.y) <= w[3]
W_U1 = (102.5, 99.5, 117.0, 110.5)     # under / around U1, the U1-J1 gap, the strip below
W_J1 = (106.3, 98.5, 118.6, 110.5)     # J1 and the strip below it
W_G = (109.65, 96.7, 118.6, 110.5)
rip = {'/SR_LATCH': W_U1, '/SR_DATA': W_U1, '/SR_CLK': W_U1, '/SR_CHAIN': W_U1, '/LDR': W_U1, '/GATE_DRV': W_U1,
       '/VBUS': W_J1, 'GND': W_J1}
gone = {'/NRST', '/LAMP10', '/CC1', '/CC2'}
kill = []
for tr in [x.Cast() for x in seq(b.Tracks())]:
    net = tr.GetNetname()
    if net in gone: kill.append(tr); continue
    if net == '/LAMPA10':    # LAMPA10 leaves U3 one pin lower now (QD); LAMP10 takes QE, straight to R50
        if tr.GetClass() != 'PCB_VIA' and tr.GetLayer() == pcbnew.B_Cu and min(mm(tr.GetStart().x), mm(tr.GetEnd().x)) > 117.0 \
                and mm(tr.GetStart().y) < 93.5: kill.append(tr)
        continue
    if net == 'GND' and tr.GetClass() != 'PCB_VIA' and (inside(tr.GetStart(), W_G) or inside(tr.GetEnd(), W_G)):
        kill.append(tr); continue    # GND stubs to the old J1 shell / around C5 (the pours connect GND)
    if net not in rip: continue
    w = rip[net]
    if tr.GetClass() == 'PCB_VIA':
        if inside(tr.GetPosition(), w): kill.append(tr)
    elif inside(tr.GetStart(), w) and inside(tr.GetEnd(), w):
        kill.append(tr)

def track(net, pts, w=0.15, layer=pcbnew.B_Cu):
    for a, c in zip(pts, pts[1:]):
        s = pcbnew.PCB_TRACK(b); s.SetStart(V(*a)); s.SetEnd(V(*c)); s.SetWidth(MM(w)); s.SetLayer(layer)
        s.SetNet(b.FindNet(net)); b.Add(s)
u3, r50 = FPS['U3'], FPS['R50']
xy = lambda f, pad: (mm(f.FindPadByNumber(pad).GetPosition().x), mm(f.FindPadByNumber(pad).GetPosition().y))
assert u3.FindPadByNumber('4').GetNetname() == '/LAMP10' and u3.FindPadByNumber('3').GetNetname() == '/LAMPA10'
track('/LAMP10', [xy(u3, '4'), xy(r50, '1')])
qd = xy(u3, '3'); track('/LAMPA10', [qd, (117.604, qd[1]), (117.127, 93.027)])
print('J1 pads:', {p.GetNumber(): (round(mm(p.GetPosition().x), 3), round(mm(p.GetPosition().y), 3))
                   for p in j1.Pads() if p.GetNumber() in ('A5', 'B5', 'A6', 'B7')})
for it in kill + OLD: b.Remove(it)
pcbnew.SaveBoard(PCB, b)
print('removed', len(kill), 'track items and', [f.GetReference() for f in OLD])
sys.stdout.flush(); os._exit(0)     # skip interpreter teardown: the GC of removed SWIG objects segfaults in this build
