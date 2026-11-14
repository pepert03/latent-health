"""Descarga los otros datos abiertos que usa el proyecto, a data/raw/.

- **PhysioNet/CinC Challenge 2017** (physionet.org, licencia Open Data Commons Attribution):
  8.528 registros de un electrocardiógrafo de bolsillo (una derivación, 300 Hz, de 9 a 60 s)
  etiquetados como ritmo normal, fibrilación auricular, otro ritmo o ruido. Unos 95 MB.
- **Muestra del ensayo PREDIMED** (paquete de R compareGroups 4.4.6, en el archivo de CRAN,
  licencia GPL): 6.324 participantes españoles de alto riesgo cardiovascular con seguimiento de
  infarto, ictus o muerte cardiovascular. Solo se guarda el fichero de datos. La versión 4.9.1
  ya no lo trae. Unos 3,5 MB.
- **ECG y sonido cardíaco con ecocardiograma** (zenodo.org/records/16934966, CC-BY 4.0): 620
  personas de dos hospitales de Wuhan con la fracción de eyección medida por ecocardiograma y
  30 s de ECG de una derivación y fonocardiograma en cuatro focos, con un Eko DUO. 363 MB.
- **MUSIC** (physionet.org, licencia ODbL): tabla clínica de 992 pacientes con insuficiencia
  cardíaca de ocho hospitales españoles, con mortalidad a cuatro años. Solo la tabla (0,3 MB);
  los Holter ocupan 90 GB y no se descargan.
- **Intervalos entre latidos** (physionet.org, ODC-BY): chf2db (29 personas con insuficiencia
  cardíaca) y nsr2db (54 en ritmo sinusal normal), 24 h cada una. Unos 18 MB.

Los ficheros que ya existen no se vuelven a descargar.

Uso:
    uv run python scripts/download_open_data.py
"""

import hashlib
import tarfile
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "raw"
PHYSIONET = "https://physionet.org/files/challenge-2017/1.0.0/{name}?download"
COMPAREGROUPS = "https://cran.r-project.org/src/contrib/Archive/compareGroups/compareGroups_4.4.6.tar.gz"
ZENODO = "https://zenodo.org/records/16934966/files/{name}?download=1"
HFREF_FILES = {
    "HFrEF_5_folds.zip": "a84763772612104afb2c2b4bcabcedd8",
    "HFrEF_community_scenario_test_set.zip": "184483385b61e55a0dc3608f63acece1",
}
MUSIC = "https://physionet.org/files/music-sudden-cardiac-death/1.0.1/{name}?download"
MUSIC_FILES = ["subject-info.csv", "subject-info_codes.csv", "subject-info_definitions.csv"]
RR_DATABASE = "https://physionet.org/files/{database}/1.0.0/{name}?download"


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "python-urllib"})
    with urllib.request.urlopen(request, timeout=600) as response:
        return response.read()


def fetch_to(url: str, path: Path) -> None:
    """Descarga a disco por trozos (para ficheros grandes)."""
    request = urllib.request.Request(url, headers={"User-Agent": "python-urllib"})
    partial = path.with_suffix(path.suffix + ".part")
    with urllib.request.urlopen(request, timeout=600) as response, partial.open("wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)
    partial.replace(path)


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
        print("Descargando compareGroups_4.4.6.tar.gz (3,5 MB)", flush=True)
        with tarfile.open(fileobj=BytesIO(fetch(COMPAREGROUPS)), mode="r:gz") as archive:
            member = archive.extractfile("compareGroups/data/predimed.rda")
            if member is None:
                raise RuntimeError("El paquete no trae data/predimed.rda")
            path.write_bytes(member.read())
    print(f"PREDIMED: {path} ({path.stat().st_size} bytes)")


def md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def hfref() -> None:
    """Los dos archivos de Zenodo. No se descomprimen: el código los lee tal cual."""
    directory = ROOT / "hfref"
    directory.mkdir(parents=True, exist_ok=True)
    for name, expected in HFREF_FILES.items():
        path = directory / name
        if not path.exists():
            print(f"Descargando {name}", flush=True)
            fetch_to(ZENODO.format(name=name), path)
        found = md5(path)
        if found != expected:
            raise RuntimeError(f"{name}: la huella no coincide ({found})")
        print(f"ECG y sonido: {path} ({path.stat().st_size / 1e6:.1f} MB)")


def music() -> None:
    directory = ROOT / "music"
    directory.mkdir(parents=True, exist_ok=True)
    for name in MUSIC_FILES:
        path = directory / name
        if not path.exists():
            print(f"Descargando {name}", flush=True)
            path.write_bytes(fetch(MUSIC.format(name=name)))
    print(f"MUSIC: {directory}")


def rr_databases() -> None:
    """Anotaciones de latidos (.ecg) y cabeceras (.hea) de chf2db y nsr2db, fichero a fichero."""
    for database in ("chf2db", "nsr2db"):
        directory = ROOT / "rr" / database
        directory.mkdir(parents=True, exist_ok=True)
        records = directory / "RECORDS"
        if not records.exists():
            records.write_bytes(fetch(RR_DATABASE.format(database=database, name="RECORDS")))
        names = [line.strip() for line in records.read_text().splitlines() if line.strip()]
        for record in names:
            if not record.replace("_", "").isalnum():  # el nombre viene de la red: solo letras y números
                raise RuntimeError(f"Nombre de registro inesperado: {record!r}")
            for extension in (".ecg", ".hea"):
                path = directory / f"{record}{extension}"
                if not path.exists():
                    path.write_bytes(fetch(RR_DATABASE.format(database=database, name=record + extension)))
        print(f"{database}: {len(names)} registros en {directory}", flush=True)


if __name__ == "__main__":
    physionet()
    predimed()
    music()
    rr_databases()
    hfref()
