"""Segunda ronda de prototipos: gota, casa, ritmo, LH de tiras y monograma."""
import math
import os

import typo
from geom import A, C, INK, PAPER, PLASTIC, TEAL, TEAL_MID, TEAL_SOFT, drop, n, poly, pt, ring, rrect, squircle, svg

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proto")
SQ = squircle()


def icon(body, bg, key):
    return svg(
        1024,
        1024,
        f'<defs><clipPath id="m{key}"><path d="{SQ}"/></clipPath></defs>'
        f'<g clip-path="url(#m{key})"><rect width="1024" height="1024" fill="{bg}"/>{body}</g>',
    )


P = {}

# 03b gota en diagonal sobre la esquina de la almohadilla (Venn)
pad = (400, 420, 400, 400)
R = 175
dpath, tip = drop(400 + 20, 420 + 10, R, 60)
def gota(pad, dpath, fill_pad, fill_drop, fill_int, key, rr=48):
    return (
        f'<defs><clipPath id="c{key}"><path d="{rrect(*pad, rr)}"/></clipPath></defs>'
        f'<path d="{rrect(*pad, rr)}" fill="{fill_pad}"/>'
        f'<path d="{dpath}" fill="{fill_drop}"/>'
        f'<path d="{dpath}" fill="{fill_int}" clip-path="url(#c{key})"/>'
    )
# centrar el conjunto
x_min = min(400 + 20 - R, pad[0]); x_max = pad[0] + pad[2]
y_min = tip[1]; y_max = pad[1] + pad[3]
dx = 512 - (x_min + x_max) / 2; dy = 512 - (y_min + y_max) / 2
P["03b"] = icon(f'<g transform="translate({n(dx)} {n(dy)})">{gota(pad, dpath, A[0], TEAL_MID, TEAL, "b")}</g>', INK, "03b")

# 03c gota sobre una tira ancha (horizontal)
pad = (150, 560, 724, 250)
dpath, tip = drop(512, 560, 170, 60)
dy = 512 - (tip[1] + 810) / 2
P["03c"] = icon(f'<g transform="translate(0 {n(dy)})">{gota(pad, dpath, A[0], TEAL_MID, TEAL, "c", 40)}</g>', INK, "03c")

# 03d gota en diagonal, fondo claro: almohadilla blanca con borde, gota tinta
pad = (392, 400, 420, 420)
dpath, tip = drop(392 + 30, 400 + 30, 185, 60)
x_min = 392 + 30 - 185; x_max = 812; y_min = tip[1]; y_max = 820
dx = 512 - (x_min + x_max) / 2; dy = 512 - (y_min + y_max) / 2
P["03d"] = icon(f'<g transform="translate({n(dx)} {n(dy)})">{gota(pad, dpath, A[1], TEAL_MID, TEAL, "d")}</g>', PAPER, "03d")

# 04c casa más rotunda
t = 132
apex = 176
half = 372
k = t * math.sqrt(2)
roof = poly([(512, apex), (512 + half, apex + half), (512 + half - k, apex + half), (512, apex + k), (512 - half + k, apex + half), (512 - half, apex + half)])
s = 344
sq_y = apex + k + (half - k) - 4  # el cuadrado arranca a la altura del alero interior
sq_y = apex + half - 10
P["04c"] = icon(f'<path d="{roof}" fill="{INK}"/><path d="{rrect(512 - s / 2, sq_y, s, s, 40)}" fill="{TEAL}"/>', PAPER, "04c")
# 04d: tejado sobre tinta, cuadrado verde medio
P["04d"] = icon(f'<path d="{roof}" fill="#fff"/><path d="{rrect(512 - s / 2, sq_y, s, s, 40)}" fill="{A[2]}"/>', INK, "04d")

# 05c ritmo: anillos que se estrechan, grosor creciente
P["05c"] = icon(
    f'<path d="{ring(150, 150, 724, 724, 150, 46)}" fill="{TEAL_MID}" fill-rule="evenodd"/>'
    f'<path d="{ring(262, 262, 500, 500, 104, 70)}" fill="{TEAL}" fill-rule="evenodd"/>'
    f'<path d="{rrect(392, 392, 240, 240, 50)}" fill="{INK}"/>',
    PAPER,
    "05c",
)
# 05d ritmo sobre tinta
P["05d"] = icon(
    f'<path d="{ring(150, 150, 724, 724, 150, 46)}" fill="{TEAL}" fill-rule="evenodd"/>'
    f'<path d="{ring(262, 262, 500, 500, 104, 70)}" fill="{A[2]}" fill-rule="evenodd"/>'
    f'<path d="{rrect(392, 392, 240, 240, 50)}" fill="#fff"/>',
    INK,
    "05d",
)

# 06b LH de tiras con las almohadillas dentro de las letras
w = 124
H = 540
y0 = 512 - H / 2
Lw = 330
Hw = 400
gapLH = 74
total = Lw + gapLH + Hw
x0 = 512 - total / 2
r = 26
L_stem = rrect(x0, y0, w, H, r)
L_foot = rrect(x0, y0 + H - w, Lw, w, r)
x1 = x0 + Lw + gapLH
H_l = rrect(x1, y0, w, H, r)
H_r = rrect(x1 + Hw - w, y0, w, H, r)
P["06b"] = icon(
    f'<path d="{L_stem}{L_foot}" fill="#fff"/>'
    f'<path d="{rrect(x0 + Lw - w, y0 + H - w, w, w, r)}" fill="{A[2]}"/>'
    f'<path d="{H_l}{H_r}" fill="#fff"/>'
    f'<rect x="{n(x1 + w - 1)}" y="{n(512 - w / 2)}" width="{n(Hw - 2 * w + 2)}" height="{n(w)}" fill="{C[3]}"/>',
    INK,
    "06b",
)
# 06c: igual pero almohadillas separadas por una junta fina
j = 16
P["06c"] = icon(
    f'<path d="{L_stem}" fill="#fff"/>'
    f'<path d="{rrect(x0 + w + j, y0 + H - w, Lw - w - j, w, r)}" fill="{A[2]}"/>'
    f'<path d="{H_l}{H_r}" fill="#fff"/>'
    f'<path d="{rrect(x1 + w + j, 512 - w / 2, Hw - 2 * w - 2 * j, w, r)}" fill="{C[3]}"/>',
    INK,
    "06c",
)

# 07c monograma: L fina (peso 400) + H negra, mismo ancho
F = 600
dL, wL, bL = typo.layout("L", F, wght=420, wdth=100)
dH, wH, bH = typo.layout("H", F, wght=900, wdth=100, x=wL + 6)
tw = bH[2] - bL[0]
capH = bH[3] - bH[1]
P["07c"] = icon(f'<g transform="translate({n(512 - tw / 2 - bL[0])} {n(512 + capH / 2)})"><path d="{dL} {dH}" fill="#fff"/></g>', TEAL, "07c")
# 07d: L estrecha negra + H ancha negra sobre tinta, con la L en verde medio
dL, wL, bL = typo.layout("L", F, wght=900, wdth=62)
dH, wH, bH = typo.layout("H", F, wght=900, wdth=125, x=wL - 6)
tw = bH[2] - bL[0]
P["07d"] = icon(
    f'<g transform="translate({n(512 - tw / 2 - bL[0])} {n(512 + capH / 2)})"><path d="{dL}" fill="{TEAL_MID}"/><path d="{dH}" fill="#fff"/></g>',
    INK,
    "07d",
)

for k, v in P.items():
    with open(os.path.join(OUT, f"{k}.svg"), "w", encoding="utf8") as f:
        f.write(v)
print("ok", ",".join(P))
