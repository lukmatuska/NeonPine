#!/usr/bin/env python3
"""Route the open connections of a few nets with Freerouting, keeping every existing track and via where it is (exported as
fixed wires), then refill the zones. Used after tools/usb_rework.py.
Freerouting has no net filter, and it does not accept the existing SOT-363 fan-outs (custom 0.2 mm rule) or the pour-only GND
as routed, so every net that is not listed loses its pin list in the DSN: its pads and wires stay as obstacles only.
Usage: python3 tools/route_local.py <freerouting-2.4.1.jar> <passes> <net> [<net> ...]   (net names without the leading '/')"""
import sys, os, re, subprocess
import pcbnew

PRJ = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
PCB = os.path.join(PRJ, 'NeonPine.kicad_pcb')
jar, passes, nets = sys.argv[1], sys.argv[2], set(sys.argv[3:])
dsn, ses = PCB.replace('.kicad_pcb', '.dsn'), PCB.replace('.kicad_pcb', '.ses')
seq = lambda c: [c[i] for i in range(len(c))]

b = pcbnew.LoadBoard(PCB)
b.SynchronizeNetsAndNetClasses(True)
locked = set()
for t in seq(b.Tracks()):
    if t.IsLocked(): locked.add(t.m_Uuid.AsString())
    t.SetLocked(True)
zones = seq(b.Zones())
for z in zones: b.Remove(z)
assert pcbnew.ExportSpecctraDSN(b, dsn), 'DSN export failed'
txt = open(dsn).read()            # HVBUS: B.Cu only (see route.py)
i = txt.find('(class HVBUS'); j = txt.find('(circuit', i)
txt = txt[:j] + '(circuit\n        (use_layer B.Cu)' + txt[j + len('(circuit'):]
keep = lambda m: m.group(0) if m.group(1).strip('"').lstrip('/') in nets else '(net %s' % m.group(1)
txt = re.sub(r'\(net ("[^"]+"|[^\s()]+)\s*\(pins [^)]*\)', keep, txt)
if os.environ.get('KEEP_DSN'): open(dsn + '.filtered', 'w').write(txt)
open(dsn, 'w').write(txt)
if os.environ.get('DRY'): sys.stdout.flush(); os._exit(0)
subprocess.run(['java', '-jar', jar, '-de', dsn, '-do', ses, '-mp', passes, '--gui.enabled=false'], check=True)
assert pcbnew.ImportSpecctraSES(b, ses), 'SES import failed'
for t in seq(b.Tracks()):
    t.SetLocked(t.m_Uuid.AsString() in locked)
for z in zones: b.Add(z)
pcbnew.SaveBoard(PCB, b)
b = pcbnew.LoadBoard(PCB); b.SynchronizeNetsAndNetClasses(True); b.BuildConnectivity()
pcbnew.ZONE_FILLER(b).Fill(seq(b.Zones()))
pcbnew.SaveBoard(PCB, b)
for f in (dsn, ses): os.remove(f)
sys.stdout.flush(); os._exit(0)
