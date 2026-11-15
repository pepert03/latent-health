"""Geometría común: superelipse del icono, números compactos, formas básicas."""
import math

# Ficha de estilo «La tira» (paleta oficial)
INK = "#0d2226"  # tinta de etiqueta
PAPER = "#ffffff"  # blanco bote
YELLOW = "#f6ec9b"  # albúmina 10
LIME = "#c8de6e"  # albúmina 30
GREEN = "#5fbe8c"  # albúmina 80
TEAL = "#0b7774"  # albúmina 150
SALMON = "#f29a78"  # creatinina 100
A = [YELLOW, LIME, GREEN, TEAL]  # la escala: motivo central
# solo para la página de presentación (líneas finas), no para los logos
LINE = "#d6dedb"
# compatibilidad con los prototipos antiguos
TEAL_MID = LIME
TEAL_SOFT = PAPER
PLASTIC = PAPER
C = [PAPER, PAPER, SALMON, SALMON, SALMON]


def n(v, nd=1):
    s = f"{v:.{nd}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def pt(p, nd=1):
    return f"{n(p[0], nd)} {n(p[1], nd)}"


def squircle(S=1024.0, ex=5.0, N=96, x0=0.0, y0=0.0):
    """Superelipse |x|^ex + |y|^ex = 1 (forma de icono de iOS) como curvas de Bézier."""
    a = S / 2
    pts = []
    for i in range(N):
        t = 2 * math.pi * i / N
        c, s = math.cos(t), math.sin(t)
        r = (abs(c) ** ex + abs(s) ** ex) ** (-1 / ex)
        pts.append((x0 + a + a * r * c, y0 + a + a * r * s))
    d = [f"M{pt(pts[0])}"]
    for i in range(N):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % N], pts[(i + 2) % N]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d.append(f"C{pt(c1)} {pt(c2)} {pt(p2)}")
    return "".join(d) + "Z"


def rrect(x, y, w, h, r):
    """Rectángulo redondeado como trazado (para poder combinarlo en un solo d)."""
    r = min(r, w / 2, h / 2)
    if r <= 0:
        return f"M{n(x)} {n(y)}h{n(w)}v{n(h)}h{n(-w)}Z"
    k = 0.5523 * r
    return (
        f"M{n(x + r)} {n(y)}H{n(x + w - r)}"
        f"C{n(x + w - r + k)} {n(y)} {n(x + w)} {n(y + r - k)} {n(x + w)} {n(y + r)}"
        f"V{n(y + h - r)}"
        f"C{n(x + w)} {n(y + h - r + k)} {n(x + w - r + k)} {n(y + h)} {n(x + w - r)} {n(y + h)}"
        f"H{n(x + r)}"
        f"C{n(x + r - k)} {n(y + h)} {n(x)} {n(y + h - r + k)} {n(x)} {n(y + h - r)}"
        f"V{n(y + r)}"
        f"C{n(x)} {n(y + r - k)} {n(x + r - k)} {n(y)} {n(x + r)} {n(y)}Z"
    )


def ring(x, y, w, h, r, t):
    """Marco de grosor t (borde exterior en x, y, w, h) como un solo trazado con hueco (evenodd)."""
    return rrect(x, y, w, h, r) + rrect(x + t, y + t, w - 2 * t, h - 2 * t, max(r - t, 0))


def poly(points):
    return "M" + "L".join(pt(p) for p in points) + "Z"


def drop(cx, cy, R, tip_angle_deg=64.0):
    """Gota con la punta hacia arriba: círculo de radio R centrado en (cx, cy) y punta recta."""
    half = math.radians(tip_angle_deg / 2)
    d = R / math.sin(half)  # distancia del centro a la punta
    tip = (cx, cy - d)
    # puntos de tangencia: ángulo desde el eje vertical hacia arriba = 90° - half
    phi = math.pi / 2 - half
    tl = (cx - R * math.cos(math.pi / 2 - phi), cy - R * math.sin(math.pi / 2 - phi))
    tr = (cx + R * math.cos(math.pi / 2 - phi), cy - R * math.sin(math.pi / 2 - phi))
    # arco grande por abajo de tr a tl (sentido horario en pantalla: sweep=1)
    return f"M{pt(tip)}L{pt(tr)}A{n(R)} {n(R)} 0 1 1 {pt(tl)}Z", tip


def svg(w, h, body, title=None, extra=""):
    t = f"<title>{title}</title>" if title else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n(w)} {n(h)}" width="{n(w)}" height="{n(h)}"{extra}>'
        f"{t}{body}</svg>\n"
    )
