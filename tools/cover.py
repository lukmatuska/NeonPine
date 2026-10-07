#!/usr/bin/env python3
"""Mechanical PCBs for NeonPine rev B, written to NeonPine-cover.kicad_pcb:
  * REAR COVER: plain FR-4 (no copper) with the tree outline mirrored, so that its F side is the outer face, the M2 holes of
    the main board, the stand tabs, and all product markings in silkscreen (CE, WEEE bin, rating, model, warnings, S/N field).
    It sits on M2 x 5 mm standoffs behind the main board and covers every HV part (risk assessment H1).
  * STAND BASE: 50 x 26 mm plate with slots for the tabs of the tree and of the cover (6.6 mm apart = 1.6 board + 5 standoff).
Usage: python3 tools/cover.py"""
import os, sys, math
import pcbnew
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcb as main                      # outline(), HOLES, TABS, TAB_H

OUT = os.path.join(main.PRJ, 'NeonPine-cover.kicad_pcb')
MM = pcbnew.FromMM
STANDOFF = 5.0
PITCH = 1.6 + STANDOFF                  # tree board -> cover board, plate to plate
BX, BY = 100.0, main.OY + 70 * main.SC + 28   # where the base plate is drawn (absolute mm), below the cover

b = pcbnew.NewBoard(OUT)
b.GetDesignSettings().SetBoardThickness(MM(1.6))
A = lambda x, y: pcbnew.VECTOR2I(MM(x), MM(y))

def seg(p, q, layer, w=0.1):
    s = pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetLayer(layer)
    s.SetStart(A(*p)); s.SetEnd(A(*q)); s.SetWidth(MM(w)); b.Add(s)
def arc(c, r, a0, a1, layer, w):
    """arc around c from angle a0 to a1 (degrees, y down)"""
    pt = lambda a: (c[0] + r * math.cos(math.radians(a)), c[1] + r * math.sin(math.radians(a)))
    s = pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_ARC); s.SetLayer(layer); s.SetWidth(MM(w))
    s.SetArcGeometry(A(*pt(a0)), A(*pt((a0 + a1) / 2)), A(*pt(a1))); b.Add(s)
def circle(c, r, layer, w=0.15, fill=False):
    s = pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_CIRCLE); s.SetLayer(layer); s.SetFilled(fill)
    s.SetStart(A(*c)); s.SetEnd(A(c[0] + r, c[1])); s.SetWidth(MM(w)); b.Add(s)
def rect(x0, y0, x1, y1, layer, w=0.15, fill=False):
    s = pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_RECT); s.SetLayer(layer); s.SetFilled(fill)
    s.SetStart(A(x0, y0)); s.SetEnd(A(x1, y1)); s.SetWidth(MM(w)); b.Add(s)
def text(t, x, y, h, layer=pcbnew.F_SilkS, bold=False):
    s = pcbnew.PCB_TEXT(b); s.SetText(t); s.SetPosition(A(x, y)); s.SetLayer(layer)
    s.SetTextSize(pcbnew.VECTOR2I(MM(h), MM(h))); s.SetTextThickness(MM(h * (0.2 if bold else 0.15))); b.Add(s)
def npth(x, y, d=2.2):
    f = pcbnew.FOOTPRINT(b); f.SetPosition(A(x, y)); f.SetReference('H'); f.Reference().SetVisible(False)
    f.SetBoardOnly(True); f.SetExcludedFromBOM(True); f.SetExcludedFromPosFiles(True)
    p = pcbnew.PAD(f); p.SetAttribute(pcbnew.PAD_ATTRIB_NPTH); p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    p.SetSize(pcbnew.VECTOR2I(MM(d), MM(d))); p.SetDrillSize(pcbnew.VECTOR2I(MM(d), MM(d)))
    p.SetLayerSet(pcbnew.LSET.AllCuMask()); p.SetPosition(A(x, y)); f.Add(p); b.Add(f)

# ---------------- rear cover: mirrored tree outline (outer face = F side)
ol = main.outline()                     # in absolute coords (main.OX/OY offset)
o = ol.Outline(0)
mx = lambda x: 2 * main.OX - x          # mirror about the tree's centre line
pts = [(mx(o.CPoint(i).x / 1e6), o.CPoint(i).y / 1e6) for i in range(o.PointCount())]
for p, q in zip(pts, pts[1:] + pts[:1]): seg(p, q, pcbnew.Edge_Cuts)
for hx, hy in main.HOLES: npth(main.OX - hx, main.OY + hy)
X = lambda x: main.OX + x * main.SC     # cover-face coordinates (rev B size, scaled like the tree): x right as seen from behind
Y = lambda y: main.OY + y * main.SC
SILK = pcbnew.F_SilkS

text('NeonPine', X(0), Y(36.0), 3.0, bold=True)
text('NP-1  rev B', X(0), Y(40.0), 1.5)
text('5 V DC  0.15 A  via USB-C', X(0), Y(44.0), 1.3)
text('INDOOR USE ONLY - NOT A TOY - 14+', X(0), Y(47.0), 1.0)
text('DO NOT OPEN: 110 V INSIDE.', X(0), Y(49.2), 1.0)
text('No user-serviceable parts.', X(0), Y(51.2), 1.0)
text('[Company] [street] [city] [country]', X(0), Y(58.0), 0.9)
text('[support e-mail]  -  Made in [country]', X(0), Y(59.8), 0.9)
# serial number field (white box for a printed sticker or laser marking)
rect(X(-8), Y(61.5), X(8), Y(64.5), SILK, 0.15)
text('S/N', X(-10.2), Y(63.0), 1.0)
# CE mark: two arcs of a circle (height 6 mm), E with a shorter middle bar
H = 6.0; r = H / 2 - 0.35; cy = Y(53.5); cx = X(-18.0)
arc((cx, cy), r, 60, 300, SILK, 0.7)
ex = cx + H * 0.93
arc((ex, cy), r, 60, 300, SILK, 0.7)
seg((ex - r, cy), (ex + r * 0.55, cy), SILK, 0.7)
# WEEE crossed-out wheeled bin + bar (EN 50419)
wx, wy = X(16.6), Y(49.6)
seg((wx - 1.9, wy), (wx + 1.9, wy), SILK, 0.3)                                   # lid
seg((wx - 0.6, wy - 0.5), (wx + 0.6, wy - 0.5), SILK, 0.3)                       # handle
for p, q in [((wx - 1.7, wy + 0.3), (wx - 1.3, wy + 4.6)), ((wx + 1.7, wy + 0.3), (wx + 1.3, wy + 4.6)),
             ((wx - 1.3, wy + 4.6), (wx + 1.3, wy + 4.6))]: seg(p, q, SILK, 0.3)  # bin
circle((wx - 0.9, wy + 5.1), 0.35, SILK, 0.2); circle((wx + 0.9, wy + 5.1), 0.35, SILK, 0.2)
seg((wx - 2.4, wy - 0.7), (wx + 2.4, wy + 5.6), SILK, 0.35); seg((wx + 2.4, wy - 0.7), (wx - 2.4, wy + 5.6), SILK, 0.35)
rect(wx - 2.2, wy + 6.2, wx + 2.2, wy + 7.0, SILK, 0.1, fill=True)                 # bar: placed on the market after 2005

# ---------------- stand base plate (drawn below the cover)
W2, D0, D1 = 25.0, -10.0, 16.0          # half width, front edge, back edge (y = depth, tree plate at 0, cover at +6.6)
def rrect(x0, y0, x1, y1, r):
    c = [(x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)]
    pts = []
    for cx_, cy_, a in c:
        pts += [(cx_ + r * math.cos(math.radians(a + k * 10)), cy_ + r * math.sin(math.radians(a + k * 10))) for k in range(10)]
    return pts
base = rrect(BX - W2, BY + D0, BX + W2, BY + D1, 2.0)
for p, q in zip(base, base[1:] + base[:1]): seg(p, q, pcbnew.Edge_Cuts)
for tx, tw in main.TABS:
    for depth in (0.0, PITCH):          # tree tab slot, cover tab slot (cover is behind the tree, mirrored -> same x as seen from the front)
        sl = rrect(BX + tx - tw / 2 - 0.1, BY + depth - 0.85, BX + tx + tw / 2 + 0.1, BY + depth + 0.85, 0.5)
        for p, q in zip(sl, sl[1:] + sl[:1]): seg(p, q, pcbnew.Edge_Cuts)
text('NeonPine stand  -  FRONT (lamp side)', BX, BY + D0 + 2.2, 1.2)
seg((BX - 2, BY + D0 + 4.2), (BX, BY + D0 + 3.4), SILK, 0.2); seg((BX + 2, BY + D0 + 4.2), (BX, BY + D0 + 3.4), SILK, 0.2)
text('tree', BX - 18, BY - 2.0, 1.0); text('cover', BX - 18, BY + PITCH + 2.2, 1.0)
text('Glue or press-fit the tabs. Rev B.', BX, BY + D1 - 2.0, 0.9)

pcbnew.SaveBoard(OUT, b)
print('wrote', OUT)
