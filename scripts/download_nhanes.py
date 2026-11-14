"""Descarga los ficheros públicos de NHANES (CDC) que usa el proyecto a data/raw/nhanes/<oleada>/.

Los ficheros que ya existen no se vuelven a descargar. Unos 220 MB en total.

Uso:
    uv run python scripts/download_nhanes.py
"""

import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "raw" / "nhanes"
URL = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/{year}/DataFiles/{name}.xpt"

PANEL = ("DEMO", "ALB_CR", "UCFLOW", "BIOPRO", "GHB", "TCHOL", "HDL", "CBC", "BMX", "BPX", "BPQ", "DIQ", "MCQ", "SMQ", "KIQ_U")
CYCLES = {
    # Albuminuria (dos muestras por persona) y panel de sangre.
    "2009-2010": (2009, [f"{n}_F" for n in PANEL]),
    "2011-2012": (2011, [f"{n}_G" for n in PANEL]),
    "2013-2014": (2013, [f"{n}_H" for n in PANEL]),
    "2015-2016": (2015, [f"{n}_I" for n in PANEL]),
    "2017-2018": (2017, [f"{n}_J" for n in PANEL]),
    # NT-proBNP (sueros guardados de 1999-2004, todo en SSBNP_A) con su historia y orina.
    "1999-2000": (1999, ["DEMO", "SSBNP_A", "LAB16", "LAB18", "LAB10", "BMX", "BPX", "BPQ", "DIQ", "MCQ", "SMQ"]),
    "2001-2002": (2001, ["DEMO_B", "L16_B", "L40_B", "L10_B", "BMX_B", "BPX_B", "BPQ_B", "DIQ_B", "MCQ_B", "SMQ_B"]),
    "2003-2004": (2003, ["DEMO_C", "L16_C", "L40_C", "L10_C", "BMX_C", "BPX_C", "BPQ_C", "DIQ_C", "MCQ_C", "SMQ_C"]),
}


def main() -> None:
    for cycle, (year, names) in CYCLES.items():
        directory = ROOT / cycle
        directory.mkdir(parents=True, exist_ok=True)
        for name in names:
            path = directory / f"{name}.xpt"
            if path.exists():
                continue
            print(f"Descargando {cycle}/{name}.xpt")
            with urllib.request.urlopen(URL.format(year=year, name=name), timeout=120) as response:
                data = response.read()
            if not data.startswith(b"HEADER RECORD"):
                raise RuntimeError(f"{name}: la respuesta no es un fichero XPT")
            path.write_bytes(data)
    print(f"Datos en {ROOT}")


if __name__ == "__main__":
    main()
