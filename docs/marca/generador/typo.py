"""Texto a trazados con Archivo (fuente variable local) para los logotipos.

Instancia la fuente en (wght, wdth), aplica el kerning de GPOS (PairPos) y devuelve el
atributo d del trazado ya escalado, más las medidas útiles para componer.
"""
import os
from functools import lru_cache

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = {
    "archivo": os.path.join(HERE, "fonts", "archivo.ttf"),
    "chivo": os.path.join(HERE, "fonts", "chivomono.ttf"),
}


def _num(v):
    s = f"{v:.2f}"
    s = s.rstrip("0").rstrip(".") if "." in s else s
    return "0" if s in ("-0", "") else s


@lru_cache(None)
def instance(family="archivo", wght=700, wdth=100):
    f = TTFont(FONTS[family])
    loc = {"wght": wght}
    if any(a.axisTag == "wdth" for a in f["fvar"].axes):
        loc["wdth"] = wdth
    return instancer.instantiateVariableFont(f, loc)


def _kern_lookups(font):
    if "GPOS" not in font:
        return []
    gpos = font["GPOS"].table
    idx = set()
    for fr in gpos.FeatureList.FeatureRecord:
        if fr.FeatureTag == "kern":
            idx.update(fr.Feature.LookupListIndex)
    return [gpos.LookupList.Lookup[i] for i in sorted(idx)]


def kern(font, left, right):
    total = 0
    for lk in _kern_lookups(font):
        for st in lk.SubTable:
            if lk.LookupType == 9:
                st = st.ExtSubTable
            if getattr(st, "LookupType", 2) != 2 and lk.LookupType != 2:
                continue
            cov = st.Coverage.glyphs
            if left not in cov:
                continue
            if st.Format == 1:
                ps = st.PairSet[cov.index(left)]
                hit = next((r for r in ps.PairValueRecord if r.SecondGlyph == right), None)
                if hit is None:
                    continue
                v = hit.Value1
                total += (getattr(v, "XAdvance", 0) or 0) if v else 0
                break
            if st.Format == 2:
                c1 = st.ClassDef1.classDefs.get(left, 0)
                c2 = st.ClassDef2.classDefs.get(right, 0)
                v = st.Class1Record[c1].Class2Record[c2].Value1
                total += (getattr(v, "XAdvance", 0) or 0) if v else 0
                break
    return total


def layout(text, size, family="archivo", wght=700, wdth=100, tracking=0.0, x=0.0, baseline=0.0, per_char=None):
    """Devuelve (d, ancho, caja) del texto a `size` px de cuerpo.

    tracking en em (como letter-spacing de CSS, se añade tras cada letra salvo la última).
    per_char: lista opcional de (wght, wdth) por letra para variar la fuente dentro de la palabra.
    """
    cmds = []
    pen_x = x
    xmin = ymin = float("inf")
    xmax = ymax = float("-inf")
    names = []
    fonts = []
    for i, ch in enumerate(text):
        f = instance(family, *(per_char[i] if per_char else (wght, wdth)))
        fonts.append(f)
        names.append(f.getBestCmap()[ord(ch)])
    for i, (f, name) in enumerate(zip(fonts, names)):
        upm = f["head"].unitsPerEm
        s = size / upm
        gs = f.getGlyphSet()
        sp = SVGPathPen(gs, ntos=_num)
        tp = TransformPen(sp, (s, 0, 0, -s, pen_x, baseline))
        gs[name].draw(tp)
        cmds.append(sp.getCommands())
        bp = BoundsPen(gs)
        gs[name].draw(bp)
        if bp.bounds:
            bx0, by0, bx1, by1 = bp.bounds
            xmin = min(xmin, pen_x + bx0 * s)
            xmax = max(xmax, pen_x + bx1 * s)
            ymin = min(ymin, baseline - by1 * s)
            ymax = max(ymax, baseline - by0 * s)
        adv = f["hmtx"][name][0]
        if i + 1 < len(names):
            # kerning con la fuente de la letra izquierda (si varía, es una aproximación)
            adv += kern(f, name, names[i + 1])
            pen_x += adv * s + tracking * size
        else:
            pen_x += adv * s
    return " ".join(c for c in cmds if c), pen_x - x, (xmin, ymin, xmax, ymax)


def metrics(family="archivo", wght=700, wdth=100):
    f = instance(family, wght, wdth)
    os2 = f["OS/2"]
    upm = f["head"].unitsPerEm
    return {"cap": os2.sCapHeight / upm, "x": os2.sxHeight / upm}


def cap_height(size, family="archivo", wght=700, wdth=100):
    """Altura real de la H a ese cuerpo (la de OS/2 no varía con los ejes)."""
    _, _, (x0, y0, x1, y1) = layout("H", size, family, wght, wdth)
    return y1 - y0


if __name__ == "__main__":
    d, w, box = layout("LatentHealth", 100, wght=750, wdth=100, tracking=-0.01)
    print(round(w, 2), [round(v, 2) for v in box], len(d))
    print("cap H a 100:", round(cap_height(100, wght=750), 2))
