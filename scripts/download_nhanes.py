"""Descarga los ficheros públicos de NHANES (CDC) que usa el proyecto a data/raw/nhanes/.

- Analíticas, exploración y cuestionarios de las diez oleadas de 1999 a 2018, en
  data/raw/nhanes/<oleada>/.
- Mortalidad enlazada con el registro de defunciones de EE. UU. (seguimiento hasta el 31 de
  diciembre de 2019), en data/raw/nhanes/mortality/.

Los ficheros que ya existen no se vuelven a descargar. Unos 360 MB en total.

Uso:
    uv run python scripts/download_nhanes.py
"""

import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "raw" / "nhanes"
URL = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/{year}/DataFiles/{name}.xpt"
MORTALITY_URL = "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/datalinkage/linked_mortality/{name}"

SUFFIX = {
    "1999-2000": "",
    "2001-2002": "_B",
    "2003-2004": "_C",
    "2005-2006": "_D",
    "2007-2008": "_E",
    "2009-2010": "_F",
    "2011-2012": "_G",
    "2013-2014": "_H",
    "2015-2016": "_I",
    "2017-2018": "_J",
}
# Exploración y cuestionarios, con el mismo nombre en todas las oleadas. CDQ: dolor torácico y
# disnea; HUQ: salud percibida e ingresos; PFQ: dificultad para caminar; PAQ: actividad física.
COMMON = ("DEMO", "BMX", "BPX", "BPQ", "DIQ", "MCQ", "SMQ", "CDQ", "HUQ", "PFQ", "PAQ")
# Analíticas desde 2005: orina, bioquímica, HbA1c, colesterol total y HDL.
LABS = ("ALB_CR", "BIOPRO", "GHB", "TCHOL", "HDL")
# Antes de 2005 las analíticas tienen otros nombres (orina, bioquímica, HbA1c, lípidos).
OLD_LABS = {
    "1999-2000": ["LAB16", "LAB18", "LAB10", "LAB13"],
    "2001-2002": ["L16_B", "L40_B", "L10_B", "L13_B"],
    "2003-2004": ["L16_C", "L40_C", "L10_C", "L13_C"],
}
# Glucosa en ayunas (la mitad de la muestra, citada por la mañana) y horas de ayuno, desde 2005:
# para saber cuánta diabetes sin diagnosticar encuentra una glucosa capilar hecha en casa.
GLUCOSE = ("GLU", "FASTQX")
# Solo para el panel de sangre (2009-2018) y el NT-proBNP (sueros de 1999-2004, todo en SSBNP_A).
PANEL_ONLY = ("UCFLOW", "CBC", "KIQ_U")
EXTRA = {"1999-2000": ["SSBNP_A"]}


def cycle_files(cycle: str) -> list[str]:
    s = SUFFIX[cycle]
    names = [f"{n}{s}" for n in COMMON]
    names += OLD_LABS[cycle] if cycle in OLD_LABS else [f"{n}{s}" for n in LABS]
    if int(cycle[:4]) >= 2005:
        names += [f"{n}{s}" for n in GLUCOSE]
    if int(cycle[:4]) >= 2009:
        names += [f"{n}{s}" for n in PANEL_ONLY]
    return names + EXTRA.get(cycle, [])


def mortality_file(cycle: str) -> str:
    return f"NHANES_{cycle.replace('-', '_')}_MORT_2019_PUBLIC.dat"


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=180) as response:
        return response.read()


def main() -> None:
    for cycle in SUFFIX:
        directory = ROOT / cycle
        directory.mkdir(parents=True, exist_ok=True)
        for name in cycle_files(cycle):
            path = directory / f"{name}.xpt"
            if path.exists():
                continue
            print(f"Descargando {cycle}/{name}.xpt", flush=True)
            data = fetch(URL.format(year=cycle[:4], name=name))
            if not data.startswith(b"HEADER RECORD"):
                raise RuntimeError(f"{name}: la respuesta no es un fichero XPT")
            path.write_bytes(data)
    directory = ROOT / "mortality"
    directory.mkdir(parents=True, exist_ok=True)
    for cycle in SUFFIX:
        path = directory / mortality_file(cycle)
        if path.exists():
            continue
        print(f"Descargando mortality/{path.name}", flush=True)
        data = fetch(MORTALITY_URL.format(name=path.name))
        if len(data) < 100_000 or not data[:6].strip().isdigit():
            raise RuntimeError(f"{path.name}: la respuesta no es un fichero de mortalidad")
        path.write_bytes(data)
    print(f"Datos en {ROOT}")


if __name__ == "__main__":
    main()
