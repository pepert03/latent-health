"""Tercera ronda: gota, casa con dos almohadillas, ritmo estilo Albers, LH y rampa de peso."""
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


def gota(pad, dpath, fill_pad, fill_drop, fill_int, key, rr=48):
    return (
        f'<defs><clipPath id="c{key}"><path d="{rrect(*pad, rr)}"/></clipPath></defs>'
        f'<path d="{rrect(*pad, rr)}" fill="{fill_pad}"/>'
        f'<path d="{dpath}" fill="{fill_drop}"/>'
        f'<path d="{dpath}" fill="{fill_int}" clip-path="url(#c{key})"/>'
    )


def centered(pad, R, dcx, dcy, tip_angle):
    dpath, tip = drop(dcx, dcy, R, tip_angle)
    x_min = min(dcx - R, pad[0]); x_max = max(pad[0] + pad[2], dcx + R)
    y_min = tip[1]; y_max = max(pad[1] + pad[3], dcy + R)
    return dpath, 512 - (x_min + x_max) / 2, 512 - (y_min + y_max) / 2


P = {}
# 03e: almohadilla blanca, gota verde medio, cruce verde azulado; cruce más grande
pad = (420, 420, 400, 400)
dpath, dx, dy = centered(pad, 180, 450, 450, 60)
P["03e"] = icon(f'<g transform="translate({n(dx)} {n(dy)})">{gota(pad, dpath, "#fff", TEAL_MID, TEAL, "e")}</g>', INK, "03e")
# 03f: sobre verde azulado: almohadilla blanca, gota tinta? -> gota verde claro, cruce tinta
dpath, dx, dy = centered(pad, 180, 450, 450, 60)
P["03f"] = icon(f'<g transform="translate({n(dx)} {n(dy)})">{gota(pad, dpath, "#fff", TEAL_MID, INK, "f")}</g>', TEAL, "03f")

# 04e: casa con las dos almohadillas de la tira
t = 128
apex = 190
half = 360
k = t * math.sqrt(2)
roof = poly([(512, apex), (512 + half, apex + half), (512 + half - k, apex + half), (512, apex + k), (512 - half + k, apex + half), (512 - half, apex + half)])
s = 196
g = 28
yq = apex + half - 34
P["04e"] = icon(
    f'<path d="{roof}" fill="{INK}"/>'
    f'<path d="{rrect(512 - g / 2 - s, yq, s, s * 1.5, 30)}" fill="{A[2]}"/>'
    f'<path d="{rrect(512 + g / 2, yq, s, s * 1.5, 30)}" fill="{C[3]}"/>',
    PAPER,
    "04e",
)

# 05e: Albers en creatinina (cálido)
def albers(cols, bg, key, sizes=(760, 520, 280), drop_ratio=0.62):
    body = ""
    prev = (132, 132, 760)
    x, y, s0 = 512 - sizes[0] / 2, 512 - sizes[0] / 2, sizes[0]
    body += f'<path d="{rrect(x, y, s0, s0, s0 * 0.16)}" fill="{cols[0]}"/>'
    for i, s in enumerate(sizes[1:], 1):
        free = s0 - s
        nx = x + free / 2
        ny = y + free * drop_ratio  # más margen arriba que abajo
        body += f'<path d="{rrect(nx, ny, s, s, s * 0.16)}" fill="{cols[i]}"/>'
        x, y, s0 = nx, ny, s
    return icon(body, bg, key)

P["05e"] = albers([C[1], C[2], C[4]], C[0], "05e")
P["05f"] = albers([TEAL_MID, A[2], TEAL], TEAL_SOFT, "05f")
P["05g"] = albers([A[1], A[2], INK], "#fff", "05g", sizes=(720, 480, 240))
# 05h: anillos en marcha: discontinuo fuera, continuo dentro, centro lleno
def dashed_ring(x, y, s, t, dash, col):
    return (f'<rect x="{n(x + t / 2)}" y="{n(y + t / 2)}" width="{n(s - t)}" height="{n(s - t)}" rx="{n(s * 0.18)}" fill="none" '
            f'stroke="{col}" stroke-width="{n(t)}" stroke-dasharray="{dash}"/>')
P["05h"] = icon(
    dashed_ring(150, 150, 724, 52, "70 46", TEAL_MID)
    + f'<path d="{ring(262, 262, 500, 500, 100, 70)}" fill="{TEAL}" fill-rule="evenodd"/>'
    + f'<path d="{rrect(392, 392, 240, 240, 46)}" fill="{INK}"/>',
    PAPER,
    "05h",
)

# 06d: LH de tiras, extremos más redondos y almohadillas cuadradas
w = 132
H = 560
y0 = 512 - H / 2
Lw = 340
Hw = 420
gapLH = 64
x0 = 512 - (Lw + gapLH + Hw) / 2
r = 40
x1 = x0 + Lw + gapLH
P["06d"] = icon(
    f'<path d="{rrect(x0, y0, w, H, r)}{rrect(x0, y0 + H - w, Lw, w, r)}" fill="#fff"/>'
    f'<path d="{rrect(x0 + Lw - w, y0 + H - w, w, w, r)}" fill="{A[2]}"/>'
    f'<path d="{rrect(x1, y0, w, H, r)}{rrect(x1 + Hw - w, y0, w, H, r)}" fill="#fff"/>'
    f'<rect x="{n(x1 + w - 1)}" y="{n(512 - w / 2)}" width="{n(Hw - 2 * w + 2)}" height="{n(w)}" fill="{C[3]}"/>',
    INK,
    "06d",
)

# 07e: L fina + H negra, más juntas, blanco sobre verde azulado
F = 610
dL, wL, bL = typo.layout("L", F, wght=380, wdth=100)
dH, wH, bH = typo.layout("H", F, wght=900, wdth=100, x=wL - 14)
tw = bH[2] - bL[0]
capH = bH[3] - bH[1]
P["07e"] = icon(f'<g transform="translate({n(512 - tw / 2 - bL[0])} {n(512 + capH / 2)})"><path d="{dL} {dH}" fill="#fff"/></g>', TEAL, "07e")
# 07f: igual sobre tinta con L verde medio
P["07f"] = icon(f'<g transform="translate({n(512 - tw / 2 - bL[0])} {n(512 + capH / 2)})"><path d="{dL}" fill="{TEAL_MID}"/><path d="{dH}" fill="#fff"/></g>', INK, "07f")

for k, v in P.items():
    with open(os.path.join(OUT, f"{k}.svg"), "w", encoding="utf8") as f:
        f.write(v)

# rampa de palabra para 07
rows = []
y = 120
for label, per in [
    ("peso 250→900", [(250 + (900 - 250) * i / 11, 100) for i in range(12)]),
    ("peso 350→900", [(350 + (900 - 350) * i / 11, 100) for i in range(12)]),
    ("ancho 62→125", [(780, 62 + (125 - 62) * i / 11) for i in range(12)]),
    ("Latent 300 / Health 850", [(300, 100)] * 6 + [(850, 100)] * 6),
]:
    d, wdt, box = typo.layout("LatentHealth", 100, per_char=per, tracking=-0.01, x=20, baseline=y)
    rows.append(f'<path d="{d}" fill="{INK}"/><text x="{n(40 + wdt)}" y="{y}" font-size="16" font-family="monospace">{label}</text>')
    y += 130
with open(os.path.join(OUT, "rampa.svg"), "w", encoding="utf8") as f:
    f.write(svg(1100, y - 40, "".join(rows)))
print("ok", ",".join(P))
