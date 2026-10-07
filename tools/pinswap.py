#!/usr/bin/env python3
"""Lamp -> MCU pin swap. The firmware drives lamps through a lookup table, so any lamp may use any of the
10 lamp pins (PC0-PC7 = pins 10..17, PD0 = pin 8, PD4 = pin 1). Reads the placed board and solves the
assignment that minimises the straight-line R_Bn -> U1 pin distance (which also removes crossings),
then writes tools/lamp_pins.json for gen.py.
Usage: python3 tools/pinswap.py"""
import os, json, math
import pcbnew
from scipy.optimize import linear_sum_assignment

HERE = os.path.dirname(os.path.abspath(__file__))
PINS = ['10', '11', '12', '13', '14', '15', '16', '17', '8', '1']
b = pcbnew.LoadBoard(os.path.join(HERE, '..', 'NeonPine.kicad_pcb'))
pos = lambda ref, pin: (lambda p: (p.x / 1e6, p.y / 1e6))(b.FindFootprintByReference(ref).FindPadByNumber(pin).GetPosition())
cost = [[math.dist(pos(f'R{40 + n}', '1'), pos('U1', p)) for p in PINS] for n in range(1, 11)]
before = sum(cost[n][n] for n in range(10))
rows, cols = linear_sum_assignment(cost)
m = {PINS[c]: f'LAMP{r + 1}' for r, c in zip(rows, cols)}
json.dump(m, open(os.path.join(HERE, 'lamp_pins.json'), 'w'), indent=1)
print('lamp wiring %.0f mm -> %.0f mm' % (before, sum(cost[r][c] for r, c in zip(rows, cols))))
print(' '.join(f'{v}=pin{k}' for k, v in sorted(m.items(), key=lambda kv: int(kv[1][4:]))))
