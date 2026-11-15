"""Vista rápida de todos los ficheros generados (icono, logotipos y versión de un color)."""
import os
import sys

folder = sys.argv[1]
names = sorted({f.rsplit("-", 1)[0] if f.endswith("-icono.svg") else None for f in os.listdir(folder)} - {None})
rows = []
for b in names:
    rows.append(
        f'<div class="r"><b>{b}</b><img class="ic" src="{b}-icono.svg">'
        f'<div class="hs"><img src="{b}-icono.svg" width="32" height="32"></div>'
        f'<div class="p w"><img class="lg" src="{b}-logotipo.svg"></div>'
        f'<div class="p k"><img class="lg" src="{b}-logotipo-negativo.svg"></div>'
        f'<div class="p w"><img class="lg" src="{b}-mono.svg"></div></div>'
    )
html = f"""<!doctype html><meta charset=utf-8><style>
body{{margin:0;padding:20px;font:13px system-ui;background:#fff}}
.r{{display:flex;gap:16px;align-items:center;margin-bottom:14px}}
b{{width:80px}}
.ic{{width:120px;height:120px}}
.hs{{display:grid;place-items:center;width:56px;height:56px;background:#dfe5e3}}
.p{{display:grid;place-items:center;width:360px;height:120px}}
.w{{background:#fff;outline:1px solid #e3e8e6}} .k{{background:#0d2226}}
.lg{{zoom:.34}}
</style>{''.join(rows)}"""
with open(os.path.join(folder, "_preview.html"), "w", encoding="utf8") as f:
    f.write(html)
print("ok", len(names))
