"""Variantes de logotipo para decidir: iceberg, gota, tiras integradas y peso con símbolo."""
import math
import os

import build as B
import typo
from geom import A, C, INK, TEAL, TEAL_MID, TEAL_SOFT, n, poly, pt, ring, rrect, svg

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out2")
os.makedirs(OUT, exist_ok=True)
c = B.CAP
WHITE = "#fff"


def save(name, content):
    with open(os.path.join(OUT, name + ".svg"), "w", encoding="utf8") as f:
        f.write(content)


# ---- 01 mono con esquinas más vivas
def sym_carta_mono(mode, c, key):
    bw, g, h, r = 0.5 * c, 0.16 * c, 1.02 * c, 0.05 * c
    top = -c - (h - c) / 2
    out = []
    for i in range(4):
        x = i * (bw + g)
        if i == 3:
            out.append(f'<path d="{rrect(x, top, bw, h, r)}"/>')
        else:
            t = [0.08, 0.15, 0.215][i] * c
            out.append(f'<path d="{ring(x, top, bw, h, r, t)}" fill-rule="evenodd"/>')
    return f'<g fill="currentColor">{"".join(out)}</g>', 4 * bw + 3 * g, top, top + h


save("01-mono-vivo", B.logotype(sym_carta_mono, "mono", "a", "t"))


# ---- 02 iceberg: rombo achatado (más ancho que alto) y versión con bloque de agua
def ice(mode, c, key, Rx=1.0, Ry=0.78, t_frac=0.44, block=False, stripes=False):
    lt, gap = 0.085 * c, 0.065 * c
    line_y = -c * 0.98
    t = t_frac * Ry  # altura de la punta
    top = line_y - t
    cx = Rx + (0 if block else 0.06 * c)
    cy = top + Ry
    k = Rx / Ry
    tip = poly([(cx, top), (cx + t * k, top + t), (cx - t * k, top + t)])
    y_cut = line_y + (0 if block else lt + gap)
    dy = y_cut - top
    half = dy * k
    sub = poly([(cx - half, y_cut), (cx + half, y_cut), (cx + Rx, cy), (cx, cy + Ry), (cx - Rx, cy)])
    W = 2 * cx
    bottom = cy + Ry
    fg = {"pos": INK, "neg": WHITE, "mono": "currentColor"}[mode]
    if block:
        pad_x = 0.0
        water = f'<rect x="{n(-0.0)}" y="{n(line_y, 2)}" width="{n(W, 2)}" height="{n(bottom - line_y + 0.0, 2)}" rx="{n(0.08 * c, 2)}"/>'
        if mode == "mono":
            body = f'<defs><mask id="k{key}"><rect x="-5" y="-200" width="400" height="400" fill="#fff"/><path d="{sub}" fill="#000"/></mask></defs><g fill="currentColor"><path d="{tip}"/><g mask="url(#k{key})">{water}</g></g>'
        else:
            body = f'<path d="{tip}" fill="{fg}"/><g fill="{TEAL}">{water}</g><path d="{sub}" fill="{WHITE if mode == "pos" else TEAL_MID}"/>'
        return body, W, top, bottom
    line = f'<rect x="0" y="{n(line_y, 2)}" width="{n(W, 2)}" height="{n(lt, 2)}"/>'
    if mode == "mono":
        if stripes:
            st = []
            yy = y_cut
            step = 0.13 * c
            while yy < bottom:
                st.append(f'<rect x="0" y="{n(yy, 2)}" width="{n(W, 2)}" height="{n(step * 0.55, 2)}"/>')
                yy += step
            body = f'<defs><clipPath id="s{key}"><path d="{sub}"/></clipPath></defs><g fill="currentColor"><path d="{tip}"/>{line}<g clip-path="url(#s{key})">{"".join(st)}</g></g>'
        else:
            body = f'<g fill="currentColor"><path d="{tip}"/>{line}<path d="{sub}"/></g>'
    else:
        body = f'<g fill="{fg}"><path d="{tip}"/>{line}</g><path d="{sub}" fill="{TEAL if mode == "pos" else TEAL_MID}"/>'
    return body, W, top, bottom


for mode in ("pos", "neg", "mono"):
    save(f"02-ancho-{mode}", B.logotype(lambda m, c, k: ice(m, c, k), mode, "b" + mode, "t", 0.42))
    save(f"02-bloque-{mode}", B.logotype(lambda m, c, k: ice(m, c, k, block=True), mode, "c" + mode, "t", 0.42))
save("02-rayas-mono", B.logotype(lambda m, c, k: ice(m, c, k, stripes=True), "mono", "d", "t", 0.42))


# ---- 03 gota: almohadilla verde claro en positivo
def gota_pos(mode, c, key, pad_fill=A[1]):
    g = B.GOTA
    h_units = (g["pad"][1] + g["pad"][3]) - (g["cy"] - g["R"] / math.sin(math.radians(g["ang"] / 2)))
    s = 1.62 * c / h_units
    x_min = g["cx"] - g["R"]
    bottom = 0.16 * c
    ox, oy = -x_min * s, bottom - (g["pad"][1] + g["pad"][3]) * s
    pad, dpath, tip, rr = B.gota_geom(s, ox, oy)
    padp = rrect(*pad, rr)
    body = (
        f'<defs><clipPath id="p{key}"><path d="{padp}"/></clipPath></defs>'
        f'<path d="{padp}" fill="{pad_fill}"/><path d="{dpath}" fill="{TEAL}"/><path d="{dpath}" fill="{INK}" clip-path="url(#p{key})"/>'
    )
    return body, (g["pad"][0] + g["pad"][2] - x_min) * s, tip[1], bottom


save("03-pos-a1", B.logotype(lambda m, c, k: gota_pos(m, c, k), "pos", "e", "t", 0.5))
save("03-pos-mid", B.logotype(lambda m, c, k: gota_pos(m, c, k, TEAL_MID), "pos", "f", "t", 0.5))


# ---- 06 integrada: la L y la H de la palabra hechas de tiras
def word_tiras(mode, x, baseline):
    fg = {"pos": INK, "neg": WHITE, "mono": "currentColor"}[mode]
    f = typo.instance("archivo", B.WGHT, B.WDTH)
    s = B.F / 1000
    text = "LatentHealth"
    # posiciones de cada letra con el kerning de la palabra
    xs = []
    pen = x
    names = [f.getBestCmap()[ord(ch)] for ch in text]
    for i, nm in enumerate(names):
        xs.append(pen)
        adv = f["hmtx"][nm][0]
        if i + 1 < len(names):
            adv += typo.kern(f, nm, names[i + 1])
            pen += adv * s + B.TRACK * B.F
    parts = []
    for i, ch in enumerate(text):
        if ch in "LH":
            continue
        d, _, _ = typo.layout(ch, B.F, wght=B.WGHT, wdth=B.WDTH, x=xs[i], baseline=baseline)
        parts.append(d)
    out = f'<path d="{" ".join(parts)}" fill="{fg}"/>'
    # L: tallo 75–240, pie 0–137 hasta 587; H: tallos 75–240 y 531–695, travesaño 282–418
    def X(u, i):
        return xs[i] + u * s

    def Y(u):
        return baseline - u * s

    L, H = 0, 6
    stem = f'M{n(X(75, L), 2)} {n(Y(687), 2)}H{n(X(240, L), 2)}V{n(Y(137), 2)}H{n(X(587 - 140, L), 2)}V{n(Y(0), 2)}H{n(X(75, L), 2)}Z'
    toe = rrect(X(587 - 137, L), Y(137), 137 * s, 137 * s, 0)
    hst = f'M{n(X(75, H), 2)} {n(Y(687), 2)}H{n(X(240, H), 2)}V{n(Y(0), 2)}H{n(X(75, H), 2)}Z M{n(X(531, H), 2)} {n(Y(687), 2)}H{n(X(695, H), 2)}V{n(Y(0), 2)}H{n(X(531, H), 2)}Z'
    bar = (X(240, H), Y(418), (531 - 240) * s, 136 * s)
    if mode == "mono":
        t = 0.03 * B.F
        out += f'<g fill="currentColor"><path d="{stem}"/><path d="{hst}"/><path d="{ring(bar[0] - 0.3, bar[1], bar[2] + 0.6, bar[3], 0, t)}{ring(X(587 - 137, L) + 0.0, Y(137), 137 * s, 137 * s, 0, t)}" fill-rule="evenodd"/></g>'
    else:
        out += f'<g fill="{fg}"><path d="{stem}"/><path d="{hst}"/></g><path d="{toe}" fill="{A[2]}"/><rect x="{n(bar[0] - 0.3, 2)}" y="{n(bar[1], 2)}" width="{n(bar[2] + 0.6, 2)}" height="{n(bar[3], 2)}" fill="{C[3]}"/>'
    _, _, box = typo.layout(text, B.F, wght=B.WGHT, wdth=B.WDTH, tracking=B.TRACK, x=x, baseline=baseline)
    return out, box


for mode in ("pos", "neg", "mono"):
    save(f"06-integrada-{mode}", B.logotype(B.sym_none, mode, "g" + mode, "t", 0, word_body=word_tiras))


# ---- 07 peso con símbolo: el par LH (fina + negra) delante de la palabra en rampa
def sym_lh(mode, c, key):
    fg = {"pos": INK, "neg": WHITE, "mono": "currentColor"}[mode]
    size = 1.42 * B.F
    dL, dH, bL, bH = B.mono_lh(size)
    capH = bH[3] - bH[1]
    # centrado en la banda de mayúsculas
    base = -c / 2 + capH / 2
    dL, dH, bL, bH = B.mono_lh(size, x=-bL[0], baseline=base)
    return f'<path d="{dL} {dH}" fill="{fg}"/>', bH[2], base - capH, base


for mode in ("pos", "neg", "mono"):
    save(f"07-lh-{mode}", B.logotype(sym_lh, mode, "h" + mode, "t", 0.7, word_body=B.word_peso))

names = sorted(f[:-4] for f in os.listdir(OUT) if f.endswith(".svg"))
cells = "".join(
    f'<div class="p {"k" if "neg" in nm else "w"}"><img src="{nm}.svg" style="zoom:.42"><small>{nm}</small></div>' for nm in names
)
with open(os.path.join(OUT, "_v.html"), "w", encoding="utf8") as f:
    f.write(f"""<!doctype html><meta charset=utf-8><style>body{{margin:0;padding:16px;display:flex;flex-wrap:wrap;gap:12px;font:11px monospace}}
.p{{display:flex;flex-direction:column;gap:6px;align-items:center;justify-content:center;width:420px;height:130px}}
.w{{outline:1px solid #e3e8e6}} .k{{background:#0d2226;color:#aaa}}</style>{cells}""")
print(len(names))
