#!/usr/bin/env python3
"""3D model for L11: shielded SMD power inductor 6.3 x 6.3 x 3 mm (SWPA6030 / SRN6028 class) on the
Inductor_SMD:L_6.3x6.3_H3 land pattern (pads at x = +-2.75 mm).
Square ferrite shield with rounded corners, round top opening showing the drum core and the copper winding,
tinned terminals on the bottom wrapping up the two side faces.
Usage: freecadcmd tools/inductor3d.py
Model coords: origin = footprint origin, Z up from the copper (KiCad mirrors it for the back side)."""
import os, sys
import Part
from FreeCAD import Vector as V

HERE = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.path.join(os.getcwd(), 'tools')
sys.path.insert(0, HERE)
from model3d import save

NAME = 'L_6.3x6.3_H3'
W, H, Z0 = 6.3, 3.0, 0.1          # body size, height, stand-off above the copper (terminal thickness)
D_OPEN, D_CORE, RECESS = 5.2, 3.4, 0.35

body = Part.makeBox(W, W, H - Z0, V(-W / 2, -W / 2, Z0))
body = body.makeFillet(0.8, [e for e in body.Edges if abs(e.Vertexes[0].Point.z - e.Vertexes[1].Point.z) > 1e-6])
opening = Part.makeCylinder(D_OPEN / 2, RECESS + 0.01, V(0, 0, H - RECESS))
shield = body.cut(opening)
core = Part.makeCylinder(D_CORE / 2, RECESS - 0.05, V(0, 0, H - RECESS))   # drum core top, just below the rim
ferrite = shield.fuse(core).removeSplitter()
winding = Part.makeCylinder(D_OPEN / 2 - 0.05, 0.12, V(0, 0, H - RECESS)).cut(
          Part.makeCylinder(D_CORE / 2 + 0.05, 0.2, V(0, 0, H - RECESS - 0.05)))

term = None
for sx in (-1, 1):
    bottom = Part.makeBox(1.0, 2.2, Z0, V(-0.5 + sx * 2.65, -1.1, 0))
    side = Part.makeBox(0.1, 2.2, 0.9, V(sx * (W / 2) - (0.1 if sx < 0 else 0), -1.1, 0))
    t = bottom.fuse(side).removeSplitter()
    term = t if term is None else term.fuse(t)

save(NAME, [('ferrite', ferrite, (0.16, 0.16, 0.17), 0.0),
            ('winding', winding, (0.80, 0.45, 0.20), 0.0),
            ('terminals', term, (0.85, 0.85, 0.83), 0.0)], 'inductor3d.py')
