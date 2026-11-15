"""Ronda 4: los iconos con la paleta oficial «La tira» (amarillo, lima, verde, verde azulado, salmón, tinta)."""
import math
import os

import build as B
import typo
from geom import GREEN, INK, LIME, PAPER, SALMON, TEAL, YELLOW, A, n, poly, rrect, svg

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proto4")
os.makedirs(OUT, exist_ok=True)
W = "#fff"
P = {}


def ic(body, bg, key, defs=""):
    return B.icon(defs + body, bg, key, key)


# 01
w, g, h, r = 150, 38, 492, 34
x0 = 512 - (4 * w + 3 * g) / 2
P["01a"] = ic("".join(f'<path d="{rrect(x0 + i * (w + g), 512 - h / 2, w, h, r)}" fill="{A[i]}"/>' for i in range(4)), INK, "01a")

# 02
yl, R, t = 420, 312, 148
tip, sub, _, _ = B.iceberg_parts(512, yl - t, R, t, yl, 0, 0)
P["02a"] = ic(f'<rect y="{yl}" width="1024" height="{1024 - yl}" fill="{TEAL}"/><path d="{tip}" fill="{W}"/><path d="{sub}" fill="{LIME}"/>', INK, "02a")
P["02b"] = ic(f'<rect y="{yl}" width="1024" height="{1024 - yl}" fill="{TEAL}"/><path d="{tip}" fill="{W}"/><path d="{sub}" fill="{YELLOW}"/>', INK, "02b")
grad = (f'<defs><linearGradient id="gz" x1="0" y1="{yl}" x2="0" y2="{yl - t + 2 * R}" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{YELLOW}"/><stop offset=".4" stop-color="{LIME}"/><stop offset=".75" stop-color="{GREEN}"/><stop offset="1" stop-color="{TEAL}"/></linearGradient></defs>')
P["02c"] = ic(f'<rect y="{yl}" width="1024" height="{1024 - yl}" fill="{INK}"/><path d="{tip}" fill="{TEAL}"/><path d="{sub}" fill="url(#gz)"/>', W, "02c", grad)
P["02d"] = ic(f'<rect y="{yl - 14}" width="1024" height="28" fill="{LIME}"/><path d="{tip}" fill="{W}" transform="translate(0 -30)"/><path d="{sub}" fill="url(#gz)" transform="translate(0 30)"/>', INK, "02d", grad)

# 03
g3 = B.GOTA
pad, dpath, tip3, rr = B.gota_geom()
x_min, x_max = g3["cx"] - g3["R"], pad[0] + pad[2]
pad, dpath, tip3, rr = B.gota_geom(1.0, 512 - (x_min + x_max) / 2, 512 - (tip3[1] + pad[1] + pad[3]) / 2)


def gota(bg, fp, fd, fi, key):
    return ic(
        f'<path d="{rrect(*pad, rr)}" fill="{fp}"/><path d="{dpath}" fill="{fd}"/><path d="{dpath}" fill="{fi}" clip-path="url(#p{key})"/>',
        bg,
        key,
        f'<defs><clipPath id="p{key}"><path d="{rrect(*pad, rr)}"/></clipPath></defs>',
    )


P["03a"] = gota(TEAL, W, YELLOW, GREEN, "03a")
P["03b"] = gota(TEAL, W, LIME, INK, "03b")
P["03c"] = gota(INK, W, YELLOW, TEAL, "03c")
P["03d"] = gota(INK, W, LIME, GREEN, "03d")

# 04
roof, sq = B.casa_parts(512, 176, 372, 132, 344, 176 + 372 - 10, 40)
P["04a"] = ic(f'<path d="{roof}" fill="{INK}"/><path d="{sq}" fill="{LIME}"/>', W, "04a")
P["04b"] = ic(f'<path d="{roof}" fill="{INK}"/><path d="{sq}" fill="{TEAL}"/>', W, "04b")
P["04c"] = ic(f'<path d="{roof}" fill="{W}"/><path d="{sq}" fill="{LIME}"/>', INK, "04c")
P["04d"] = ic(f'<path d="{roof}" fill="{INK}"/><path d="{sq}" fill="{W}"/>', LIME, "04d")

# 05
def alb(cols, bg, key, S=760, rel=(1.0, 0.684, 0.368)):
    sqs = B.albers(512 - S / 2, 512 - S / 2, S, rel)
    return ic("".join(f'<path d="{rrect(x, y, s, s, s * 0.16)}" fill="{cols[i]}"/>' for i, (x, y, s) in enumerate(sqs)), bg, key)


P["05a"] = alb([LIME, GREEN, TEAL], YELLOW, "05a")
P["05b"] = alb([YELLOW, LIME, GREEN, TEAL], W, "05b", 800, (1.0, 0.74, 0.48, 0.24))
P["05c"] = alb([YELLOW, LIME, GREEN, TEAL], INK, "05c", 800, (1.0, 0.74, 0.48, 0.24))

# 06
p = B.LH
total = p["Lw"] + p["gap"] + p["Hw"]
Ls, Lp, Hs, cr, _ = B.lh_parts(512 - total / 2, 512 - p["H"] / 2, p["w"], p["H"], p["Lw"], p["Hw"], p["gap"], p["r"])
for key, fl, fh in (("06a", GREEN, SALMON), ("06b", LIME, SALMON)):
    P[key] = ic(
        f'<path d="{Ls}" fill="{W}"/><path d="{Lp}" fill="{fl}"/><path d="{Hs}" fill="{W}"/>'
        f'<rect x="{n(cr[0] - 1)}" y="{n(cr[1])}" width="{n(cr[2] + 2)}" height="{n(cr[3])}" fill="{fh}"/>',
        INK,
        key,
    )

# 07
def lh_type(F7, wd, bg, fl, fh, key, wl=380, wh=900, ov=14):
    dL, wL, bL = typo.layout("L", F7, wght=wl, wdth=wd)
    dH, wH, bH = typo.layout("H", F7, wght=wh, wdth=wd, x=wL - ov * F7 / 610)
    tw = bH[2] - bL[0]
    capH = bH[3] - bH[1]
    return ic(f'<g transform="translate({n(512 - tw / 2 - bL[0])} {n(512 + capH / 2)})"><path d="{dL}" fill="{fl}"/><path d="{dH}" fill="{fh}"/></g>', bg, key)


P["07a"] = lh_type(610, 100, LIME, INK, INK, "07a")
P["07b"] = lh_type(420, 125, LIME, INK, INK, "07b")
P["07c"] = lh_type(610, 100, W, INK, INK, "07c")
P["07d"] = lh_type(470, 125, INK, LIME, W, "07d", ov=20)

for k, v in P.items():
    with open(os.path.join(OUT, f"{k}.svg"), "w", encoding="utf8") as f:
        f.write(v)
print(",".join(P))
