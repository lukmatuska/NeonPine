#!/usr/bin/env python3
"""Autoroute NeonPine.kicad_pcb with Freerouting, then refill zones.
Usage: python3 tools/route.py <freerouting.jar> [passes] [--keep]
  --keep  start from the existing tracks (finish an almost-complete board) instead of routing from scratch"""
import sys, os, subprocess
import pcbnew

PRJ = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
PCB = os.path.join(PRJ, 'NeonPine.kicad_pcb')
keep = '--keep' in sys.argv
args = [a for a in sys.argv[1:] if a != '--keep']
jar, passes = args[0], (args[1] if len(args) > 1 else '40')
dsn, ses = PCB.replace('.kicad_pcb', '.dsn'), PCB.replace('.kicad_pcb', '.ses')

b = pcbnew.LoadBoard(PCB)
b.SynchronizeNetsAndNetClasses(True)        # apply the .kicad_pro netclass patterns (HV clearance!) before export
seq = lambda c: [c[i] for i in range(len(c))]   # SWIG iterators are broken on Python 3.14
if not keep:
    for t in seq(b.Tracks()): b.Remove(t)
zones = seq(b.Zones())
for z in zones: b.Remove(z)                    # pours would be exported as blocking planes
assert pcbnew.ExportSpecctraDSN(b, dsn), 'DSN export failed'
# HVBUS (the unlimited 105 V supply) may only use the back copper: it must stay under the rear cover
txt = open(dsn).read()
i = txt.find('(class HVBUS')
assert i >= 0, 'HVBUS class missing in DSN'
j = txt.find('(circuit', i)
txt = txt[:j] + '(circuit\n        (use_layer B.Cu)' + txt[j + len('(circuit'):]
open(dsn, 'w').write(txt)
subprocess.run(['java', '-jar', jar, '-de', dsn, '-do', ses, '-mp', passes, '--gui.enabled=false'], check=True)
assert pcbnew.ImportSpecctraSES(b, ses), 'SES import failed'
for z in zones: b.Add(z)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
pcbnew.SaveBoard(PCB, b)
for f in (dsn, ses): os.remove(f)
print('routed:', len(b.Tracks()), 'track items')
