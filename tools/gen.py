import uuid, os, copy
from sx import *
_c=[0]
def U():
    _c[0]+=1; return str(uuid.uuid5(uuid.NAMESPACE_URL,'neonpine/%d'%_c[0]))
ROOT='f460b743-0f84-4eb6-8cd0-caf2149a2015'
FPDIR='/usr/share/kicad/footprints/'
R06='Resistor_SMD:R_0603_1608Metric'; R12='Resistor_SMD:R_1206_3216Metric'
C06='Capacitor_SMD:C_0603_1608Metric'
parts=[]  # (ref,lib,name,x,y,value,fp,{pin:net},dnp)
def P(ref,lib,name,x,y,val,fp,nets,dnp=False): parts.append((ref,lib,name,x,y,val,fp,nets,dnp))
# --- power in
P('J1','Connector','USB_C_Receptacle_PowerOnly_6P',35.56,55.88,'USB-C 6P (USB4125-GF-A)','Connector_USB:USB_C_Receptacle_GCT_USB4125-xx-x_6P_TopMnt_Horizontal',
  {'A9':'VBUS','B9':'VBUS','A5':'CC1','B5':'CC2','A12':'GND','B12':'GND','SH':'GND'})
P('R3','Device','R',60.96,68.58,'5k1',R06,{'1':'CC1','2':'GND'})
P('R4','Device','R',68.58,68.58,'5k1',R06,{'1':'CC2','2':'GND'})
P('F1','Device','Polyfuse',76.2,45.72,'PTC 0.5A (MF-NSMF050-2)','Fuse:Fuse_1206_3216Metric',{'1':'VBUS_F','2':'VBUS'})
P('FB1','Device','FerriteBead_Small',83.82,68.58,'600R@100MHz','Inductor_SMD:L_0603_1608Metric',{'1':'VBUS_F','2':'+5V'})
P('D3','Device','D_Zener',50.8,76.2,'SMF5.0A (TVS)','Diode_SMD:D_SOD-123F',{'1':'VBUS','2':'GND'})
P('C1','Device','C',91.44,48.26,'10u',C06,{'1':'+5V','2':'GND'})
P('C2','Device','C',104.14,48.26,'100n',C06,{'1':'+5V','2':'GND'})
P('#FLG01','power','PWR_FLAG',86.36,35.56,'PWR_FLAG','',{'1':'+5V'})
P('#FLG02','power','PWR_FLAG',35.56,83.82,'PWR_FLAG','',{'1':'GND'})
# --- boost
P('C3','Device','C',121.92,48.26,'22u 10V','Capacitor_SMD:C_0805_2012Metric',{'1':'+5V','2':'GND'})
P('L11','Device','L',134.62,40.64,'330u (SWPA6028S331MT, Isat>=0.4A)','NeonPine:L_6.3x6.3_H3',{'1':'+5V','2':'SW'})
P('D1','Device','D',152.4,33.02,'ES1D','Diode_SMD:D_SMA',{'2':'SW','1':'HV+'})
P('Q1','Transistor_FET','Q_NMOS_GDS',144.78,58.42,'DMN15H310SE','Package_TO_SOT_SMD:SOT-223-3_TabPin2',{'1':'GATE','2':'SW','3':'GND'})
P('R1','Device','R',129.54,68.58,'47',R06,{'1':'GATE_DRV','2':'GATE'})
P('R2','Device','R',137.16,68.58,'100k',R06,{'1':'GATE','2':'GND'})
P('C4','Device','C',170.18,48.26,'1u 250V','Capacitor_SMD:C_1210_3225Metric',{'1':'HV+','2':'GND'})
P('D2','Device','D_Zener',185.42,48.26,'SMAJ100A','Diode_SMD:D_SMA',{'1':'HV+','2':'GND'})
P('R12','Device','R',228.6,40.64,'100 (snubber)','Resistor_SMD:R_0805_2012Metric',{'1':'SW','2':'SNUB'},dnp=True)
P('C8','Device','C',228.6,53.34,'100p C0G 250V','Capacitor_SMD:C_0805_2012Metric',{'1':'SNUB','2':'GND'},dnp=True)
P('R5','Device','R',208.28,40.64,'1M',R06,{'1':'HV+','2':'FB_MID'})
P('R6','Device','R',208.28,53.34,'1M',R06,{'1':'FB_MID','2':'VFB'})
P('R7','Device','R',208.28,66.04,'39k',R06,{'1':'VFB','2':'GND'})
P('C5','Device','C',218.44,66.04,'10n',C06,{'1':'VFB','2':'GND'})
# --- MCU. Lamp -> pin map (PC0-7 = pins 10-17, PD0 = 8, PD4 = 1) comes from tools/pinswap.py when present
_lp=os.path.join(os.path.dirname(os.path.abspath(__file__)),'lamp_pins.json')
import json
LAMP_PINS=json.load(open(_lp)) if os.path.exists(_lp) else {'10':'LAMP1','11':'LAMP2','12':'LAMP3','13':'LAMP4','14':'LAMP5',
  '15':'LAMP6','16':'LAMP7','17':'LAMP8','8':'LAMP9','1':'LAMP10'}
# --- MCU
P('U1','MCU_WCH_RiscV','CH32V003FxPx',60.96,121.92,'CH32V003F4P6','Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm',
  {**LAMP_PINS, '18':'SWIO','19':'GATE_DRV','20':'VFB','2':'LDR','4':'NRST',
   '5':'BUZZ','6':'TOUCH2','9':'+5V','7':'GND'})
P('C6','Device','C',101.6,106.68,'100n',C06,{'1':'+5V','2':'GND'})
P('C7','Device','C',101.6,129.54,'100n',C06,{'1':'NRST','2':'GND'})
P('J2','Connector_Generic','Conn_01x03',101.6,149.86,'SWD pogo pads','NeonPine:Pogo_1x03_P2.54mm',
  {'1':'+5V','2':'SWIO','3':'GND'})
# --- inputs
P('Q2','Device','Q_Photo_NPN',137.16,111.76,'TEPT4400','LED_THT:LED_D3.0mm',{'1':'+5V','2':'LDR'})
P('R9','Device','R',137.16,127,'22k',R06,{'1':'LDR','2':'GND'})
P('TP2','Connector','TestPoint',175.26,111.76,'Touch trunk','NeonPine:TouchPad_D4.0mm_Masked',{'1':'TP_TRUNK'})
P('R11','Device','R',175.26,124.46,'1k',R06,{'1':'TP_TRUNK','2':'TOUCH2'})
P('TP3','Connector','TestPoint',198.12,111.76,'BUZZ/spare','TestPoint:TestPoint_Pad_1.5x1.5mm',{'1':'BUZZ'})
# --- lamps
for n in range(1,11):
    x=27.94+(n-1)*25.4; y0=190.5
    P(f'R{20+n}','Device','R',x,y0,'150k','Resistor_SMD:R_0805_2012Metric',{'1':'HV+','2':f'A{n}'})
    P(f'LA{n}','Device','Lamp_Neon',x,y0+3.81+5.08+2.54,'NEON-3','NeonPine:Lamp_Neon_Brightmaster_NEON-3_D4x10_P3.0',{'2':f'A{n}','1':f'K{n}'})
    P(f'Q{10+n}','Transistor_BJT','Q_NPN_BEC',x-2.54,y0+3.81+5.08+2.54+5.08+2.54+5.08,'MMBTA42','Package_TO_SOT_SMD:SOT-23',{'3':f'K{n}','2':'GND','1':f'B{n}'})
    P(f'R{40+n}','Device','R',x-12.7,y0+33.02,'22k',R06,{'1':f'LAMP{n}','2':f'B{n}'})

notes=[(25.4,25.4,'POWER IN – USB-C 5V, TVS D3, PTC F1, ferrite FB1'),(119.38,25.4,'HV BOOST 75–100 V (MCU-controlled, TIM1 30 kHz)'),
 (25.4,96.52,'MCU CH32V003F4P6 (runs at 5 V)'),(132.08,96.52,'INPUTS – LDR, TKEY touch pads, spare pad'),
 (25.4,177.8,'NEON LAMPS – Brightmaster NEON-3 (4x10, strike ≤90 VDC, ~60 V settled): I = (V_HV - 60 V)/150k ≈ 0.1–0.3 mA, MMBTA42 low-side switches'),
 (119.38,81.28,'Q1 DMN15H310SE: 150 V, 0.33 Ω @ Vgs=5 V. R2 keeps boost off during reset.'),
 (119.38,85.09,'D2 = hard OVP clamp (Vbr 111–123 V). R12/C8 snubber: optional (DNP).')]

for ref,lib,name,*_ ,fp,nets,dnp in [(p[0],p[1],p[2],p[3],p[4],p[5],p[6],p[7],p[8]) for p in parts]:
    if fp and not ref.startswith('#'):
        l,f=fp.split(':'); assert os.path.exists((FPDIR if l!='NeonPine' else '/home/lcrm/Documents/EDA/KTE/VanocniStromek/NeonPine/')+f'{l}.pretty/{f}.kicad_mod'),fp
# ---- build
syms={}; out=[]; wires=[]; labels=[]; pwr=[]
def eff(hide=False,just=None):
    e=['effects',['font',['size','1.27','1.27']]]
    if just: e.append(['justify',just])
    if hide: e.append(['hide','yes'])
    return e
def prop(k,v,x,y,hide=False,just=None): return ['property',f'"{k}"',f'"{v}"',['at',f'{x:g}',f'{y:g}','0'],eff(hide,just)]
pinpos={}  # net -> list of (x,y,outdir)
npw=0
def place(ref,lib,name,x,y,val,fp,nets,dnp,power=False,rot=0):
    lid=f'{lib}:{name}'
    if lid not in syms:
        s=copy.deepcopy(getsym(lib,name)); s[1]=f'"{lid}"'; syms[lid]=s
    s=syms[lid]
    sym=['symbol',['lib_id',f'"{lid}"'],['at',f'{x:g}',f'{y:g}',str(rot)],['unit','1'],['exclude_from_sim','no'],
         ['in_bom','no' if power else 'yes'],['on_board','no' if power else 'yes'],['dnp','yes' if dnp else 'no'],['uuid',f'"{U()}"']]
    if power:
        sym+= [prop('Reference',ref,x,y+3.81,True),prop('Value',val,x,y-3.81 if name!='GND' else y+3.81)]
    else:
        sym+= [prop('Reference',ref,x+5.08,y-1.27-(20.32 if ref=='U1' else 0),just='left'),prop('Value',val,x+5.08,y+1.27-(20.32 if ref=='U1' else 0),just='left')]
    sym+= [prop('Footprint',fp,x,y,True),prop('Datasheet','~',x,y,True),prop('Description','',x,y,True)]
    for no,nm,px,py,a in pins(getsym(lib,name)):
        sym.append(['pin',f'"{no}"',['uuid',f'"{U()}"']])
        if no in nets:
            import math
            d=(-round(math.cos(math.radians(a))),round(math.sin(math.radians(a))))
            pinpos.setdefault(nets[no],[]).append((round(x+px,2),round(y-py,2),d))
    sym.append(['instances',['project','"NeonPine"',['path',f'"/{ROOT}"',['reference',f'"{ref}"'],['unit','1']]]])
    out.append(sym)
for p in parts: place(*p,power=p[0].startswith('#'))
def wire(a,b): wires.append(['wire',['pts',['xy',f'{a[0]:g}',f'{a[1]:g}'],['xy',f'{b[0]:g}',f'{b[1]:g}']],['stroke',['width','0'],['type','default']],['uuid',f'"{U()}"']])
for net,pl in pinpos.items():
    pl=list(dict.fromkeys(pl))
    if len(pl)==2 and pl[0][0]==pl[1][0] and net not in ('GND','+5V'):
        wire(pl[0][:2],pl[1][:2]); continue
    for x,y,d in pl:
        e=(round(x+d[0]*2.54,2),round(y+d[1]*2.54,2)); wire((x,y),e)
        if net in ('GND','+5V'):
            npw+=1
            if net=='GND': rot={(0,1):0,(0,-1):180,(1,0):90,(-1,0):270}[d]
            else: rot={(0,-1):0,(0,1):180,(-1,0):90,(1,0):270}[d]
            place(f'#PWR{npw:03d}','power',net,e[0],e[1],net,'',{},False,power=True,rot=rot)
        else:
            ang={(1,0):0,(-1,0):180,(0,-1):90,(0,1):270}[d]
            labels.append(['label',f'"{net}"',['at',f'{e[0]:g}',f'{e[1]:g}',str(ang)],['effects',['font',['size','1.27','1.27']],['justify','right' if ang in (180,270) else 'left','bottom']],['uuid',f'"{U()}"']])
texts=[['text',f'"{t}"',['exclude_from_sim','no'],['at',f'{x:g}',f'{y:g}','0'],['effects',['font',['size','2' if t.isupper() or '–' in t[:20] else '1.27','2' if t.isupper() or '–' in t[:20] else '1.27']],['justify','left','bottom']],['uuid',f'"{U()}"']] for x,y,t in notes]
sch=['kicad_sch',['version','20260306'],['generator','"eeschema"'],['generator_version','"10.0"'],['uuid',f'"{ROOT}"'],['paper','"A3"'],
     ['title_block',['title','"NeonPine – neon Christmas tree night light"'],['date','"2026-10-05"'],['rev','"B"']],
     ['lib_symbols']+list(syms.values())]+texts+wires+labels+out+[['sheet_instances',['path','"/"',['page','"1"']]],['embedded_fonts','no']]
open('/home/lcrm/Documents/EDA/KTE/VanocniStromek/NeonPine/NeonPine.kicad_sch','w').write(dump(sch)+'\n')
print(len(parts),'parts', npw,'pwr', len(labels),'labels')
