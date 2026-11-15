"""Genera web/site/logos.html: las siete propuestas en orden, con el mismo tamaño de palabra en todas."""
import os
import re
import sys

SITE = r"C:\dev\LatentHealth\web\site"
LOGOS = os.path.join(SITE, "img", "logos")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(SITE, "logos.html")
SCALE = 0.27  # px de pantalla por unidad del SVG del logotipo (la palabra va a cuerpo 100)

P = [
    ("01", "carta", "Carta",
     "Parte del logo actual: las cuatro casillas de la carta de albúmina, de amarillo a verde azulado, porque leer la tira en casa es comparar su color con esta escala."),
    ("02", "iceberg", "Iceberg",
     "Lo que da síntomas es solo la punta; la tira mide lo que queda bajo la línea del agua, y cuanto más hondo, más avanza la escala de color."),
    ("03", "gota", "Gota",
     "Donde la gota toca la almohadilla aparece el color: con una gota de orina en casa se ve lo que estaba latente."),
    ("04", "casa", "Casa",
     "La almohadilla bajo un tejado, porque la prueba se hace en casa y sin cita; en negativo es el botón de la marca, tinta con su cuadrado lima."),
    ("05", "ritmo", "Ritmo",
     "Medir varias veces: cada medida se asienta dentro de la anterior y la duda se estrecha hasta el resultado, en cuadrados anidados a lo Albers con la escala de la tira."),
    ("06", "tiras", "Tiras",
     "La L y la H están hechas de tiras y llevan las dos almohadillas de la prueba: albúmina en el pie de la L y creatinina en el travesaño de la H."),
    ("07", "peso", "Peso",
     "La palabra pasa de un trazo fino a uno negro sin cambiar de letra (Archivo, del peso 300 al 900): lo latente se hace visible."),
]


def size(path):
    head = open(path, encoding="utf8").read(400)
    w, h = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', head).groups()
    return float(w), float(h)


def img(src, w, h, alt, cls=""):
    c = f' class="{cls}"' if cls else ""
    return f'<img{c} src="{src}" width="{round(w)}" height="{round(h)}" alt="{alt}" />'


sections = []
for num, slug, name, frase in P:
    base = f"img/logos/{num}-{slug}"
    lw, lh = size(os.path.join(LOGOS, f"{num}-{slug}-logotipo.svg"))
    nw, nh = size(os.path.join(LOGOS, f"{num}-{slug}-logotipo-negativo.svg"))
    mw, mh = size(os.path.join(LOGOS, f"{num}-{slug}-mono.svg"))
    sections.append(
        f"""
      <section class="prop" id="p{num}" aria-labelledby="t{num}">
        <div class="txt">
          <p class="num">{num}</p>
          <h2 id="t{num}">{name}</h2>
          <p class="frase">{frase}</p>
        </div>
        <figure class="cell icono">
          <a href="{base}-icono.svg">{img(base + "-icono.svg", 184, 184, f"Icono de app de la propuesta {name}")}</a>
          <figcaption>Icono de app</figcaption>
        </figure>
        <figure class="cell inicio">
          <div class="pantalla clara">{img(base + "-icono.svg", 32, 32, "")}<span>LatentHealth</span></div>
          <div class="pantalla oscura">{img(base + "-icono.svg", 32, 32, "")}<span>LatentHealth</span></div>
          <figcaption>A 32 px</figcaption>
        </figure>
        <figure class="cell logo blanco">
          <a href="{base}-logotipo.svg">{img(base + "-logotipo.svg", lw * SCALE, lh * SCALE, f"Logotipo {name} sobre blanco")}</a>
          <figcaption>Sobre blanco</figcaption>
        </figure>
        <figure class="cell logo tinta">
          <a href="{base}-logotipo-negativo.svg">{img(base + "-logotipo-negativo.svg", nw * SCALE, nh * SCALE, f"Logotipo {name} sobre tinta")}</a>
          <figcaption>Sobre tinta</figcaption>
        </figure>
        <figure class="cell logo uno">
          <a href="{base}-mono.svg">{img(base + "-mono.svg", mw * SCALE, mh * SCALE, f"Logotipo {name} en un solo color")}</a>
          <figcaption>Un color</figcaption>
        </figure>
      </section>"""
    )

html = f"""<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="description" content="Siete propuestas de logo para LatentHealth: icono de app, logotipo sobre blanco y sobre tinta y versión de un color." />
    <title>Logos de LatentHealth</title>
    <link rel="icon" type="image/svg+xml" href="favicon.svg" />
    <style>
      /* Propuestas de logo · paleta oficial «La tira»: blanco bote, escala de albúmina, salmón y tinta. */
      @font-face {{
        font-family: "Archivo";
        font-style: normal;
        font-display: swap;
        font-weight: 100 900;
        font-stretch: 62% 125%;
        src: url("fonts/archivo-latin-wdth-normal.woff2") format("woff2-variations");
        unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329,
          U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
      }}
      @font-face {{
        font-family: "Archivo";
        font-style: normal;
        font-display: swap;
        font-weight: 100 900;
        font-stretch: 62% 125%;
        src: url("fonts/archivo-latin-ext-wdth-normal.woff2") format("woff2-variations");
        unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+1E00-1E9F, U+1EF2-1EFF, U+2020,
          U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF;
      }}
      @font-face {{
        font-family: "Chivo Mono";
        font-style: normal;
        font-display: swap;
        font-weight: 100 900;
        src: url("fonts/chivo-mono-latin-wght-normal.woff2") format("woff2-variations");
        unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329,
          U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
      }}
      :root {{
        --paper: #ffffff;
        --ink: #0d2226;
        --ink-soft: rgb(13 34 38 / 0.68);
        --line: rgb(13 34 38 / 0.14);
        --yellow: #f6ec9b;
        --lime: #c8de6e;
        --green: #5fbe8c;
        --teal: #0b7774;
        --salmon: #f29a78;
        --sans: "Archivo", "Segoe UI", Arial, sans-serif;
        --mono: "Chivo Mono", "Cascadia Mono", Consolas, monospace;
      }}
      *,
      *::before,
      *::after {{
        box-sizing: border-box;
      }}
      html {{
        background: var(--paper);
      }}
      body {{
        margin: 0;
        background: var(--paper);
        color: var(--ink);
        font: 400 16px/1.5 var(--sans);
        -webkit-font-smoothing: antialiased;
      }}
      h1,
      h2,
      p,
      figure {{
        margin: 0;
      }}
      img {{
        display: block;
        max-width: 100%;
        height: auto;
      }}
      a {{
        color: inherit;
      }}
      :focus-visible {{
        outline: 3px solid var(--teal);
        outline-offset: 3px;
      }}
      .wrap {{
        max-width: 1600px;
        margin-inline: auto;
        padding: 40px clamp(16px, 3vw, 40px) 56px;
      }}

      /* Cabecera */
      .head {{
        display: grid;
        gap: 12px;
        padding-bottom: 28px;
        border-bottom: 1.5px solid var(--ink);
      }}
      .tag {{
        display: flex;
        align-items: center;
        gap: 10px;
        font: 500 13px/1 var(--mono);
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }}
      .tag::before {{
        content: "";
        width: 11px;
        height: 11px;
        background: var(--lime);
        box-shadow: inset 0 0 0 1px rgb(13 34 38 / 0.18);
      }}
      h1 {{
        font: 700 clamp(30px, 3.4vw, 46px) / 1.04 var(--sans);
        font-stretch: 125%;
        letter-spacing: -0.02em;
      }}
      .lede {{
        max-width: 62em;
        color: var(--ink-soft);
        text-wrap: pretty;
      }}

      /* Una fila por propuesta */
      .prop {{
        display: grid;
        grid-template-columns: 250px 184px 112px repeat(3, minmax(0, 1fr));
        gap: 18px;
        align-items: stretch;
        padding: 22px 0;
        border-bottom: 1px solid var(--line);
      }}
      .txt {{
        display: grid;
        align-content: start;
        gap: 6px;
      }}
      .num {{
        font: 500 13px/1 var(--mono);
        letter-spacing: 0.06em;
        color: var(--teal);
      }}
      h2 {{
        font: 700 26px/1.1 var(--sans);
        font-stretch: 125%;
        letter-spacing: -0.015em;
      }}
      .frase {{
        font-size: 15px;
        line-height: 1.45;
        color: var(--ink-soft);
        text-wrap: pretty;
      }}
      .cell {{
        display: grid;
        grid-template-rows: 1fr auto;
        gap: 8px;
        min-width: 0;
      }}
      figcaption {{
        font: 500 11px/1 var(--mono);
        letter-spacing: 0.07em;
        text-transform: uppercase;
        color: var(--ink-soft);
      }}
      .icono a {{
        display: block;
        width: 184px;
        height: 184px;
      }}
      /* un filo que sigue la forma del icono: sin él, un icono blanco desaparece sobre la página */
      .icono img {{
        filter: drop-shadow(0 0 0.75px rgb(13 34 38 / 0.5));
      }}
      .inicio {{
        grid-template-rows: 1fr 1fr auto;
      }}
      .pantalla {{
        display: grid;
        justify-items: center;
        align-content: center;
        gap: 5px;
        border-radius: 10px;
        font: 500 11px/1 var(--sans);
      }}
      .pantalla img {{
        width: 32px;
        height: 32px;
      }}
      .clara {{
        background: #e6ebe9;
        color: var(--ink);
      }}
      .oscura {{
        background: #24292b;
        color: #fff;
      }}
      .logo > a {{
        display: grid;
        place-items: center;
        padding: 18px;
        border-radius: 4px;
      }}
      .blanco > a,
      .uno > a {{
        box-shadow: inset 0 0 0 1px var(--line);
      }}
      .tinta > a {{
        background: var(--ink);
      }}

      /* Pantallas medianas: texto arriba, imágenes debajo */
      @media (max-width: 1399px) {{
        .prop {{
          grid-template-columns: 184px 112px repeat(3, minmax(0, 1fr));
        }}
        .txt {{
          grid-column: 1 / -1;
        }}
        .frase {{
          max-width: 60em;
        }}
      }}
      @media (max-width: 980px) {{
        .prop {{
          grid-template-columns: 184px 1fr;
        }}
        .logo {{
          grid-column: 1 / -1;
        }}
        .logo > a {{
          min-height: 120px;
        }}
        .inicio {{
          max-width: 140px;
        }}
      }}
      @media (max-width: 520px) {{
        .prop {{
          grid-template-columns: 1fr 112px;
        }}
        .icono a {{
          width: 100%;
          height: auto;
          max-width: 184px;
        }}
      }}
    </style>
  </head>
  <body>
    <main class="wrap">
      <header class="head">
        <p class="tag">LatentHealth · Marca</p>
        <h1>Siete ideas para el logo</h1>
        <p class="lede">
          Cada propuesta es un concepto distinto. De cada una: el icono de la app, el mismo icono a 32 px como en la
          pantalla de inicio de un móvil, el logotipo sobre blanco y sobre tinta y la versión de un color. Paleta de la
          tira y Archivo ancha, con la palabra pasada a trazados. Pulsa cualquier imagen para abrir su SVG.
        </p>
      </header>{"".join(sections)}
    </main>
  </body>
</html>
"""
with open(OUT, "w", encoding="utf8", newline="\n") as f:
    f.write(html)
print("ok", OUT, len(html))
