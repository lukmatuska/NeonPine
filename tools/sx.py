import re
def parse(s):
    toks=re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+',s); i=0
    def rd():
        nonlocal i
        t=toks[i]; i+=1
        if t=='(':
            l=[]
            while toks[i]!=')': l.append(rd())
            i+=1; return l
        return t
    out=[]
    while i<len(toks): out.append(rd())
    return out
def dump(e,ind=0):
    if not isinstance(e,list): return e
    if all(not isinstance(x,list) for x in e): return '('+' '.join(e)+')'
    pre='\t'*(ind+1)
    return '('+' '.join(x for x in e if not isinstance(x,list)) + ''.join('\n'+pre+dump(x,ind+1) for x in e if isinstance(x,list))+')'
LIB='/usr/share/kicad/symbols/'
_cache={}
def getsym(lib,name):
    if lib not in _cache: _cache[lib]=parse(open(LIB+lib+'.kicad_sym').read())[0]
    for e in _cache[lib]:
        if isinstance(e,list) and e[0]=='symbol' and e[1]=='"%s"'%name: return e
    raise KeyError(name)
def pins(sym,unit=1):
    r=[]
    for u in sym:
        if isinstance(u,list) and u[0]=='symbol':
            un=int(u[1].strip('"').split('_')[-2])
            if un not in (0,unit): continue
            for p in u:
                if isinstance(p,list) and p[0]=='pin':
                    at=[x for x in p if isinstance(x,list) and x[0]=='at'][0]
                    nm=[x for x in p if isinstance(x,list) and x[0]=='name'][0][1].strip('"')
                    no=[x for x in p if isinstance(x,list) and x[0]=='number'][0][1].strip('"')
                    r.append((no,nm,float(at[1]),float(at[2]),float(at[3]) if len(at)>3 else 0))
    return r
