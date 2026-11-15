"""Iceberg en el logotipo: horizonte largo, o la palabra apoyada en la línea del agua."""
import os

import build as B
from geom import GREEN, INK, LIME, TEAL, YELLOW, n, poly

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out6")
os.makedirs(OUT, exist_ok=True)
W = "#fff"


def save(name, content):
    with open(os.path.join(OUT, name + ".svg"), "w", encoding="utf8") as f:
        f.write(content)


def ice_parts(cx, top, Rx, Ry, t, line_y, lt, gap):
    k = Rx / Ry
    cy = top + Ry
    te = line_y - gap - top
    tip = poly([(cx, top), (cx + te * k, top + te), (cx - te * k, top + te)])
    y_cut = line_y + lt + gap
    half = (y_cut - top) * k
    sub = poly([(cx - half, y_cut), (cx + half, y_cut), (cx + Rx, cy), (cx, cy + Ry), (cx - Rx, cy)])
    return tip, sub, y_cut, cy + Ry


def colors(mode):
    return dict(
        tip={"pos": INK, "neg": W, "mono": "currentColor"}[mode],
        line={"pos": INK, "neg": LIME, "mono": "currentColor"}[mode],
        stops=B.SCALE_STOPS if mode == "neg" else [(0, LIME), (0.45, GREEN), (1, TEAL)],
    )


def stripes(key, sub, x0, x1, y0, y1, c):
    step, out, yy = 0.15 * c, [], y0
    while yy < y1:
        out.append(f'<rect x="{n(x0, 2)}" y="{n(yy, 2)}" width="{n(x1 - x0, 2)}" height="{n(step * 0.56, 2)}"/>')
        yy += step
    return f'<defs><clipPath id="s{key}"><path d="{sub}"/></clipPath></defs><g clip-path="url(#s{key})" fill="currentColor">{"".join(out)}</g>'


# (a) horizonte largo
def ice_long(mode, c, key, Rx=0.9, Ry=0.78, t=0.36, ext=0.42):
    Rx, Ry, t, ext = Rx * c, Ry * c, t * c, ext * c
    lt, gap = 0.08 * c, 0.06 * c
    line_y = -c + 0.04 * c
    top = line_y - t
    cx = ext + Rx
    tip, sub, y_cut, y_bot = ice_parts(cx, top, Rx, Ry, t, line_y, lt, gap)
    Wd = 2 * Rx + 2 * ext
    col = colors(mode)
    line = f'<rect x="0" y="{n(line_y, 2)}" width="{n(Wd, 2)}" height="{n(lt, 2)}" fill="{col["line"]}"/>'
    if mode == "mono":
        body = f'<path d="{tip}" fill="currentColor"/>{line}' + stripes(key, sub, 0, Wd, y_cut, y_bot, c)
    else:
        body = f'<defs>{B.gradient("g" + key, 0, y_cut, 0, y_bot, col["stops"])}</defs><path d="{tip}" fill="{col["tip"]}"/>{line}<path d="{sub}" fill="url(#g{key})"/>'
    return body, Wd, top, y_bot


for m in ("pos", "neg", "mono"):
    save(f"02-largo-{m}", B.logotype(ice_long, m, "a" + m, "t", 0.3))


# (b) la palabra apoyada en la línea: la línea sigue por debajo de toda la palabra
def lockup_line(mode, key):
    c = B.CAP
    col = colors(mode)
    wb, box = B.word(mode, 0, 0)
    Rx, Ry = 0.62 * c, 0.62 * c
    lt, gap = 0.075 * c, 0.07 * c
    line_y = 0.16 * c  # bajo la línea base
    t = 0.5 * c
    top = line_y - t
    cx = Rx
    tip, sub, y_cut, y_bot = ice_parts(cx, top, Rx, Ry, t, line_y, lt, gap)
    wx = 2 * Rx + 0.28 * c - box[0]
    Wd = wx + box[2]
    line = f'<rect x="0" y="{n(line_y, 2)}" width="{n(Wd, 2)}" height="{n(lt, 2)}" fill="{col["line"]}"/>'
    if mode == "mono":
        sym = f'<path d="{tip}" fill="currentColor"/>{line}' + stripes(key, sub, 0, 2 * Rx, y_cut, y_bot, c)
    else:
        sym = f'<defs>{B.gradient("g" + key, 0, y_cut, 0, y_bot, col["stops"])}</defs><path d="{tip}" fill="{col["tip"]}"/>{line}<path d="{sub}" fill="url(#g{key})"/>'
    y0, y1 = min(top, box[1]), y_bot
    m = 2
    content = f'<g transform="translate({m} {n(m - y0, 2)})">{sym}<g transform="translate({n(wx, 2)} 0)">{wb}</g></g>'
    extra = ' color="#0d2226"' if mode == "mono" else ""
    from geom import svg

    return svg(Wd + 2 * m, y1 - y0 + 2 * m, content, "t", extra)


for m in ("pos", "neg", "mono"):
    save(f"02-linea-{m}", lockup_line(m, "b" + m))

names = sorted(f[:-4] for f in os.listdir(OUT) if f.endswith(".svg"))
cells = "".join(f'<div class="p {"k" if "neg" in nm else "w"}"><img src="{nm}.svg" style="zoom:.4"><small>{nm}</small></div>' for nm in names)
with open(os.path.join(OUT, "_v.html"), "w", encoding="utf8") as f:
    f.write(
        f"""<!doctype html><meta charset=utf-8><style>body{{margin:0;padding:16px;display:grid;grid-template-columns:repeat(3,440px);gap:12px;font:11px monospace}}
.p{{display:flex;flex-direction:column;gap:6px;align-items:center;justify-content:center;height:130px}}
.w{{outline:1px solid #e3e8e6}} .k{{background:#0d2226;color:#aaa}}</style>{cells}"""
    )
print(len(names))
