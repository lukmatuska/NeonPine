import uuid, os, copy
from sx import *
_c=[0]
def U():
    _c[0]+=1; return str(uuid.uuid5(uuid.NAMESPACE_URL,'neonpine/%d'%_c[0]))
ROOT='f460b743-0f84-4eb6-8cd0-caf2149a2015'
FPDIR='/usr/share/kicad/footprints/'
PRJ=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..')
R06='Resistor_SMD:R_0603_1608Metric'; R12='Resistor_SMD:R_1206_3216Metric'
C06='Capacitor_SMD:C_0603_1608Metric'
R04='Resistor_SMD:R_0402_1005Metric'; C04='Capacitor_SMD:C_0402_1005Metric'   # low-voltage passives (0402: 50 V max)
parts=[]  # (ref,lib,name,x,y,value,fp,{pin:net},dnp,unit)
# BOM fields (JLCPCB/LCSC upload): manufacturer part numbers, descriptions, pad-only parts kept out of the BOM
MPN={'D2': 'SMF100A', 'D3': 'SMF5.0A', 'F1': 'MF-NSMF050-2', 'J1': 'USB4125-GF-A', 'L11': 'SWPA6028S331MT', 'LA1': 'NEON-3', 'LA2': 'NEON-3', 'LA3': 'NEON-3', 'LA4': 'NEON-3', 'LA5': 'NEON-3', 'LA6': 'NEON-3', 'LA7': 'NEON-3', 'LA8': 'NEON-3', 'LA9': 'NEON-3', 'LA10': 'NEON-3', 'Q1': 'DMN15H310SE', 'Q2': 'TEPT4400', 'Q11': 'MMDT5551(RANGE:100-300)', 'Q12': 'MMDT5551(RANGE:100-300)', 'Q13': 'MMDT5551(RANGE:100-300)', 'Q14': 'MMDT5551(RANGE:100-300)', 'Q15': 'MMDT5551(RANGE:100-300)', 'Q16': 'MMDT5551(RANGE:100-300)', 'Q17': 'MMDT5551(RANGE:100-300)', 'Q18': 'MMDT5551(RANGE:100-300)', 'Q19': 'MMDT5551(RANGE:100-300)', 'Q20': 'MMDT5551(RANGE:100-300)', 'U1': 'CH32V003F4P6', 'U2': '74HC595BQ,115', 'U3': '74HC595BQ,115'}
DESC={'C1': 'MLCC X5R/X7R, 10 V or more', 'C2': 'MLCC X7R, 16 V or more', 'C6': 'MLCC X7R, 16 V or more', 'C7': 'MLCC X7R, 16 V or more', 'C9': 'MLCC X7R, 16 V or more', 'C10': 'MLCC X7R, 16 V or more', 'C3': 'MLCC X5R/X7R', 'C4': 'MLCC X7R, HV rail bulk cap', 'C5': 'MLCC X7R, ADC filter', 'C8': 'Snubber cap, not fitted by default', 'D1': 'Boost rectifier, SOD-123F; part number not chosen yet', 'D2': 'TVS 100 V, HV rail clamp', 'D3': 'TVS 5 V, USB VBUS', 'F1': 'PTC resettable fuse 0.5 A hold', 'FB1': 'Ferrite bead', 'J1': 'USB-C power-only receptacle, 6 pin', 'L11': 'Shielded power inductor 6x6 mm, Isat >= 0.4 A', 'LA1': 'Brightmaster neon lamp (TME, not stocked at LCSC); hand-soldered', 'LA2': 'Brightmaster neon lamp (TME, not stocked at LCSC); hand-soldered', 'LA3': 'Brightmaster neon lamp (TME, not stocked at LCSC); hand-soldered', 'LA4': 'Brightmaster neon lamp (TME, not stocked at LCSC); hand-soldered', 'LA5': 'Brightmaster neon lamp (TME, not stocked at LCSC); hand-soldered', 'LA6': 'Brightmaster neon lamp (TME, not stocked at LCSC); hand-soldered', 'LA7': 'Brightmaster neon lamp (TME, not stocked at LCSC); hand-soldered', 'LA8': 'Brightmaster neon lamp (TME, not stocked at LCSC); hand-soldered', 'LA9': 'Brightmaster neon lamp (TME, not stocked at LCSC); hand-soldered', 'LA10': 'Brightmaster neon lamp (TME, not stocked at LCSC); hand-soldered', 'Q2': 'Ambient light phototransistor, THT', 'Q11': 'Dual NPN 160 V, JSCJ (pin-compatible with Diodes MMDT5551)', 'Q12': 'Dual NPN 160 V, JSCJ (pin-compatible with Diodes MMDT5551)', 'Q13': 'Dual NPN 160 V, JSCJ (pin-compatible with Diodes MMDT5551)', 'Q14': 'Dual NPN 160 V, JSCJ (pin-compatible with Diodes MMDT5551)', 'Q15': 'Dual NPN 160 V, JSCJ (pin-compatible with Diodes MMDT5551)', 'Q16': 'Dual NPN 160 V, JSCJ (pin-compatible with Diodes MMDT5551)', 'Q17': 'Dual NPN 160 V, JSCJ (pin-compatible with Diodes MMDT5551)', 'Q18': 'Dual NPN 160 V, JSCJ (pin-compatible with Diodes MMDT5551)', 'Q19': 'Dual NPN 160 V, JSCJ (pin-compatible with Diodes MMDT5551)', 'Q20': 'Dual NPN 160 V, JSCJ (pin-compatible with Diodes MMDT5551)', 'R12': 'Snubber, not fitted by default', 'R13': 'SPI clock series resistor', 'R21': 'Thick film, >= 200 V working voltage (e.g. RCV0603)', 'R22': 'Thick film, >= 200 V working voltage (e.g. RCV0603)', 'R23': 'Thick film, >= 200 V working voltage (e.g. RCV0603)', 'R24': 'Thick film, >= 200 V working voltage (e.g. RCV0603)', 'R25': 'Thick film, >= 200 V working voltage (e.g. RCV0603)', 'R26': 'Thick film, >= 200 V working voltage (e.g. RCV0603)', 'R27': 'Thick film, >= 200 V working voltage (e.g. RCV0603)', 'R28': 'Thick film, >= 200 V working voltage (e.g. RCV0603)', 'R29': 'Thick film, >= 200 V working voltage (e.g. RCV0603)', 'R30': 'Thick film, >= 200 V working voltage (e.g. RCV0603)', 'R31': 'Thick film, >= 200 V working voltage (e.g. RCV0603)', 'R32': 'Thick film, >= 200 V working voltage (e.g. RCV0603)', 'R33': 'Thick film, >= 200 V working voltage (e.g. RCV0603)', 'R34': 'Thick film, >= 200 V working voltage (e.g. RCV0603)', 'R35': 'Thick film, >= 200 V working voltage (e.g. RCV0603)', 'R36': 'Thick film, >= 200 V working voltage (e.g. RCV0603)', 'R37': 'Thick film, >= 200 V working voltage (e.g. RCV0603)', 'R38': 'Thick film, >= 200 V working voltage (e.g. RCV0603)', 'R39': 'Thick film, >= 200 V working voltage (e.g. RCV0603)', 'R40': 'Thick film, >= 200 V working voltage (e.g. RCV0603)'}
LCSC={'Q11': 'C148105', 'Q12': 'C148105', 'Q13': 'C148105', 'Q14': 'C148105', 'Q15': 'C148105', 'Q16': 'C148105', 'Q17': 'C148105', 'Q18': 'C148105', 'Q19': 'C148105', 'Q20': 'C148105'}
NOBOM=['J2', 'TP2', 'TP3']

def P(ref,lib,name,x,y,val,fp,nets,dnp=False,unit=1): parts.append((ref,lib,name,x,y,val,fp,nets,dnp,unit))
# --- power in
P('J1','Connector','USB_C_Receptacle_PowerOnly_6P',35.56,55.88,'USB4125-GF-A','Connector_USB:USB_C_Receptacle_GCT_USB4125-xx-x_6P_TopMnt_Horizontal',
  {'A9':'VBUS','B9':'VBUS','A5':'CC1','B5':'CC2','A12':'GND','B12':'GND','SH':'GND'})
P('R3','Device','R',60.96,68.58,'5.1kΩ',R04,{'1':'CC1','2':'GND'})
P('R4','Device','R',68.58,68.58,'5.1kΩ',R04,{'1':'CC2','2':'GND'})
P('F1','Device','Polyfuse',76.2,45.72,'MF-NSMF050-2','Fuse:Fuse_1206_3216Metric',{'1':'VBUS_F','2':'VBUS'})
P('FB1','Device','FerriteBead_Small',83.82,68.58,'600Ω@100MHz','Inductor_SMD:L_0603_1608Metric',{'1':'VBUS_F','2':'+5V'})
P('D3','Device','D_Zener',50.8,76.2,'SMF5.0A','Diode_SMD:D_SOD-123F',{'1':'VBUS','2':'GND'})
P('C1','Device','C',91.44,48.26,'10uF',C06,{'1':'+5V','2':'GND'})
P('C2','Device','C',104.14,48.26,'100nF',C04,{'1':'+5V','2':'GND'})
P('#FLG01','power','PWR_FLAG',86.36,35.56,'PWR_FLAG','',{'1':'+5V'})
P('#FLG02','power','PWR_FLAG',35.56,83.82,'PWR_FLAG','',{'1':'GND'})
# --- boost
P('C3','Device','C',121.92,48.26,'22uF 10V','Capacitor_SMD:C_0805_2012Metric',{'1':'+5V','2':'GND'})
P('L11','Device','L',134.62,40.64,'330uH','NeonPine:L_6.3x6.3_H3',{'1':'+5V','2':'SW'})
P('D1','Device','D',152.4,33.02,'200V 1A fast recovery','Diode_SMD:D_SOD-123F',{'2':'SW','1':'HV+'})
P('Q1','Transistor_FET','Q_NMOS_GDS',144.78,58.42,'DMN15H310SE','Package_TO_SOT_SMD:SOT-223-3_TabPin2',{'1':'GATE','2':'SW','3':'GND'})
P('R1','Device','R',129.54,68.58,'47Ω',R04,{'1':'GATE_DRV','2':'GATE'})
P('R2','Device','R',137.16,68.58,'100kΩ',R04,{'1':'GATE','2':'GND'})
P('C4','Device','C',170.18,48.26,'1uF 250V','Capacitor_SMD:C_1210_3225Metric',{'1':'HV+','2':'GND'})
P('D2','Device','D_Zener',185.42,48.26,'SMF100A','Diode_SMD:D_SOD-123F',{'1':'HV+','2':'GND'})
P('R12','Device','R',228.6,40.64,'100Ω','Resistor_SMD:R_0805_2012Metric',{'1':'SW','2':'SNUB'},dnp=True)
P('C8','Device','C',228.6,53.34,'100pF 250V C0G','Capacitor_SMD:C_0805_2012Metric',{'1':'SNUB','2':'GND'},dnp=True)
P('R5','Device','R',208.28,40.64,'1MΩ',R06,{'1':'HV+','2':'FB_MID'})
P('R6','Device','R',208.28,53.34,'1MΩ',R06,{'1':'FB_MID','2':'VFB'})
P('R7','Device','R',208.28,66.04,'39kΩ',R04,{'1':'VFB','2':'GND'})
P('C5','Device','C',218.44,66.04,'10nF',C04,{'1':'VFB','2':'GND'})
# --- MCU. Lamp -> pin map (PC0-4,PC7 = pins 10-14,17; PD0 = 8, PD6 = 3, PA1 = 5) comes from tools/pinswap.py when present
_lp=os.path.join(os.path.dirname(os.path.abspath(__file__)),'lamp_pins.json')
import json
_j=json.load(open(_lp)) if os.path.exists(_lp) else {}
SR_SLOTS=_j.get('sr')                       # AC branch format: {"mcu": {pin: LAMPn}, "sr": [16 shift-register slots]}
LAMP_PINS=_j['mcu'] if 'mcu' in _j else _j if _j else {'10':'LAMP1','11':'LAMP2','12':'LAMP3','13':'LAMP4','14':'LAMP5',
  '15':'LAMP6','16':'LAMP7','17':'LAMP8','8':'LAMP9','1':'LAMP10'}
# --- MCU
LAMP_PINS={k:v for k,v in LAMP_PINS.items() if k not in ('1','15','16')}   # PD4/PC5/PC6 drive the shift registers (PC5/PC6 = SPI1 SCK/MOSI)
P('U1','MCU_WCH_RiscV','CH32V003FxPx',60.96,121.92,'CH32V003F4P6','Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm',
  {**LAMP_PINS, '18':'SWIO','19':'GATE_DRV','20':'VFB','2':'LDR','4':'NRST',
   '15':'SR_SCK','6':'TOUCH2','16':'SR_DATA','1':'SR_LATCH','9':'+5V','7':'GND'})
P('C6','Device','C',101.6,106.68,'100nF',C04,{'1':'+5V','2':'GND'})
P('C7','Device','C',101.6,129.54,'100nF',C04,{'1':'NRST','2':'GND'})
P('J2','Connector_Generic','Conn_01x03',101.6,149.86,'SWD pogo pads','NeonPine:Pogo_1x03_P2.54mm',
  {'1':'+5V','2':'SWIO','3':'GND'})
# --- inputs
P('Q2','Device','Q_Photo_NPN',137.16,111.76,'TEPT4400','LED_THT:LED_D3.0mm',{'1':'+5V','2':'LDR'})
P('R9','Device','R',137.16,127,'22kΩ',R04,{'1':'LDR','2':'GND'})
P('TP2','Connector','TestPoint',175.26,111.76,'Touch trunk','NeonPine:TouchPad_D4.0mm_Masked',{'1':'TP_TRUNK'})
P('R11','Device','R',175.26,124.46,'1kΩ',R04,{'1':'TP_TRUNK','2':'TOUCH2'})
P('TP3','Connector','TestPoint',198.12,111.76,'SR_CLK test','TestPoint:TestPoint_Pad_1.5x1.5mm',{'1':'SR_CLK'})
# --- lamps (x 10): each lead has a 150k pull-up to HV+ and one half of an MMDT5551 (dual 160 V NPN, SOT-363) to GND
# (an H-bridge per lamp: unit 1 = K side, unit 2 = A side). The pull-ups see up to 105 V (123 V at the D2 clamp), so they
# are 0603 high-voltage types (>= 200 V working voltage, e.g. RCV0603); ordinary 0603 thick film is only rated 75 V.
# Pulling one lead low makes that lead the cathode, so that electrode glows; both off = dark (see DESIGN.md 2.3).
# Drawn with explicit wires (MANUAL parts skip the automatic label stubs).
MANUAL=set(); ROT={}; PROPS={}; mw=[]; mj=[]; ml=[]; mp=[]   # manual wires, junctions, labels, power symbols
SR_LAMPS=[f'LAMPA{n}' for n in range(1,11)]+[f'LAMP{n}' for n in range(1,11) if f'LAMP{n}' not in LAMP_PINS.values()]
assert len(SR_LAMPS)<=16
COL0, PITCH, XK, ROW0, ROWP = 38.1, 76.2, 38.1, 184.15, 38.1
SOT363='Package_TO_SOT_SMD:SOT-363_SC-70-6'
for n in range(1,11):
    r,c=(n-1)//5,(n-1)%5
    xa=COL0+c*PITCH; xk=xa+XK; mid=xa+XK/2; Yr=ROW0+r*ROWP; yN=Yr+12.7; Yg=yN+15.24
    def M(ref,*a,rot=0,props=None,unit=1):
        P(ref,*a,unit=unit); MANUAL.add(ref); ROT[ref]=rot
        if props: PROPS[ref]=props
    M(f'R{20+n}','Device','R',xa,yN-6.35,'150kΩ 200V',R06,{'1':'HV+','2':f'A{n}'})
    M(f'R{30+n}','Device','R',xk,yN-6.35,'150kΩ 200V',R06,{'1':'HV+','2':f'K{n}'})
    M(f'LA{n}','Device','Lamp_Neon',mid,yN,'NEON-3','NeonPine:Lamp_Neon_Brightmaster_NEON-3_D4x10_P3.0',{'2':f'A{n}','1':f'K{n}'},
      rot=90,props=(mid,yN-7.62,mid,yN-5.08,None,90))
    M(f'Q{10+n}','Transistor_BJT','Q_Dual_NPN_NPN_E1B1C2E2B2C1',xa-2.54,yN+7.62,'MMDT5551',SOT363,{'3':f'A{n}','4':'GND','5':f'BA{n}'},unit=2)
    M(f'Q{10+n}','Transistor_BJT','Q_Dual_NPN_NPN_E1B1C2E2B2C1',xk-2.54,yN+7.62,'MMDT5551',SOT363,{'6':f'K{n}','1':'GND','2':f'B{n}'},unit=1)
    M(f'R{50+n}','Device','R',xa-11.43,yN+7.62,'22kΩ',R04,{'1':f'LAMPA{n}','2':f'BA{n}'},rot=90,props=(xa-11.43,yN+5.08,xa-11.43,yN+10.16,None,90))
    M(f'R{40+n}','Device','R',xk-11.43,yN+7.62,'22kΩ',R04,{'1':f'LAMP{n}','2':f'B{n}'},rot=90,props=(xk-11.43,yN+5.08,xk-11.43,yN+10.16,None,90))
    for x in (xa,xk):
        mw.append(((x,Yr),(x,yN-10.16))); mw.append(((x,yN-2.54),(x,yN))); mw.append(((x,yN),(x,yN+2.54)))
        mw.append(((x,yN+12.7),(x,Yg))); mj.append((x,yN))
    mw.append(((xa,yN),(mid-5.08,yN))); mw.append(((mid+5.08,yN),(xk,yN)))
    for x,net in ((xa,f'LAMPA{n}'),(xk,f'LAMP{n}')):
        mw.append(((x-15.24,yN+7.62),(x-17.78,yN+7.62))); ml.append((net,x-17.78,yN+7.62,180))
    if c==0:   # row rails: HV+ along the top, GND along the bottom
        x_end=COL0+4*PITCH+XK
        mw.append(((xa-7.62,Yr),(x_end,Yr))); ml.append(('HV+',xa-7.62,Yr,180))
        mw.append(((xa,Yg),(x_end,Yg))); mp.append(('GND',xa,Yg))
    for x in (xa,xk):
        if not (c==4 and x==xk): mj.append((x,Yr))
        if not (c==4 and x==xk): mj.append((x,Yg))
# --- lamp drive shift registers: 2 x 74HC595, outputs in SR_LAMPS order (firmware maps lamp -> bit by table)
SR_OUT=['15','1','2','3','4','5','6','7']   # QA..QH
if SR_SLOTS: assert sorted(x for x in SR_SLOTS if x)==sorted(SR_LAMPS), 'lamp_pins.json does not match'
srn=(lambda k:{SR_OUT[i]:SR_SLOTS[k*8+i] for i in range(8) if SR_SLOTS[k*8+i]}) if SR_SLOTS else \
    (lambda k:{SR_OUT[i]:SR_LAMPS[k*8+i] for i in range(8) if k*8+i<len(SR_LAMPS)})
PROPS['U2']=(260.35,144.78,260.35,147.32,'left',0); PROPS['U3']=(313.69,144.78,313.69,147.32,'left',0)
P('U2','74xx','74HC595',256.54,124.46,'74HC595BQ','NeonPine:DHVQFN-16-1EP_2.5x3.5mm_P0.5mm_EP1x2mm_EPGND',
  {**srn(0),'14':'SR_DATA','11':'SR_CLK','12':'SR_LATCH','10':'+5V','13':'GND','9':'SR_CHAIN','16':'+5V','8':'GND'})
P('U3','74xx','74HC595',309.88,124.46,'74HC595BQ','NeonPine:DHVQFN-16-1EP_2.5x3.5mm_P0.5mm_EP1x2mm_EPGND',
  {**srn(1),'14':'SR_CHAIN','11':'SR_CLK','12':'SR_LATCH','10':'+5V','13':'GND','16':'+5V','8':'GND'})
P('C9','Device','C',233.68,149.86,'100nF',C04,{'1':'+5V','2':'GND'})
P('C10','Device','C',287.02,149.86,'100nF',C04,{'1':'+5V','2':'GND'})
P('R13','Device','R',215.9,124.46,'33Ω',R04,{'1':'SR_SCK','2':'SR_CLK'})   # SPI clock series R: edge rate / EMC (SR_CLK runs 39 mm on F.Cu)

notes=[(25.4,25.4,'POWER IN – USB-C 5V, TVS D3, PTC F1, ferrite FB1'),(119.38,25.4,'HV BOOST 75–100 V (MCU-controlled, TIM1 30 kHz)'),
 (25.4,96.52,'MCU CH32V003F4P6 (runs at 5 V)'),(132.08,96.52,'INPUTS – LDR, TKEY touch pads, spare pad'),
 (25.4,177.8,'NEON LAMPS – Brightmaster NEON-3 (strike ≤90 VDC, ~60 V settled). Each lead: 150k (200 V type) to HV+ and one half of an MMDT5551 (160 V) to GND. Pull one lead low: that electrode glows.'),
 (25.4,181.61,'I_lamp = (V_HV - 60 V)/150k ≈ 0.1–0.3 mA, plus V_HV/150k ≈ 0.7 mA lost in the pulled-low lead\'s own pull-up. Both off: dark, no current.'),
 (228.6,96.52,'LAMP DRIVE – 2 × 74HC595: LAMPA1–10 (anode-side switches) + the one cathode switch the MCU has no pin for'),
 (228.6,100.33,'SR_DATA = PC6 (SPI1 MOSI), SR_CLK = PC5 (SPI1 SCK), SR_LATCH = PD4. /OE tied low: outputs are random until the first latch, but the boost is off then (R2).'),
 (119.38,81.28,'Q1 DMN15H310SE: 150 V, 0.33 Ω @ Vgs=5 V. R2 keeps boost off during reset.'),
 (119.38,85.09,'D2 = hard OVP clamp (Vbr 111–123 V). R12/C8 snubber: optional (DNP).')]

for ref,lib,name,*_ ,fp,nets,dnp,unit in parts:
    if fp and not ref.startswith('#'):
        l,f=fp.split(':'); assert os.path.exists((FPDIR if l!='NeonPine' else PRJ+'/')+f'{l}.pretty/{f}.kicad_mod'),fp
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
def place(ref,lib,name,x,y,val,fp,nets,dnp,unit=1,power=False,rot=0):
    lid=f'{lib}:{name}'
    if lid not in syms:
        s=copy.deepcopy(getsym(lib,name)); s[1]=f'"{lid}"'; syms[lid]=s
    s=syms[lid]
    sym=['symbol',['lib_id',f'"{lid}"'],['at',f'{x:g}',f'{y:g}',str(rot)],['unit',str(unit)],['exclude_from_sim','no'],
         ['in_bom','no' if power or ref in NOBOM else 'yes'],['on_board','no' if power else 'yes'],['dnp','yes' if dnp else 'no'],['uuid',f'"{U()}"']]
    if power and rot in (90,270):   # sideways power symbol: value text horizontal, beyond its tip
        left=(rot==90)==(name!='GND')
        sym+= [prop('Reference',ref,x,y+3.81,True),['property','"Value"',f'"{val}"',['at',f'{x-5.08 if left else x+5.08:g}',f'{y:g}','90'],eff(False,'right' if left else 'left')]]
    elif power:
        sym+= [prop('Reference',ref,x,y+3.81,True),prop('Value',val,x,y-3.81 if name!='GND' else y+3.81)]
    elif ref in PROPS:
        rx,ry,vx,vy,j,a=PROPS[ref]; pr=lambda k,v,px,py: ['property',f'"{k}"',f'"{v}"',['at',f'{px:g}',f'{py:g}',str(a)],eff(False,j)]
        sym+= [pr('Reference',ref,rx,ry),pr('Value',val,vx,vy)]
    else:
        sym+= [prop('Reference',ref,x+5.08,y-1.27-(20.32 if ref=='U1' else 0),just='left'),prop('Value',val,x+5.08,y+1.27-(20.32 if ref=='U1' else 0),just='left')]
    sym+= [prop('Footprint',fp,x,y,True),prop('Datasheet','~',x,y,True),prop('Description',DESC.get(ref,''),x,y,True)]
    if ref in MPN: sym.append(prop('MPN',MPN[ref],x,y,True))
    if ref in LCSC: sym.append(prop('LCSC',LCSC[ref],x,y,True))
    for no,nm,px,py,a in pins(getsym(lib,name),unit):
        sym.append(['pin',f'"{no}"',['uuid',f'"{U()}"']])
        if no in nets and ref not in MANUAL:
            import math
            d=(-round(math.cos(math.radians(a))),round(math.sin(math.radians(a))))
            pinpos.setdefault(nets[no],[]).append((round(x+px,2),round(y-py,2),d))
    sym.append(['instances',['project','"NeonPine"',['path',f'"/{ROOT}"',['reference',f'"{ref}"'],['unit',str(unit)]]]])
    out.append(sym)
for p in parts: place(*p,power=p[0].startswith('#'),rot=ROT.get(p[0],0))
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
for a,b in mw: wire(a,b)
junctions=[['junction',['at',f'{x:g}',f'{y:g}'],['diameter','0'],['color','0','0','0','0'],['uuid',f'"{U()}"']] for x,y in dict.fromkeys(mj)]
for net,x,y,ang in ml:
    labels.append(['label',f'"{net}"',['at',f'{x:g}',f'{y:g}',str(ang)],['effects',['font',['size','1.27','1.27']],['justify','right' if ang in (180,270) else 'left','bottom']],['uuid',f'"{U()}"']])
for net,x,y in mp:
    npw+=1; place(f'#PWR{npw:03d}','power',net,x,y,net,'',{},False,power=True)
ncs=[]
for ref in ('U2','U3'):
    p=[q for q in parts if q[0]==ref][0]
    for no,nm,px,py,a in pins(getsym(p[1],p[2])):
        if no not in p[7]: ncs.append(['no_connect',['at',f'{p[3]+px:g}',f'{round(p[4]-py,2):g}'],['uuid',f'"{U()}"']])
texts=[['text',f'"{t}"',['exclude_from_sim','no'],['at',f'{x:g}',f'{y:g}','0'],['effects',['font',['size','2' if t.isupper() or '–' in t[:20] else '1.27','2' if t.isupper() or '–' in t[:20] else '1.27']],['justify','left','bottom']],['uuid',f'"{U()}"']] for x,y,t in notes]
sch=['kicad_sch',['version','20260306'],['generator','"eeschema"'],['generator_version','"10.0"'],['uuid',f'"{ROOT}"'],['paper','"A3"'],
     ['title_block',['title','"NeonPine – neon Christmas tree night light"'],['date','"2026-10-05"'],['rev','"B"']],
     ['lib_symbols']+list(syms.values())]+texts+junctions+ncs+wires+labels+out+[['sheet_instances',['path','"/"',['page','"1"']]],['embedded_fonts','no']]
open(os.path.join(PRJ,'NeonPine.kicad_sch'),'w').write(dump(sch)+'\n')
print(len(parts),'parts', npw,'pwr', len(labels),'labels')
