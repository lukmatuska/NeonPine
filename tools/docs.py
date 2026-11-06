#!/usr/bin/env python3
"""Regenerate the documentation outputs (docs/compliance is left alone):
  * docs/NeonPine-schematic.pdf                      kicad-cli sch export pdf
  * docs/img/{front,back,iso-front,iso-back}.png      kicad-cli pcb render (cover-and-stand.png only with --cover)
  * docs/mcu-netlist.md                               tools/mcu_netlist.py
  * fab/ (Gerbers + drill + zip, pick & place, BOM, STEP; cover + stand Gerbers)   the commands of docs/manufacturing.md §1
  * DESIGN.pdf, docs/{README,manufacturing,user-manual,mcu-netlist}.pdf   Markdown -> HTML -> headless Chromium
Usage: python3 tools/docs.py [--no-render] [--no-fab] [--cover]"""
import os, re, sys, subprocess, shutil, zipfile, tempfile, html
import markdown

PRJ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
PCB, SCH = os.path.join(PRJ, 'NeonPine.kicad_pcb'), os.path.join(PRJ, 'NeonPine.kicad_sch')
MD = ['DESIGN.md', 'docs/README.md', 'docs/manufacturing.md', 'docs/user-manual.md', 'docs/mcu-netlist.md']
CHROME = shutil.which('chromium') or shutil.which('google-chrome') or shutil.which('google-chrome-stable')

def run(*cmd):
    print('$', ' '.join(cmd))
    r = subprocess.run(cmd, cwd=PRJ, capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stdout + r.stderr)

def schematic():
    run('kicad-cli', 'sch', 'export', 'pdf', '-o', 'docs/NeonPine-schematic.pdf', SCH)

RENDERS = {   # name: (side, width, height, extra)
    'front': ('top', 1568, 1768, []),
    'back': ('bottom', 1568, 1768, []),
    'iso-front': ('top', 1768, 1488, ['--perspective', '--rotate', '-45,0,-25', '--zoom', '0.8', '--pan', '0,1,0']),
    'iso-back': ('bottom', 1768, 1488, ['--perspective', '--rotate', '-35,0,30', '--zoom', '0.8', '--pan', '0,1,0']),
}
def renders(cover):
    for name, (side, w, h, extra) in RENDERS.items():
        run('kicad-cli', 'pcb', 'render', '-o', f'docs/img/{name}.png', '--side', side, '-w', str(w), '-h', str(h),
            '--quality', 'high', '--floor', '--background', 'opaque', *extra, PCB)
    if cover:
        run('kicad-cli', 'pcb', 'render', '-o', 'docs/img/cover-and-stand.png', '--side', 'top', '-w', '1376', '-h', '1768',
            '--quality', 'high', '--floor', '--background', 'opaque', os.path.join(PRJ, 'NeonPine-cover.kicad_pcb'))

def fab():
    g = 'fab/gerber/'
    for f in os.listdir(os.path.join(PRJ, g)): os.remove(os.path.join(PRJ, g, f))
    run('kicad-cli', 'pcb', 'export', 'gerbers', '-o', g, '--layers',
        'F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,F.Paste,B.Paste,Edge.Cuts', PCB)
    run('kicad-cli', 'pcb', 'export', 'drill', '-o', g, '--format', 'excellon', '--generate-map', '--map-format', 'gerberx2', PCB)
    with zipfile.ZipFile(os.path.join(PRJ, 'fab/NeonPine-gerbers.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(os.path.join(PRJ, g))): z.write(os.path.join(PRJ, g, f), f)
    run('kicad-cli', 'pcb', 'export', 'pos', '-o', 'fab/NeonPine-pos.csv', '--format', 'csv', '--units', 'mm', '--side', 'both',
        '--exclude-dnp', PCB)
    run('kicad-cli', 'sch', 'export', 'bom', '-o', 'fab/NeonPine-bom.csv', '--fields',
        'Reference,Value,Footprint,${QUANTITY},${DNP}', '--group-by', 'Value,Footprint', SCH)
    run('kicad-cli', 'pcb', 'export', 'step', '-o', 'fab/NeonPine.step', '--subst-models', '--force', PCB)
    # rear cover + stand base (no copper): built by tools/cover.py from the same outline()
    c, cover = 'fab/cover/', os.path.join(PRJ, 'NeonPine-cover.kicad_pcb')
    for f in os.listdir(os.path.join(PRJ, c)): os.remove(os.path.join(PRJ, c, f))
    run('kicad-cli', 'pcb', 'export', 'gerbers', '-o', c, '--layers', 'F.Mask,B.Mask,F.Silkscreen,Edge.Cuts', cover)
    run('kicad-cli', 'pcb', 'export', 'drill', '-o', c, '--format', 'excellon', cover)
    with zipfile.ZipFile(os.path.join(PRJ, 'fab/NeonPine-cover-stand-gerbers.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(os.path.join(PRJ, c))): z.write(os.path.join(PRJ, c, f), f)

CSS = '''
@page { size: A4; margin: 14mm 14mm 16mm 14mm; }
body { font-family: "DejaVu Sans", sans-serif; font-size: 9.5pt; line-height: 1.38; color: #111; }
h1 { font-size: 19pt; border-bottom: 2px solid #333; padding-bottom: 3px; margin-top: 0; }
h2 { font-size: 14pt; border-bottom: 1px solid #999; padding-bottom: 2px; margin-top: 18px; page-break-after: avoid; }
h3 { font-size: 11.5pt; margin-top: 14px; page-break-after: avoid; }
table { border-collapse: collapse; margin: 6px 0 10px; page-break-inside: auto; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid #aaa; padding: 2px 6px; vertical-align: top; font-size: 8.5pt; }
th { background: #e8e8e8; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 8pt; background: #f2f2f2; padding: 0 2px; }
pre { background: #f2f2f2; border: 1px solid #ddd; padding: 6px 8px; white-space: pre-wrap; font-size: 6.8pt; line-height: 1.25; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
pre.art { white-space: pre; font-family: "DejaVu Sans Mono", monospace; font-size: 6.6pt; overflow: hidden; }
pre.art code { font-size: 6.6pt; }
blockquote { border-left: 3px solid #bbb; margin: 8px 0; padding: 2px 10px; background: #fafafa; }
img { max-width: 100%; max-height: 120mm; }
td img { max-height: 90mm; }
a { color: #0645ad; text-decoration: none; }
'''

def gfm_lists(text):
    """python-markdown wants 4-space list nesting; these docs use GitHub's 2-space style. Double leading indents outside code."""
    out, fence = [], False
    for line in text.split('\n'):
        if line.lstrip().startswith('```'): fence = not fence; out.append(line); continue
        if fence: out.append(line); continue
        pre = ''
        m = re.match(r'^(\s*>\s?)(.*)$', line)
        if m: pre, line = m.group(1), m.group(2)
        n = len(line) - len(line.lstrip(' '))
        out.append(pre + ' ' * (2 * n) + line.lstrip(' ') if n else pre + line)
    return '\n'.join(out)

def pdf(md_path):
    src = os.path.join(PRJ, md_path)
    body = markdown.markdown(gfm_lists(open(src).read()), extensions=['tables', 'fenced_code', 'sane_lists'])
    # ASCII diagrams (box-drawing characters) must not wrap; long shell commands may
    body = re.sub(r'<pre>(<code[^>]*>)((?:(?!</code>).)*[\u2500-\u257f](?:(?!</code>).)*)</code></pre>',
                  r'<pre class="art">\1\2</code></pre>', body, flags=re.S)
    body = re.sub(r'href="([^":#]+)\.md(#[^"]*)?"', lambda m: f'href="{m.group(1)}.pdf{m.group(2) or ""}"', body)
    title = html.escape(open(src).readline().lstrip('# ').strip())
    page = f'<!doctype html><html><head><meta charset="utf-8"><title>{title}</title><style>{CSS}</style></head><body>{body}</body></html>'
    tmp = os.path.join(os.path.dirname(src), '.~docs-tmp.html')     # next to the .md so relative image paths resolve
    open(tmp, 'w').write(page)
    out = src[:-3] + '.pdf'
    try:
        with tempfile.TemporaryDirectory() as prof:
            subprocess.run([CHROME, '--headless', '--disable-gpu', '--no-sandbox', f'--user-data-dir={prof}', '--no-pdf-header-footer',
                            f'--print-to-pdf={out}', 'file://' + tmp], check=True, capture_output=True)
    finally:
        os.remove(tmp)
    print('wrote', os.path.relpath(out, PRJ))

if __name__ == '__main__':
    schematic()
    if '--no-render' not in sys.argv: renders('--cover' in sys.argv)
    run(sys.executable, 'tools/mcu_netlist.py')
    if '--no-fab' not in sys.argv: fab()
    assert CHROME, 'chromium not found'
    for m in MD: pdf(m)
