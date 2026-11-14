"""Descarga los otros datos abiertos que usa el proyecto, a data/raw/.

- **PhysioNet/CinC Challenge 2017** (physionet.org, licencia Open Data Commons Attribution):
  8.528 registros de un electrocardiógrafo de bolsillo (una derivación, 300 Hz, de 9 a 60 s)
  etiquetados como ritmo normal, fibrilación auricular, otro ritmo o ruido. Unos 95 MB.
- **Muestra del ensayo PREDIMED** (paquete de R compareGroups 4.9.1, en el archivo de CRAN,
  licencia GPL): 6.324 participantes españoles de alto riesgo cardiovascular con seguimiento de
  infarto, ictus o muerte cardiovascular. Solo se guarda el fichero de datos. Unos 3,5 MB.

Los ficheros que ya existen no se vuelven a descargar.

Uso:
    uv run python scripts/download_open_data.py
"""

import tarfile
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "raw"
PHYSIONET = "https://physionet.org/files/challenge-2017/1.0.0/{name}?download"
COMPAREGROUPS = "https://cran.r-project.org/src/contrib/Archive/compareGroups/compareGroups_4.9.1.tar.gz"


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "python-urllib"})
    with urllib.request.urlopen(request, timeout=600) as response:
        return response.read()


def physionet() -> None:
    directory = ROOT / "physionet2017"
    directory.mkdir(parents=True, exist_ok=True)
    labels = directory / "REFERENCE-v3.csv"
    if not labels.exists():
        print("Descargando REFERENCE-v3.csv", flush=True)
        labels.write_bytes(fetch(PHYSIONET.format(name="REFERENCE-v3.csv")))
    records = directory / "training2017"
    if not records.exists() or not any(records.glob("*.mat")):
        print("Descargando training2017.zip (unos 95 MB)", flush=True)
        data = fetch(PHYSIONET.format(name="training2017.zip"))
        records.mkdir(exist_ok=True)
        with zipfile.ZipFile(BytesIO(data)) as archive:
            for member in archive.infolist():
                name = Path(member.filename).name
                if name.endswith((".mat", ".hea")):  # solo señales y cabeceras, sin rutas del archivo
                    (records / name).write_bytes(archive.read(member))
    print(f"PhysioNet 2017: {len(list(records.glob('*.mat')))} registros en {records}")


def predimed() -> None:
    directory = ROOT / "predimed"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "predimed.rda"
    if not path.exists():
        print("Descargando compareGroups_4.9.1.tar.gz (3,5 MB)", flush=True)
        with tarfile.open(fileobj=BytesIO(fetch(COMPAREGROUPS)), mode="r:gz") as archive:
            member = archive.extractfile("compareGroups/data/predimed.rda")
            if member is None:
                raise RuntimeError("El paquete no trae data/predimed.rda")
            path.write_bytes(member.read())
    print(f"PREDIMED: {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    physionet()
    predimed()
