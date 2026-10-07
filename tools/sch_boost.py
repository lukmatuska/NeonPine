#!/usr/bin/env python3
"""Draw the HV boost section of NeonPine.kicad_sch with real wires (gen.py only writes label stubs).
Removes gen.py's stubs, labels and power symbols on the boost parts, moves the parts into a clean layout
and wires +5V -> L11 -> SW -> D1 -> HV+, the gate drive, the snubber, the divider and one GND return rail.
Net names stay the same (SW, GATE, GATE_DRV, HV+, VFB labels; SNUB and FB_MID stay unnamed).
Usage: python3 tools/sch_boost.py   (run right after tools/gen.py)"""
import sys, os, uuid, copy, math
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE); from sx import *
F=os.path.join(HERE,'..','NeonPine.kicad_sch')
T=parse(open(F).read())[0]
ROOT='f460b743-0f84-4eb6-8cd0-caf2149a2015'
def U(): return str(uuid.uuid4())
def g(e,k): 
    for x in e:
        if isinstance(x,list) and x[0]==k: return x
def ref(sym):
    for x in sym:
        if isinstance(x,list) and x[0]=='property' and x[1]=='"Reference"': return x[2].strip('"')
B=['C3','L11','D1','Q1','R1','R2','C4','D2','R12','C8','R5','R6','R7','C5']
syms={ref(e):e for e in T if isinstance(e,list) and e[0]=='symbol'}
libs={e[1].strip('"'):e for e in g(T,'lib_symbols')[1:]}
def pinxy(s):
    at=g(s,'at'); x,y,r=float(at[1]),float(at[2]),float(at[3]) if len(at)>3 else 0
    lid=g(s,'lib_id')[1].strip('"'); out={}
    for no,nm,px,py,a in pins(libs[lid]):
        c,sn=round(math.cos(math.radians(r))),round(math.sin(math.radians(r)))
        qx,qy=px*c-py*sn,px*sn+py*c
        out[no]=(round(x+qx,2),round(y-qy,2))
    return out
# --- 1. remove old stubs / labels / power symbols / junctions attached to boost pins
old=set(p for r in B for p in pinxy(syms[r]).values())
def pts(w): return [(round(float(p[1]),2),round(float(p[2]),2)) for p in g(w,'pts')[1:]]
kill=set(); ends=set()
for e in T:
    if isinstance(e,list) and e[0]=='wire':
        p=pts(e)
        if any(q in old for q in p): kill.add(id(e)); ends.update(p)
for e in T:
    if not isinstance(e,list): continue
    if e[0] in ('label','junction'):
        at=g(e,'at'); 
        if (round(float(at[1]),2),round(float(at[2]),2)) in ends: kill.add(id(e))
    if e[0]=='symbol' and ref(e).startswith('#PWR'):
        at=g(e,'at')
        if (round(float(at[1]),2),round(float(at[2]),2)) in ends: kill.add(id(e))
print('removed',len(kill))
T[:]=[e for e in T if id(e) not in kill]
# --- 2. move / rotate parts
def setprop(s,k,x,y,just=None,ang=0):
    for p in s:
        if isinstance(p,list) and p[0]=='property' and p[1]==f'"{k}"':
            p[3]=['at',f'{x:g}',f'{y:g}',str(ang)]
            eff=g(p,'effects'); eff[:]=[z for z in eff if not (isinstance(z,list) and z[0]=='justify')]
            if just: eff.append(['justify',just])
def mv(r,x,y,rot=0,props=None):
    s=syms[r]; s[s.index(g(s,'at'))]=['at',f'{x:g}',f'{y:g}',str(rot)]
    if props: (rx,ry,vx,vy,j)=props
    else: rx,ry,vx,vy,j=x+5.08,y-1.27,x+5.08,y+1.27,'left'
    a=90 if rot in (90,270) else 0
    setprop(s,'Reference',rx,ry,j,a); setprop(s,'Value',vx,vy,j,a)
    for k in ('Footprint','Datasheet','Description'): setprop(s,k,x,y)
R=33.02; G=73.66
mv('C3',121.92,40.64)
mv('L11',134.62,R,90,(134.62,27.94,134.62,30.48,None))
mv('D1',158.75,R,180,(158.75,27.94,158.75,30.48,None))
mv('R1',125.73,58.42,90,(125.73,54.61,125.73,62.23,None))
mv('R2',137.16,66.04)
mv('Q1',144.78,58.42)
mv('R12',170.18,46.99); mv('C8',170.18,58.42)
mv('C4',195.58,40.64)
mv('D2',213.36,40.64,270,(218.44,39.37,218.44,41.91,'left'))
mv('R5',236.22,40.64); mv('R6',236.22,53.34); mv('R7',236.22,66.04); mv('C5',248.92,66.04)
P={r:pinxy(syms[r]) for r in B}
for r in B: print(r,P[r])
# --- 3. new wiring
new=[]
def W(*ps):
    for a,b in zip(ps,ps[1:]):
        new.append(['wire',['pts',['xy',f'{a[0]:g}',f'{a[1]:g}'],['xy',f'{b[0]:g}',f'{b[1]:g}']],['stroke',['width','0'],['type','default']],['uuid',f'"{U()}"']])
def J(x,y): new.append(['junction',['at',f'{x:g}',f'{y:g}'],['diameter','0'],['color','0','0','0','0'],['uuid',f'"{U()}"']])
def L(t,x,y,ang=0):
    new.append(['label',f'"{t}"',['at',f'{x:g}',f'{y:g}',str(ang)],['effects',['font',['size','1.27','1.27']],['justify','right' if ang in (180,270) else 'left','bottom']],['uuid',f'"{U()}"']])
tmpl=next(e for e in T if isinstance(e,list) and e[0]=='symbol' and g(e,'lib_id')[1]=='"power:GND"')
n=[100]
def PWR(net,x,y):
    s=copy.deepcopy(tmpl); n[0]+=1; r=f'#PWR{n[0]:03d}'
    s[1]=['lib_id',f'"power:{net}"']; s[s.index(g(s,'at'))]=['at',f'{x:g}',f'{y:g}','0']; s[s.index(g(s,'uuid'))]=['uuid',f'"{U()}"']
    for p in s:
        if isinstance(p,list) and p[0]=='property':
            if p[1]=='"Reference"': p[2]=f'"{r}"'; p[3]=['at',f'{x:g}',f'{y+3.81:g}','0']
            elif p[1]=='"Value"': p[2]=f'"{net}"'; p[3]=['at',f'{x:g}',f'{y+3.81 if net=="GND" else y-3.81:g}','0']
            else: p[3]=['at',f'{x:g}',f'{y:g}','0']
        if isinstance(p,list) and p[0]=='pin': p[2]=['uuid',f'"{U()}"']
    g(g(g(s,'instances'),'project'),'path')[2]=['reference',f'"{r}"']
    new.append(s)
# +5V rail
W((109.22,R),(121.92,R),P['L11']['1']); W((121.92,R),P['C3']['1']); J(121.92,R); PWR('+5V',109.22,R)
W(P['C3']['2'],(121.92,46.99)); PWR('GND',121.92,46.99)
# SW node
sx_=P['Q1']['2'][0]
W(P['L11']['2'],(sx_,R),P['D1']['2']); J(sx_,R); L('SW',148.59,R)
W((sx_,R),(sx_,43.18),P['Q1']['2']); J(sx_,43.18)
W((sx_,43.18),P['R12']['1'])
W(P['R12']['2'],P['C8']['1'])             # SNUB (stays unnamed)
# HV+ rail
xs=[P['C4']['1'][0],P['D2']['1'][0],P['R5']['1'][0]]
W(P['D1']['1'],*[(x,R) for x in xs],(256.54,R)); L('HV+',256.54,R)
for x,pn in zip(xs,[P['C4']['1'],P['D2']['1'],P['R5']['1']]): W((x,R),pn); J(x,R)
# divider
W(P['R5']['2'],P['R6']['1'])              # FB_MID (stays unnamed)
W(P['R6']['2'],(236.22,59.69),P['R7']['1']); J(236.22,59.69)
W((236.22,59.69),(248.92,59.69),(256.54,59.69)); W((248.92,59.69),P['C5']['1']); J(248.92,59.69); L('VFB',256.54,59.69)
# gate drive
W((119.38,58.42),P['R1']['1']); L('GATE_DRV',119.38,58.42,180)
W(P['R1']['2'],(137.16,58.42),P['Q1']['1']); W((137.16,58.42),P['R2']['1']); J(137.16,58.42); L('GATE',130.81,58.42)
# GND return rail
drops=[P['R2']['2'],P['Q1']['3'],P['C8']['2'],P['C4']['2'],P['D2']['2'],P['R7']['2'],P['C5']['2']]
W(*[(p[0],G) for p in drops])
for p in drops: W(p,(p[0],G))
for p in drops[1:-1]: J(p[0],G)
J(137.16,G); PWR('GND',137.16,G)
# insert before first symbol instance
i=next(k for k,e in enumerate(T) if isinstance(e,list) and e[0]=='symbol')
T[i:i]=new
open(F,'w').write(dump(T)+'\n')
