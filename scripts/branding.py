"""Generate the VU Spectrum mark and raster exports from its segment specification."""
from pathlib import Path
import cairo, gi
gi.require_version("Rsvg","2.0")
from gi.repository import Rsvg
root=Path(__file__).resolve().parents[1]
bars=[]
for column,height in enumerate((4,6,8,5,7)):
    for row in range(height):
        color=("#4298FF","#A578F4","#FF9F43")[0 if row<4 else 1 if row<6 else 2]
        bars.append(f'<rect x="{14+column*15}" y="{79-row*9}" width="12" height="6" rx="1.6" fill="{color}"/>')
mark='<rect width="100" height="100" rx="16" fill="#121826"/>'+''.join(bars)
def export(name,w,h,body,sizes):
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">{body}</svg>'
    path=root/'branding'/name
    path.with_suffix('.svg').write_text(svg)
    handle=Rsvg.Handle.new_from_data(svg.encode())
    for width,height,filename in sizes:
        surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,width,height)
        box=Rsvg.Rectangle();box.width=width;box.height=height
        handle.render_document(cairo.Context(surface),box)
        surface.write_to_png(str(root/filename))
export('vu-spectrum',100,100,mark,[(n,n,f'branding/icon-{n}.png') for n in (512,256,144)]+[(512,512,'docs/openaction/org.codex.vuengine.png')])
(root/'plugin/org.codex.vuengine.sdPlugin/icons/plugin.svg').write_bytes((root/'branding/vu-spectrum.svg').read_bytes())
for name,w,h in [('banner',1600,600),('social',1280,640)]:
    body=f'<rect width="{w}" height="{h}" fill="#191E27"/><g transform="translate({w/2-100} 32) scale(2)">{mark}</g>'
    for y,size,label,color in [(310,60,'VU ENGINE PRO','white'),(367,28,'COMMUNITY EDITION','#94A3B8'),(447,36,'Your audio. Your control.','white'),(520,28,'Built for Linux. Powered by PipeWire.','#94A3B8')]:
        body+=f'<text x="50%" y="{y}" text-anchor="middle" font-family="DejaVu Sans" font-size="{size}" fill="{color}">{label}</text>'
    export(name,w,h,body,[(w,h,f'branding/{name}.png')])
