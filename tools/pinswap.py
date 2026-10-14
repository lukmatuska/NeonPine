#!/usr/bin/env python3
"""Lamp -> driver pin swap. The firmware drives lamps through lookup tables, so any lamp switch may use any driver pin.
  * cathode-side switches (base resistor R4n): the 8 MCU lamp pins (PC0-PC6 = pins 10..16, PD0 = pin 8); the two lamps left
    over go to shift-register outputs.
  * anode-side switches (base resistor R5n) and those left-over cathode switches: the 16 outputs of U2/U3 (74HC595).
NOTE: since the USB rework the board was hand-edited (LAMP10 -> U3 QE, LAMPA10 -> U3 QD); rerunning this rewrites that.
Reads the placed board, solves both assignments for the shortest straight-line base-resistor -> driver pin distance
(which also removes crossings) and writes tools/lamp_pins.json for gen.py.
Usage: python3 tools/pinswap.py"""
import os, json, math
import pcbnew
from scipy.optimize import linear_sum_assignment

HERE = os.path.dirname(os.path.abspath(__file__))
PINS = ['10', '11', '12', '13', '14', '15', '16', '8']   # PC7 (pin 17) = SR_CLK since the USB rework
SR = [(u, p) for u in ('U2', 'U3') for p in ('15', '1', '2', '3', '4', '5', '6', '7')]   # QA..QH of each
b = pcbnew.LoadBoard(os.path.join(HERE, '..', 'NeonPine.kicad_pcb'))
pos = lambda ref, pin: (lambda p: (p.x / 1e6, p.y / 1e6))(b.FindFootprintByReference(ref).FindPadByNumber(pin).GetPosition())
cost = [[math.dist(pos(f'R{40 + n}', '1'), pos('U1', p)) for p in PINS] for n in range(1, 11)]
rows, cols = linear_sum_assignment(cost)
mcu = {PINS[c]: f'LAMP{r + 1}' for r, c in zip(rows, cols)}
left = [n for n in range(1, 11) if n - 1 not in rows]
items = [(f'LAMPA{n}', f'R{50 + n}') for n in range(1, 11)] + [(f'LAMP{n}', f'R{40 + n}') for n in left]
cost2 = [[math.dist(pos(r, '1'), pos(u, p)) for u, p in SR] for _, r in items]
r2, c2 = linear_sum_assignment(cost2)
sr = [None] * len(SR)
for r, c in zip(r2, c2): sr[c] = items[r][0]
json.dump({'mcu': mcu, 'sr': sr}, open(os.path.join(HERE, 'lamp_pins.json'), 'w'), indent=1)
print('MCU lamp wiring %.0f mm, shift-register wiring %.0f mm' % (sum(cost[r][c] for r, c in zip(rows, cols)),
                                                                 sum(cost2[r][c] for r, c in zip(r2, c2))))
print(' '.join(f'{v}=pin{k}' for k, v in sorted(mcu.items(), key=lambda kv: int(kv[1][4:]))), '|',
      ' '.join(f'{n}={u}.{p}' for (u, p), n in zip(SR, sr) if n))
