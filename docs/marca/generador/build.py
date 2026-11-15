"""Genera las siete propuestas de logo de LatentHealth (paleta oficial «La tira»).

Por propuesta, en web/site/img/logos/:
  NN-nombre-icono.svg               icono de app 1024 x 1024 con esquinas de superelipse (iOS)
  NN-nombre-logotipo.svg            símbolo + palabra, para fondo blanco
  NN-nombre-logotipo-negativo.svg   símbolo + palabra, para fondo tinta
  NN-nombre-mono.svg                un solo color (currentColor; tinta por defecto)
La palabra va en trazados sacados de Archivo (woff2 local, 700 a 125 % de ancho) con su kerning.
"""
import math
import os
import sys

import typo
from geom import A, GREEN, INK, LIME, PAPER, SALMON, TEAL, YELLOW, drop, n, poly, pt, ring, rrect, squircle, svg

OUT = sys.argv[1] if len(sys.argv) > 1 else r"C:\dev\LatentHealth\web\site\img\logos"
os.makedirs(OUT, exist_ok=True)

SQ = squircle()
F = 100  # cuerpo de la palabra en el logotipo (unidades del SVG)
WGHT, WDTH, TRACK = 700, 125, -0.01  # Archivo ancha, como los titulares de «La tira»
WHITE = "#fff"
CAP = typo.cap_height(F, wght=WGHT, wdth=WDTH)  # altura de la H (≈ 68,7)
FG = {"pos": INK, "neg": WHITE, "mono": "currentColor"}


def icon(body, bg, key, title, defs=""):
    return svg(
        1024,
        1024,
        f'<defs><clipPath id="m{key}"><path d="{SQ}"/></clipPath>{defs}</defs>'
        f'<g clip-path="url(#m{key})"><rect width="1024" height="1024" fill="{bg}"/>{body}</g>',
        title=title,
    )


def gradient(gid, x1, y1, x2, y2, stops):
    s = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in stops)
    return f'<linearGradient id="{gid}" x1="{n(x1, 2)}" y1="{n(y1, 2)}" x2="{n(x2, 2)}" y2="{n(y2, 2)}" gradientUnits="userSpaceOnUse">{s}</linearGradient>'


SCALE_STOPS = [(0, YELLOW), (0.36, LIME), (0.7, GREEN), (1, TEAL)]


def word(mode, x=0.0, baseline=0.0):
    d, w, box = typo.layout("LatentHealth", F, wght=WGHT, wdth=WDTH, tracking=TRACK, x=x, baseline=baseline)
    return f'<path d="{d}" fill="{FG[mode]}"/>', box


def logotype(sym, mode, key, title, gap=0.55, word_body=None, margin=2.0):
    """Símbolo con la línea base en y = 0 y la palabra a su derecha, en un SVG ajustado."""
    c = CAP
    body, sw, top, bottom = sym(mode, c, key) if sym else ("", 0, -c, 0)
    wb, box = (word_body or word)(mode, 0, 0)
    wx = (sw + gap * c - box[0]) if sw > 0 else -box[0]
    y_top, y_bot = min(top, box[1]), max(bottom, box[3])
    W = wx + box[2] + 2 * margin
    H = y_bot - y_top + 2 * margin
    content = f'<g transform="translate({n(margin, 2)} {n(margin - y_top, 2)})">{body}<g transform="translate({n(wx, 2)} 0)">{wb}</g></g>'
    extra = ' color="#0d2226"' if mode == "mono" else ""
    return svg(W, H, content, title=title, extra=extra)


# ==========================================================================================
# 01 · Carta — las cuatro casillas de la escala de albúmina (parte del logo actual)
# ==========================================================================================
def icon_carta():
    w, g, h, r = 156, 36, 500, 36
    x0 = 512 - (4 * w + 3 * g) / 2
    body = "".join(f'<path d="{rrect(x0 + i * (w + g), 512 - h / 2, w, h, r)}" fill="{A[i]}"/>' for i in range(4))
    return icon(body, INK, "01", "LatentHealth · Carta")


def sym_carta(mode, c, key):
    bw, g, h = 0.5 * c, 0.16 * c, 1.02 * c
    top = -c - (h - c) / 2
    out = []
    r = 0.11 * c
    for i in range(4):
        x = i * (bw + g)
        if mode == "mono":
            # un color: cada casilla es una trama de rayas más gruesas cuanto más oscuro el color
            if i == 3:
                out.append(f'<path d="{rrect(x, top, bw, h, r)}"/>')
                continue
            t = 0.05 * c
            pitch = 0.13 * c
            fill = [0.26, 0.5, 0.74][i]
            lines, yy = [], top + t + pitch * (1 - fill) / 2
            while yy < top + h - t:
                lines.append(f'<rect x="{n(x, 2)}" y="{n(yy, 2)}" width="{n(bw, 2)}" height="{n(pitch * fill, 2)}"/>')
                yy += pitch
            out.append(
                f'<clipPath id="c{key}{i}"><path d="{rrect(x, top, bw, h, r)}"/></clipPath>'
                f'<path d="{ring(x, top, bw, h, r, t)}" fill-rule="evenodd"/><g clip-path="url(#c{key}{i})">{"".join(lines)}</g>'
            )
        else:
            out.append(f'<path d="{rrect(x, top, bw, h, r)}" fill="{A[i]}"/>')
    body = "".join(out)
    if mode == "mono":
        body = f'<g fill="currentColor">{body}</g>'
    return body, 4 * bw + 3 * g, top, top + h


# ==========================================================================================
# 02 · Iceberg — la punta se ve; debajo de la línea, la parte que mide la tira
# ==========================================================================================
def iceberg(cx, top, R, t, line_y, line_t, gap):
    """Punta (triángulo) y parte sumergida (rombo recortado bajo la línea, con hueco)."""
    cy = top + R
    t_eff = line_y - gap - top  # la punta acaba un hueco antes de la línea
    tip = poly([(cx, top), (cx + t_eff, top + t_eff), (cx - t_eff, top + t_eff)])
    y_cut = line_y + line_t + gap
    dy = y_cut - top
    half = dy if dy <= R else 2 * R - dy
    sub = poly([(cx - half, y_cut), (cx + half, y_cut), (cx + R, cy), (cx, cy + R), (cx - R, cy)])
    return tip, sub, y_cut, cy + R


def icon_iceberg():
    yl, lt, gap = 404, 46, 26
    R, t = 300, 172
    top = yl - t
    tip, sub, y_cut, y_bot = iceberg(512, top, R, t, yl, lt, gap)
    defs = gradient("g02", 0, y_cut, 0, y_bot, SCALE_STOPS)
    body = f'<rect y="{yl}" width="1024" height="{lt}" fill="{LIME}"/><path d="{tip}" fill="{WHITE}"/><path d="{sub}" fill="url(#g02)"/>'
    return icon(body, INK, "02", "LatentHealth · Iceberg", defs)


def sym_iceberg(mode, c, key):
    # rombo algo achatado y horizonte largo: así se lee como mar y no como una gema
    Rx, Ry, t, ext = 0.9 * c, 0.78 * c, 0.36 * c, 0.42 * c
    lt, gap = 0.08 * c, 0.06 * c
    line_y = -c + 0.04 * c  # la línea del agua, casi a la altura de las mayúsculas
    top = line_y - t
    cx = ext + Rx
    k = Rx / Ry
    cy = top + Ry
    te = line_y - gap - top
    tip = poly([(cx, top), (cx + te * k, top + te), (cx - te * k, top + te)])
    y_cut = line_y + lt + gap
    half = (y_cut - top) * k
    sub = poly([(cx - half, y_cut), (cx + half, y_cut), (cx + Rx, cy), (cx, cy + Ry), (cx - Rx, cy)])
    y_bot = cy + Ry
    W = 2 * Rx + 2 * ext
    if mode == "mono":
        # lo sumergido, en rayas horizontales: a tamaño pequeño se lee como un tono más claro
        step, stripes, yy = 0.15 * c, [], y_cut
        while yy < y_bot:
            stripes.append(f'<rect x="0" y="{n(yy, 2)}" width="{n(W, 2)}" height="{n(step * 0.56, 2)}"/>')
            yy += step
        body = (
            f'<defs><clipPath id="s{key}"><path d="{sub}"/></clipPath></defs>'
            f'<g fill="currentColor"><path d="{tip}"/><rect x="0" y="{n(line_y, 2)}" width="{n(W, 2)}" height="{n(lt, 2)}"/>'
            f'<g clip-path="url(#s{key})">{"".join(stripes)}</g></g>'
        )
    else:
        stops = SCALE_STOPS if mode == "neg" else [(0, LIME), (0.45, GREEN), (1, TEAL)]
        line_col = INK if mode == "pos" else LIME
        tip_col = INK if mode == "pos" else WHITE
        body = (
            f'<defs>{gradient("g" + key, 0, y_cut, 0, y_bot, stops)}</defs>'
            f'<path d="{tip}" fill="{tip_col}"/><rect x="0" y="{n(line_y, 2)}" width="{n(W, 2)}" height="{n(lt, 2)}" fill="{line_col}"/>'
            f'<path d="{sub}" fill="url(#g{key})"/>'
        )
    return body, W, top, y_bot


# ==========================================================================================
# 03 · Gota — donde la gota toca la almohadilla aparece el color
# ==========================================================================================
GOTA = dict(pad=(420, 420, 400, 400), cx=450, cy=450, R=180, ang=60, rr=48)


def gota_geom(scale=1.0, ox=0.0, oy=0.0):
    g = GOTA
    px, py, pw, ph = g["pad"]
    pad = (ox + px * scale, oy + py * scale, pw * scale, ph * scale)
    dpath, tip = drop(ox + g["cx"] * scale, oy + g["cy"] * scale, g["R"] * scale, g["ang"])
    return pad, dpath, tip, g["rr"] * scale


def gota_box():
    g = GOTA
    tip_y = g["cy"] - g["R"] / math.sin(math.radians(g["ang"] / 2))
    return g["cx"] - g["R"], tip_y, g["pad"][0] + g["pad"][2], g["pad"][1] + g["pad"][3]


def icon_gota():
    x0, y0, x1, y1 = gota_box()
    pad, dpath, tip, rr = gota_geom(1.0, 512 - (x0 + x1) / 2, 512 - (y0 + y1) / 2)
    padp = rrect(*pad, rr)
    defs = f'<clipPath id="p03"><path d="{padp}"/></clipPath>'
    body = f'<path d="{padp}" fill="{WHITE}"/><path d="{dpath}" fill="{YELLOW}"/><path d="{dpath}" fill="{GREEN}" clip-path="url(#p03)"/>'
    return icon(body, TEAL, "03", "LatentHealth · Gota", defs)


def sym_gota(mode, c, key):
    x0, y0, x1, y1 = gota_box()
    s = 1.72 * c / (y1 - y0)
    bottom = 0.17 * c
    pad, dpath, tip, rr = gota_geom(s, -x0 * s, bottom - y1 * s)
    padp = rrect(*pad, rr)
    defs = f'<clipPath id="p{key}"><path d="{padp}"/></clipPath>'
    if mode == "mono":
        st = 0.075 * c
        body = (
            f'<defs>{defs}<clipPath id="d{key}"><path d="{dpath}"/></clipPath></defs>'
            f'<path d="{padp}" fill="none" stroke="currentColor" stroke-width="{n(2 * st, 2)}" clip-path="url(#p{key})"/>'
            f'<path d="{dpath}" fill="none" stroke="currentColor" stroke-width="{n(2 * st, 2)}" clip-path="url(#d{key})"/>'
            f'<path d="{dpath}" fill="currentColor" clip-path="url(#p{key})"/>'
        )
    elif mode == "pos":
        body = f'<defs>{defs}</defs><path d="{padp}" fill="{LIME}"/><path d="{dpath}" fill="{TEAL}"/><path d="{dpath}" fill="{INK}" clip-path="url(#p{key})"/>'
    else:
        body = f'<defs>{defs}</defs><path d="{padp}" fill="{WHITE}"/><path d="{dpath}" fill="{YELLOW}"/><path d="{dpath}" fill="{GREEN}" clip-path="url(#p{key})"/>'
    return body, (x1 - x0) * s, tip[1], bottom


# ==========================================================================================
# 04 · Casa — la almohadilla, bajo techo
# ==========================================================================================
def casa_parts(cx, apex, half, t, s, sq_top, r):
    k = t * math.sqrt(2)
    roof = poly([(cx, apex), (cx + half, apex + half), (cx + half - k, apex + half), (cx, apex + k), (cx - half + k, apex + half), (cx - half, apex + half)])
    return roof, rrect(cx - s / 2, sq_top, s, s, r)


CASA = dict(apex=176, half=372, t=132, s=344, r=40)


def icon_casa():
    p = CASA
    roof, sq = casa_parts(512, p["apex"], p["half"], p["t"], p["s"], p["apex"] + p["half"] - 10, p["r"])
    return icon(f'<path d="{roof}" fill="{INK}"/><path d="{sq}" fill="{LIME}"/>', PAPER, "04", "LatentHealth · Casa")


def sym_casa(mode, c, key):
    p = CASA
    sq_top = p["apex"] + p["half"] - 10
    total = sq_top + p["s"] - p["apex"]
    k = 1.56 * c / total
    top = -total * k
    roof, sq = casa_parts(p["half"] * k, top, p["half"] * k, p["t"] * k, p["s"] * k, top + (sq_top - p["apex"]) * k, p["r"] * k)
    sq_col = {"pos": TEAL, "neg": LIME, "mono": "currentColor"}[mode]
    body = f'<path d="{roof}" fill="{FG[mode]}"/><path d="{sq}" fill="{sq_col}"/>'
    return body, 2 * p["half"] * k, top, 0.0


# ==========================================================================================
# 05 · Ritmo — cada medida se asienta dentro de la anterior (cuadrados a lo Albers)
# ==========================================================================================
def albers(x, y, s0, rel, drop_ratio=0.62):
    out = [(x, y, s0)]
    for r in rel[1:]:
        s = r * s0
        px, py, ps = out[-1]
        free = ps - s
        out.append((px + free / 2, py + free * drop_ratio, s))
    return out


def icon_ritmo():
    sq = albers(132, 132, 760, (1.0, 0.684, 0.368))
    cols = [LIME, GREEN, TEAL]
    body = "".join(f'<path d="{rrect(x, y, s, s, s * 0.16)}" fill="{cols[i]}"/>' for i, (x, y, s) in enumerate(sq))
    return icon(body, YELLOW, "05", "LatentHealth · Ritmo")


def sym_ritmo(mode, c, key):
    S = 1.44 * c
    top = -c / 2 - S / 2
    sq = albers(0, top, S, (1.0, 0.74, 0.48, 0.22))
    if mode == "mono":
        t = 0.075 * c
        parts = [f'<path d="{ring(x, y, s, s, s * 0.16, t)}" fill-rule="evenodd"/>' for (x, y, s) in sq[:3]]
        x, y, s = sq[3]
        parts.append(f'<path d="{rrect(x, y, s, s, s * 0.16)}"/>')
        body = f'<g fill="currentColor">{"".join(parts)}</g>'
    else:
        body = "".join(f'<path d="{rrect(x, y, s, s, s * 0.16)}" fill="{A[i]}"/>' for i, (x, y, s) in enumerate(sq))
    return body, S, top, top + S


# ==========================================================================================
# 06 · Tiras — la L y la H hechas de tiras, con las dos almohadillas de la prueba
# ==========================================================================================
def lh_parts(x0, y0, w, H, Lw, Hw, gap, r):
    x1 = x0 + Lw + gap
    return dict(
        L=rrect(x0, y0, w, H, r) + rrect(x0, y0 + H - w, Lw, w, r),
        Lpad=rrect(x0 + Lw - w, y0 + H - w, w, w, r),
        H=rrect(x1, y0, w, H, r) + rrect(x1 + Hw - w, y0, w, H, r),
        bar=(x1 + w, y0 + H / 2 - w / 2, Hw - 2 * w, w),
        width=Lw + gap + Hw,
    )


LH = dict(w=132, H=560, Lw=340, Hw=420, gap=64, r=40)


def icon_tiras():
    p = LH
    total = p["Lw"] + p["gap"] + p["Hw"]
    q = lh_parts(512 - total / 2, 512 - p["H"] / 2, p["w"], p["H"], p["Lw"], p["Hw"], p["gap"], p["r"])
    b = q["bar"]
    body = (
        f'<path d="{q["L"]}" fill="{WHITE}"/><path d="{q["Lpad"]}" fill="{GREEN}"/><path d="{q["H"]}" fill="{WHITE}"/>'
        f'<rect x="{n(b[0] - 1)}" y="{n(b[1])}" width="{n(b[2] + 2)}" height="{n(b[3])}" fill="{SALMON}"/>'
    )
    return icon(body, INK, "06", "LatentHealth · Tiras")


def sym_tiras(mode, c, key):
    """El monograma de tiras delante de la palabra."""
    p = LH
    k = 1.3 * c / p["H"]
    Hh = p["H"] * k
    top = -c / 2 - Hh / 2
    q = lh_parts(0, top, p["w"] * k, Hh, p["Lw"] * k, p["Hw"] * k, p["gap"] * k, p["r"] * k)
    b = q["bar"]
    if mode == "mono":
        # en un color, las almohadillas quedan huecas
        t = 0.07 * c
        w = p["w"] * k
        body = (
            f'<defs><clipPath id="l{key}"><path d="{q["Lpad"]}"/></clipPath></defs>'
            f'<g fill="currentColor"><path d="{rrect(0, top, w, Hh, p["r"] * k)}{rrect(0, top + Hh - w, (p["Lw"] - p["w"]) * k + p["r"] * k, w, 0)}"/>'
            f'<path d="{q["H"]}"/><path d="{ring(b[0] - 0.5, b[1], b[2] + 1, b[3], 0, t)}" fill-rule="evenodd"/></g>'
            f'<path d="{q["Lpad"]}" fill="none" stroke="currentColor" stroke-width="{n(2 * t, 2)}" clip-path="url(#l{key})"/>'
        )
    else:
        fg = FG[mode]
        body = (
            f'<path d="{q["L"]}" fill="{fg}"/><path d="{q["Lpad"]}" fill="{GREEN}"/><path d="{q["H"]}" fill="{fg}"/>'
            f'<rect x="{n(b[0] - 0.5, 2)}" y="{n(b[1], 2)}" width="{n(b[2] + 1, 2)}" height="{n(b[3], 2)}" fill="{SALMON}"/>'
        )
    return body, q["width"], top, top + Hh


def word_tiras(mode, x=0.0, baseline=0.0):
    """La palabra con la L y la H construidas como tiras (mismas medidas que las de Archivo)."""
    f = typo.instance("archivo", WGHT, WDTH)
    s = F / 1000
    text = "LatentHealth"
    names = [f.getBestCmap()[ord(ch)] for ch in text]
    xs, pen = [], x
    for i, nm in enumerate(names):
        xs.append(pen)
        if i + 1 < len(names):
            pen += (f["hmtx"][nm][0] + typo.kern(f, nm, names[i + 1])) * s + TRACK * F
    rest = []
    for i, ch in enumerate(text):
        if ch not in "LH":
            d, _, _ = typo.layout(ch, F, wght=WGHT, wdth=WDTH, x=xs[i], baseline=baseline)
            rest.append(d)
    m = glyph_lh()
    X = lambda u, i: xs[i] + u * s  # noqa: E731
    Y = lambda u: baseline - u * s  # noqa: E731
    iL, iH = text.index("L"), text.index("H")
    stem = f'M{n(X(m["Lx0"], iL), 2)} {n(Y(m["cap"]), 2)}H{n(X(m["Lx1"], iL), 2)}V{n(Y(m["Lfoot"]), 2)}H{n(X(m["Lx2"] - m["Lfoot"], iL), 2)}V{n(Y(0), 2)}H{n(X(m["Lx0"], iL), 2)}Z'
    toe = (X(m["Lx2"] - m["Lfoot"], iL), Y(m["Lfoot"]), m["Lfoot"] * s, m["Lfoot"] * s)
    hst = (
        f'M{n(X(m["Hx0"], iH), 2)} {n(Y(m["cap"]), 2)}H{n(X(m["Hx1"], iH), 2)}V{n(Y(0), 2)}H{n(X(m["Hx0"], iH), 2)}Z'
        f'M{n(X(m["Hx2"], iH), 2)} {n(Y(m["cap"]), 2)}H{n(X(m["Hx3"], iH), 2)}V{n(Y(0), 2)}H{n(X(m["Hx2"], iH), 2)}Z'
    )
    bar = (X(m["Hx1"], iH), Y(m["Hb1"]), (m["Hx2"] - m["Hx1"]) * s, (m["Hb1"] - m["Hb0"]) * s)
    fg = FG[mode]
    out = f'<path d="{" ".join(rest)}" fill="{fg}"/><path d="{stem}{hst}" fill="{fg}"/>'
    if mode == "mono":
        t = 0.034 * F
        out += (
            f'<path d="{ring(toe[0], toe[1], toe[2], toe[3], 0, t)}{ring(bar[0] - 0.3, bar[1], bar[2] + 0.6, bar[3], 0, t)}" '
            f'fill="currentColor" fill-rule="evenodd"/>'
        )
    else:
        out += (
            f'<rect x="{n(toe[0], 2)}" y="{n(toe[1], 2)}" width="{n(toe[2], 2)}" height="{n(toe[3], 2)}" fill="{GREEN}"/>'
            f'<rect x="{n(bar[0] - 0.3, 2)}" y="{n(bar[1], 2)}" width="{n(bar[2] + 0.6, 2)}" height="{n(bar[3], 2)}" fill="{SALMON}"/>'
        )
    _, _, box = typo.layout(text, F, wght=WGHT, wdth=WDTH, tracking=TRACK, x=x, baseline=baseline)
    return out, box


def glyph_lh():
    """Medidas de la L y la H de Archivo en la instancia del logotipo (unidades de la fuente)."""
    from fontTools.pens.recordingPen import RecordingPen

    f = typo.instance("archivo", WGHT, WDTH)
    gs = f.getGlyphSet()

    def coords(ch):
        rp = RecordingPen()
        gs[f.getBestCmap()[ord(ch)]].draw(rp)
        xs = sorted({round(p[0]) for _, a in rp.value for p in a})
        ys = sorted({round(p[1]) for _, a in rp.value for p in a})
        return xs, ys

    lx, ly = coords("L")
    hx, hy = coords("H")
    return dict(Lx0=lx[0], Lx1=lx[1], Lx2=lx[2], Lfoot=ly[1], cap=ly[-1], Hx0=hx[0], Hx1=hx[1], Hx2=hx[2], Hx3=hx[3], Hb0=hy[1], Hb1=hy[2])


# ==========================================================================================
# 07 · Peso — la palabra pasa de fina a negra: lo latente se hace visible
# ==========================================================================================
RAMP = [(300 + (900 - 300) * i / 11, WDTH) for i in range(12)]


def pair_lh(size, x=0.0, baseline=0.0, wl=380, wh=900, overlap=0.02):
    dL, wL, bL = typo.layout("L", size, wght=wl, wdth=WDTH, x=x, baseline=baseline)
    dH, wH, bH = typo.layout("H", size, wght=wh, wdth=WDTH, x=x + wL - overlap * size, baseline=baseline)
    return dL, dH, bL, bH


def icon_peso():
    size = 448
    dL, dH, bL, bH = pair_lh(size)
    tw, capH = bH[2] - bL[0], bH[3] - bH[1]
    body = f'<g transform="translate({n(512 - tw / 2 - bL[0])} {n(512 + capH / 2)})"><path d="{dL} {dH}" fill="{INK}"/></g>'
    return icon(body, LIME, "07", "LatentHealth · Peso")


def word_peso(mode, x=0.0, baseline=0.0):
    d, w, box = typo.layout("LatentHealth", F, per_char=RAMP, tracking=TRACK, x=x, baseline=baseline)
    return f'<path d="{d}" fill="{FG[mode]}"/>', box


def sym_peso(mode, c, key):
    """El icono (baldosa lima con el par LH) como símbolo delante de la palabra."""
    S = 1.5 * c
    top = -c / 2 - S / 2
    size = 0.44 * S / 0.687 * 0.98
    dL, dH, bL, bH = pair_lh(size)
    tw, capH = bH[2] - bL[0], bH[3] - bH[1]
    sq = squircle(S, x0=0, y0=top)
    dL, dH, _, _ = pair_lh(size, x=S / 2 - tw / 2 - bL[0], baseline=top + S / 2 + capH / 2)
    if mode == "mono":
        return f'<path d="{sq}{dL} {dH}" fill="currentColor" fill-rule="evenodd"/>', S, top, top + S
    return f'<path d="{sq}" fill="{LIME}"/><path d="{dL} {dH}" fill="{INK}"/>', S, top, top + S


CONCEPTS = [
    dict(num="01", slug="carta", icon=icon_carta, sym=sym_carta),
    dict(num="02", slug="iceberg", icon=icon_iceberg, sym=sym_iceberg, gap=0.3),
    dict(num="03", slug="gota", icon=icon_gota, sym=sym_gota, gap=0.5),
    dict(num="04", slug="casa", icon=icon_casa, sym=sym_casa, gap=0.45),
    dict(num="05", slug="ritmo", icon=icon_ritmo, sym=sym_ritmo, gap=0.5),
    dict(num="06", slug="tiras", icon=icon_tiras, sym=sym_tiras, gap=0.5),
    dict(num="07", slug="peso", icon=icon_peso, sym=sym_peso, gap=0.45, word_body=word_peso),
]


def build(out=OUT):
    for cpt in CONCEPTS:
        base = f'{cpt["num"]}-{cpt["slug"]}'
        name = cpt["slug"].capitalize()
        kw = dict(gap=cpt.get("gap", 0.55), word_body=cpt.get("word_body"))
        files = {
            "icono": cpt["icon"](),
            "logotipo": logotype(cpt["sym"], "pos", cpt["num"] + "p", f"LatentHealth · {name}", **kw),
            "logotipo-negativo": logotype(cpt["sym"], "neg", cpt["num"] + "n", f"LatentHealth · {name} · negativo", **kw),
            "mono": logotype(cpt["sym"], "mono", cpt["num"] + "m", f"LatentHealth · {name} · un color", **kw),
        }
        for suf, content in files.items():
            with open(os.path.join(out, f"{base}-{suf}.svg"), "w", encoding="utf8", newline="\n") as fh:
                fh.write(content)
        print(base, {k: len(v) for k, v in files.items()})


if __name__ == "__main__":
    build()
