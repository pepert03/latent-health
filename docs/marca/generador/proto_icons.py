"""Prototipos de iconos (1024) para revisar a tamaño grande y a 32 px."""
import math
import os

import typo
from geom import A, C, INK, PAPER, PLASTIC, TEAL, TEAL_MID, TEAL_SOFT, drop, n, poly, pt, ring, rrect, squircle, svg

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proto")
os.makedirs(OUT, exist_ok=True)
SQ = squircle()


def icon(body, bg, key):
    return svg(
        1024,
        1024,
        f'<defs><clipPath id="m{key}"><path d="{SQ}"/></clipPath></defs>'
        f'<g clip-path="url(#m{key})"><rect width="1024" height="1024" fill="{bg}"/>{body}</g>',
    )


P = {}

# 01 carta: cuatro almohadillas de la escala de albúmina sobre tinta
w, g, h = 140, 44, 470
x0 = 512 - (4 * w + 3 * g) / 2
P["01a"] = icon("".join(f'<path d="{rrect(x0 + i * (w + g), 512 - h / 2, w, h, 30)}" fill="{A[i]}"/>' for i in range(4)), INK, "01a")

# 02 iceberg: rombo cortado por la línea del agua; mitad de abajo verde azulado
yl = 400
hd = 300  # media diagonal
top = yl - 130
cx = 512
cy = top + hd
tip = poly([(cx, top), (cx + (yl - top), yl), (cx - (yl - top), yl)])
gap = 0
sub = poly([(cx - (yl - top) - 0, yl + gap), (cx + (yl - top), yl + gap), (cx + hd, cy), (cx, cy + hd), (cx - hd, cy)])
P["02a"] = icon(
    f'<rect y="{yl}" width="1024" height="{1024 - yl}" fill="{TEAL}"/>'
    f'<path d="{tip}" fill="#fff"/><path d="{sub}" fill="{TEAL_MID}"/>',
    INK,
    "02a",
)
# variante: todo tinta, línea fina
P["02b"] = icon(
    f'<rect x="0" y="{yl - 18}" width="1024" height="36" fill="{TEAL_MID}"/>'
    f'<path d="{tip}" fill="#fff" transform="translate(0 -44)"/><path d="{sub}" fill="{TEAL_MID}" transform="translate(0 44)"/>',
    INK,
    "02b",
)

# 03 gota sobre la almohadilla
R = 168
pad = (512 - 210, 470, 420, 420)
dpath, dtip = drop(512, pad[1], R, 62)
shift = (1024 - (pad[1] + pad[3] - dtip[1])) / 2 - dtip[1]
P["03a"] = icon(
    f'<g transform="translate(0 {n(shift)})">'
    f'<defs><clipPath id="pc"><path d="{rrect(*pad, 44)}"/></clipPath></defs>'
    f'<path d="{rrect(*pad, 44)}" fill="{A[0]}"/>'
    f'<path d="{dpath}" fill="{TEAL_MID}"/>'
    f'<path d="{dpath}" fill="{TEAL}" clip-path="url(#pc)"/></g>',
    INK,
    "03a",
)

# 04 casa: tejado + almohadilla
t = 118
apex = 214
half = 330
roof = poly([(512, apex), (512 + half, apex + half), (512 + half - t * math.sqrt(2) / 1, apex + half), (512, apex + t * math.sqrt(2)), (512 - half + t * math.sqrt(2), apex + half), (512 - half, apex + half)])
s = 300
sq_y = apex + t * math.sqrt(2) + s / 2 + 40
P["04a"] = icon(f'<path d="{roof}" fill="{INK}"/><path d="{rrect(512 - s / 2, sq_y, s, s, 36)}" fill="{TEAL}"/>', PAPER, "04a")
# variante: tira alta con tejado y dos almohadillas
sw, sh = 330, 760
x = 512 - sw / 2
y = 512 - sh / 2
house = poly([(512, y), (x + sw, y + sw / 2), (x + sw, y + sh), (x, y + sh), (x, y + sw / 2)])
ps = 190
P["04b"] = icon(
    f'<path d="{house}" fill="#fff"/>'
    f'<path d="{rrect(512 - ps / 2, y + sh - 2 * ps - 70, ps, ps, 22)}" fill="{A[2]}"/>'
    f'<path d="{rrect(512 - ps / 2, y + sh - ps - 40, ps, ps, 22)}" fill="{C[3]}"/>',
    INK,
    "04b",
)

# 05 ritmo: cuadrados concéntricos que se cierran
P["05a"] = icon(
    f'<path d="{ring(512 - 350, 512 - 350, 700, 700, 120, 64)}" fill="{TEAL_MID}" fill-rule="evenodd"/>'
    f'<path d="{ring(512 - 230, 512 - 230, 460, 460, 80, 74)}" fill="{TEAL}" fill-rule="evenodd"/>'
    f'<path d="{rrect(512 - 110, 512 - 110, 220, 220, 36)}" fill="{INK}"/>',
    PAPER,
    "05a",
)
# variante Albers: asentados hacia abajo
P["05b"] = icon(
    f'<path d="{rrect(162, 150, 700, 700, 110)}" fill="{TEAL_MID}"/>'
    f'<path d="{rrect(272, 310, 480, 480, 76)}" fill="{A[2]}"/>'
    f'<path d="{rrect(382, 470, 260, 260, 42)}" fill="{TEAL}"/>',
    PAPER,
    "05b",
)

# 06 LH de tiras: tiras blancas y almohadillas de color
sw = 108
H = 540
y0 = 512 - H / 2
lx = 196
pad_s = 160
hx = lx + sw + pad_s + 14 + 70
cross = 176
body = (
    f'<path d="{rrect(lx, y0, sw, H, 22)}" fill="#fff"/>'
    f'<path d="{rrect(lx + sw + 14, y0 + H - pad_s, pad_s, pad_s, 22)}" fill="{A[2]}"/>'
    f'<path d="{rrect(hx, y0, sw, H, 22)}" fill="#fff"/>'
    f'<path d="{rrect(hx + sw + 14, 512 - 74, cross, 148, 22)}" fill="{C[3]}"/>'
    f'<path d="{rrect(hx + sw + 28 + cross, y0, sw, H, 22)}" fill="#fff"/>'
)
wtot = hx + 2 * sw + 28 + cross - lx
P["06a"] = icon(f'<g transform="translate({n(512 - wtot / 2 - lx)} 0)">{body}</g>', INK, "06a")

# 07 ancho: L estrecha + H ancha
F = 560
dL, wL, bL = typo.layout("L", F, wght=900, wdth=62)
dH, wH, bH = typo.layout("H", F, wght=900, wdth=125, x=wL - 4)
x_min = bL[0]
x_max = bH[2]
tw = x_max - x_min
capH = bH[3] - bH[1]
tx = 512 - tw / 2 - x_min
ty = 512 + capH / 2
P["07a"] = icon(f'<g transform="translate({n(tx)} {n(ty)})"><path d="{dL} {dH}" fill="#fff"/></g>', TEAL, "07a")
# variante peso: L fina, H negra
dL2, wL2, bL2 = typo.layout("L", F, wght=250, wdth=100)
dH2, wH2, bH2 = typo.layout("H", F, wght=900, wdth=100, x=wL2 + 10)
tw2 = bH2[2] - bL2[0]
P["07b"] = icon(f'<g transform="translate({n(512 - tw2 / 2 - bL2[0])} {n(ty)})"><path d="{dL2} {dH2}" fill="#fff"/></g>', TEAL, "07b")

for k, v in P.items():
    with open(os.path.join(OUT, f"{k}.svg"), "w", encoding="utf8") as f:
        f.write(v)

cells = "".join(
    f'<div class="c"><img src="{k}.svg" width="200" height="200"><div class="row">'
    f'<div class="hs l"><img src="{k}.svg" width="32" height="32"><span>LatentHealth</span></div>'
    f'<div class="hs d"><img src="{k}.svg" width="32" height="32"><span>LatentHealth</span></div>'
    f'<img src="{k}.svg" width="16" height="16"></div><b>{k}</b></div>'
    for k in P
)
html = f"""<!doctype html><meta charset=utf-8><style>
body{{margin:0;padding:24px;font:13px system-ui;background:#fff;display:flex;flex-wrap:wrap;gap:28px}}
.c{{display:flex;flex-direction:column;gap:10px;align-items:flex-start}}
.row{{display:flex;gap:10px;align-items:center}}
.hs{{display:flex;flex-direction:column;align-items:center;gap:4px;padding:10px 8px;width:80px;font-size:10px}}
.l{{background:#dfe5e3}} .d{{background:#2b2f33;color:#fff}}
</style>{cells}"""
with open(os.path.join(OUT, "index.html"), "w", encoding="utf8") as f:
    f.write(html)
print("ok", len(P))
