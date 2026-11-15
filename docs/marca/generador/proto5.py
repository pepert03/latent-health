"""Variantes de logotipo: iceberg con bloque de agua; tiras y peso con símbolo delante."""
import os

import build as B
import typo
from geom import GREEN, INK, LIME, SALMON, TEAL, YELLOW, n, poly, ring, rrect

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out5")
os.makedirs(OUT, exist_ok=True)
W = "#fff"


def save(name, content):
    with open(os.path.join(OUT, name + ".svg"), "w", encoding="utf8") as f:
        f.write(content)


# 02 con bloque de agua: rectángulo redondeado desde la línea hacia abajo, rombo dentro
def ice_block(mode, c, key, R=0.62, t=0.36, pad=0.16, rad=0.16):
    R, t, pad, rad = R * c, t * c, pad * c, rad * c
    W_ = 2 * R + 2 * pad
    line_y = -c * 0.86
    top = line_y - t
    cx = W_ / 2
    cy = top + R
    gap = 0.06 * c
    tip = poly([(cx, top), (cx + t - gap, top + t - gap), (cx - t + gap, top + t - gap)])
    y_cut = line_y + gap
    half = y_cut - top
    sub = poly([(cx - half, y_cut), (cx + half, y_cut), (cx + R, cy), (cx, cy + R), (cx - R, cy)])
    bottom = cy + R + pad
    water = rrect(0, line_y, W_, bottom - line_y, rad)
    if mode == "mono":
        body = (
            f'<path d="{tip}" fill="currentColor"/>'
            f'<path d="{water}{sub}" fill="currentColor" fill-rule="evenodd"/>'
        )
    else:
        wcol = INK if mode == "pos" else TEAL
        tipc = TEAL if mode == "pos" else W
        body = (
            f'<defs>{B.gradient("g" + key, 0, y_cut, 0, cy + R, B.SCALE_STOPS)}</defs>'
            f'<path d="{tip}" fill="{tipc}"/><path d="{water}" fill="{wcol}"/><path d="{sub}" fill="url(#g{key})"/>'
        )
    return body, W_, top, bottom


for m in ("pos", "neg", "mono"):
    save(f"02-bloque-{m}", B.logotype(ice_block, m, "b" + m, "t", 0.42))


# 06 con monograma de tiras delante y la palabra normal
def sym_lh(mode, c, key):
    p = B.LH
    k = 1.3 * c / p["H"]
    Hh = p["H"] * k
    top = -c / 2 - Hh / 2
    q = B.lh_parts(0, top, p["w"] * k, Hh, p["Lw"] * k, p["Hw"] * k, p["gap"] * k, p["r"] * k)
    b = q["bar"]
    fg = B.FG[mode]
    if mode == "mono":
        t = 0.07 * c
        w = p["w"] * k
        body = (
            f'<defs><clipPath id="l{key}"><path d="{q["Lpad"]}"/></clipPath></defs>'
            f'<g fill="currentColor"><path d="{rrect(0, top, w, Hh, p["r"] * k)}{rrect(0, top + Hh - w, (p["Lw"] - p["w"]) * k + p["r"] * k, w, 0)}"/>'
            f'<path d="{q["H"]}"/><path d="{ring(b[0] - 0.5, b[1], b[2] + 1, b[3], 0, t)}" fill-rule="evenodd"/></g>'
            f'<path d="{q["Lpad"]}" fill="none" stroke="currentColor" stroke-width="{n(2 * t, 2)}" clip-path="url(#l{key})"/>'
        )
    else:
        body = (
            f'<path d="{q["L"]}" fill="{fg}"/><path d="{q["Lpad"]}" fill="{GREEN}"/><path d="{q["H"]}" fill="{fg}"/>'
            f'<rect x="{n(b[0] - 0.5, 2)}" y="{n(b[1], 2)}" width="{n(b[2] + 1, 2)}" height="{n(b[3], 2)}" fill="{SALMON}"/>'
        )
    return body, q["width"], top, top + Hh


for m in ("pos", "neg", "mono"):
    save(f"06-mono+palabra-{m}", B.logotype(sym_lh, m, "c" + m, "t", 0.5))


# 07 con el par LH (fina + negra) delante de la palabra en rampa
def sym_pair(mode, c, key):
    size = 1.0 * B.F
    dL, dH, bL, bH = B.pair_lh(size)
    capH = bH[3] - bH[1]
    dL, dH, bL, bH = B.pair_lh(size, x=-bL[0], baseline=0)
    return f'<path d="{dL} {dH}" fill="{B.FG[mode]}"/>', bH[2], -capH, 0


for m in ("pos", "neg", "mono"):
    save(f"07-par+palabra-{m}", B.logotype(sym_pair, m, "d" + m, "t", 0.9, word_body=B.word_peso))


# 07 con el icono (baldosa lima) delante
def sym_tile(mode, c, key):
    S = 1.5 * c
    top = -c / 2 - S / 2
    size = 0.44 * S / 0.687 * 0.98
    dL, dH, bL, bH = B.pair_lh(size)
    tw, capH = bH[2] - bL[0], bH[3] - bH[1]
    sq = B.squircle(S, x0=0, y0=top)
    tx, ty = S / 2 - tw / 2 - bL[0], top + S / 2 + capH / 2
    dL, dH, _, _ = B.pair_lh(size, x=tx, baseline=ty)
    if mode == "mono":
        return f'<path d="{sq}{dL} {dH}" fill="currentColor" fill-rule="evenodd"/>', S, top, top + S
    return f'<path d="{sq}" fill="{LIME}"/><path d="{dL} {dH}" fill="{INK}"/>', S, top, top + S


for m in ("pos", "neg", "mono"):
    save(f"07-baldosa+palabra-{m}", B.logotype(sym_tile, m, "e" + m, "t", 0.45, word_body=B.word_peso))

names = sorted(f[:-4] for f in os.listdir(OUT) if f.endswith(".svg"))
cells = "".join(f'<div class="p {"k" if "neg" in nm else "w"}"><img src="{nm}.svg" style="zoom:.4"><small>{nm}</small></div>' for nm in names)
with open(os.path.join(OUT, "_v.html"), "w", encoding="utf8") as f:
    f.write(
        f"""<!doctype html><meta charset=utf-8><style>body{{margin:0;padding:16px;display:grid;grid-template-columns:repeat(3,440px);gap:12px;font:11px monospace}}
.p{{display:flex;flex-direction:column;gap:6px;align-items:center;justify-content:center;height:120px}}
.w{{outline:1px solid #e3e8e6}} .k{{background:#0d2226;color:#aaa}}</style>{cells}"""
    )
print(len(names))
