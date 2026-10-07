#!/usr/bin/env python3
"""3D model of the Brightmaster NEON-3 lamp (Ø4 x 10 mm, both leads out of one end, 3.0 mm pitch),
lying flat on the board with its leads bent down into the two pads.
Writes NeonPine.3dshapes/<name>.step (mm, for MCAD export) and .wrl (coloured, 0.1" units, for the 3D viewer).
Usage: freecadcmd tools/lamp3d.py
Model coords: origin = footprint origin (centre between pads), +Y = footprint -Y (KiCad 3D convention), Z up from the top copper."""
import os, sys, math
import FreeCAD as App, Part
from FreeCAD import Vector as V

HERE = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.path.join(os.getcwd(), 'tools')
sys.path.insert(0, HERE)
from model3d import save
NAME = 'Lamp_Neon_Brightmaster_NEON-3_D4x10_P3.0'
R, ZC = 2.0, 2.05          # glass radius, tube axis height (lamp rests on the board)
Y0, Y1 = -1.0, -11.0       # glass from the seal end to the far tip (10 mm)
PITCH, RL = 3.0, 0.25      # pad pitch, lead radius (Ø0.5 mm)

def rod(a, b, r):
    d = b - a
    return Part.makeCylinder(r, d.Length, a, d)

def polyline(pts, r):
    s = rod(pts[0], pts[1], r)
    for a, b in zip(pts[1:], pts[2:]):
        s = s.fuse(Part.makeSphere(r, a)).fuse(rod(a, b, r))
    return s.removeSplitter()

# glass: tapered pinch seal, tube, round tip
ax = V(0, -1, 0)
seal = Part.makeCone(1.3, R, 0.8, V(0, Y0, ZC), ax)
tube = Part.makeCylinder(R, (Y0 - 0.8) - (Y1 + R), V(0, Y0 - 0.8, ZC), ax)
tip = Part.makeSphere(R, V(0, Y1 + R, ZC), ax, 0, 90, 360)   # hemisphere pointing along -Y
glass = seal.fuse(tube).fuse(tip).removeSplitter()

# electrodes: two parallel plates inside the glass, fed by thin internal wires
elec = None
for sx in (-1, 1):
    plate = Part.makeBox(0.15, 5.5, 0.9, V(sx * 0.5 - 0.075, -8.0, ZC - 0.45))
    wire = rod(V(sx * 0.5, -2.5, ZC), V(sx * 0.5, Y0 + 0.3, ZC), 0.12)
    p = plate.fuse(wire)
    elec = p if elec is None else elec.fuse(p)

# external leads: out of the seal, splay to the pads, bend down through the board
leads = None
for sx in (-1, 1):
    x = sx * PITCH / 2
    l = polyline([V(sx * 0.5, Y0 + 0.3, ZC), V(sx * 0.5, Y0 + 0.6, ZC), V(x, -0.2, ZC),
                  V(x, 0, ZC - 0.25), V(x, 0, -3.0)], RL)
    leads = l if leads is None else leads.fuse(l)

parts = [('glass', glass, (0.95, 0.88, 0.80), 0.75),    # clear glass, faint warm tint
         ('electrodes', elec, (0.45, 0.45, 0.48), 0.0),
         ('leads', leads, (0.82, 0.82, 0.80), 0.0)]

save(NAME, parts, 'lamp3d.py')
