"""Hoja de prueba a tamaño real (32 y 16 px) ampliada x4 sin suavizado, para ver los píxeles."""
import os
import subprocess
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
folder, keys, out = sys.argv[1], sys.argv[2].split(","), sys.argv[3]
cells = "".join(
    f'<div class="c"><div class="hs l"><img src="{k}.svg" width="32" height="32"></div>'
    f'<div class="hs d"><img src="{k}.svg" width="32" height="32"></div>'
    f'<div class="hs l"><img src="{k}.svg" width="16" height="16"></div>'
    f'<div class="hs w"><img src="{k}.svg" width="60" height="60"></div></div>'
    for k in keys
)
html = f"""<!doctype html><meta charset=utf-8><style>
body{{margin:0;padding:8px;background:#fff;display:flex;gap:8px;flex-wrap:wrap}}
.c{{display:flex;gap:4px;align-items:center}}
.hs{{display:grid;place-items:center;width:44px;height:44px}}
.w{{width:70px;height:70px;background:#dfe5e3}}
.l{{background:#dfe5e3}} .d{{background:#2b2f33}}
</style>{cells}"""
p = os.path.join(HERE, folder, "_small.html")
with open(p, "w", encoding="utf8") as f:
    f.write(html)
raw = os.path.join(HERE, "shots", "_small_raw.png")
url = "file:///" + p.replace("\\", "/")
subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "shot.py"), url, raw, "1240", str(90 * ((len(keys) + 3) // 4)), "--wait=300"], check=True)
im = Image.open(raw)
im = im.resize((im.width * 3, im.height * 3), Image.NEAREST)
im.save(out)
print("ok", out, im.size)
