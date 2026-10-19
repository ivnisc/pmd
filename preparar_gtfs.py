#!/usr/bin/env python3
"""Verifica el GTFS fijado y extrae los ocho CSV utilizados por la tarea."""

import csv
import io
import json
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from preparar_datos import BASE, DESTINO, sha256

ARCHIVOS = ("stops", "shapes", "routes", "calendar", "calendar_dates",
            "trips", "stop_times", "frequencies")
DERIVADAS = ("paraderos_gtfs_bus", "paraderos_gtfs", "recorridos", "rutas_shapes",
             "ruta_paraderos", "recorridos_completos")


def preparar(manifiesto):
    fuente = manifiesto["sources"]["gtfs"]
    ruta = BASE / fuente["input_path"]
    print(f"GTFS: comprobando SHA-256 de {ruta.name}...", flush=True)
    if sha256(ruta) != fuente["sha256"]:
        raise ValueError("El GTFS no coincide con el hash de sources.json.")
    salida = DESTINO / "gtfs"
    salida.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".gtfs-", dir=DESTINO) as temporal:
        temporal = Path(temporal)
        headers = {}
        with ZipFile(ruta) as z:
            with z.open("feed_info.txt") as archivo:
                feed = list(csv.DictReader(io.TextIOWrapper(archivo, encoding="utf-8-sig")))
            if len(feed) != 1 or feed[0]["feed_version"] != fuente["version"]:
                raise ValueError("La versión interna del GTFS no coincide con el manifiesto.")
            for nombre in ARCHIVOS:
                with z.open(nombre + ".txt") as archivo:
                    columnas = next(csv.reader(io.TextIOWrapper(archivo, encoding="utf-8-sig")))
                if len(set(columnas)) != len(columnas) or any(
                    not re.fullmatch(r"[a-z][a-z0-9_]*", c) for c in columnas
                ):
                    raise ValueError(f"Encabezado GTFS inesperado: {nombre}.")
                headers[nombre] = columnas
                with z.open(nombre + ".txt") as entrada, (temporal / (nombre + ".txt")).open("wb") as destino:
                    shutil.copyfileobj(entrada, destino)
        metadata = {
            "source_file": ruta.name, "source_sha256": fuente["sha256"],
            "feed_info": feed[0], "headers": headers,
            "files_sha256": {n + ".txt": sha256(temporal / (n + ".txt")) for n in ARCHIVOS},
        }
        for n in ARCHIVOS:
            (temporal / (n + ".txt")).replace(salida / (n + ".txt"))
        (salida / "gtfs.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    return metadata


if __name__ == "__main__":
    preparar(json.loads((BASE / "sources.json").read_text(encoding="utf-8")))
