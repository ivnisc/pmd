#!/usr/bin/env python3
"""Extrae y verifica la DPA; adaptado de ein102b/03/preparar_datos.py."""

import json
from pathlib import Path
import shutil
import struct
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from preparar_datos import BASE, DESTINO, sha256


def preparar(manifiesto):
    fuente = manifiesto["sources"]["dpa"]
    ruta = BASE / fuente["input_path"]
    print(f"DPA: comprobando SHA-256 de {ruta.name}...", flush=True)
    if sha256(ruta) != fuente["sha256"]:
        raise ValueError("La DPA no coincide con el hash de sources.json.")
    salida = DESTINO / "dpa"
    salida.mkdir(parents=True, exist_ok=True)
    extensiones = (".shp", ".shx", ".dbf", ".prj", ".cpg")
    with TemporaryDirectory(prefix=".dpa-", dir=DESTINO) as temporal:
        temporal = Path(temporal)
        with ZipFile(ruta) as z:
            candidatos = [n for n in z.namelist() if n.lower().endswith(".shp")
                          and "comuna" in Path(n).name.lower()]
            if len(candidatos) != 1:
                raise ValueError("No se identifica un único shapefile de comunas en la DPA.")
            original = candidatos[0][:-4]
            for ext in extensiones:
                with z.open(original + ext) as entrada, (temporal / ("COMUNAS" + ext)).open("wb") as destino:
                    shutil.copyfileobj(entrada, destino)
        prj = (temporal / "COMUNAS.prj").read_text(encoding="utf-8").upper()
        if fuente["source_srid"] != 5360 or "SIRGAS-CHILE" not in prj or "PROJCS" in prj:
            raise ValueError("El PRJ de la DPA no corresponde al SIRGAS-Chile geográfico esperado.")
        encoding = (temporal / "COMUNAS.cpg").read_text(encoding="ascii").strip()
        if encoding.upper() != "UTF-8":
            raise ValueError(f"Codificación DPA inesperada: {encoding}.")
        with (temporal / "COMUNAS.dbf").open("rb") as dbf:
            cabecera = dbf.read(32)
        registros = struct.unpack("<I", cabecera[4:8])[0]
        if registros != fuente["expected_communes"]:
            raise ValueError(f"La cabecera DBF declara {registros} comunas; se esperaban 345.")
        metadata = {
            "source_file": ruta.name, "source_sha256": fuente["sha256"],
            "source_shapefile": original + ".shp", "source_srid": fuente["source_srid"],
            "encoding": encoding, "dbf_records": registros,
            "files_sha256": {"COMUNAS" + ext: sha256(temporal / ("COMUNAS" + ext))
                             for ext in extensiones},
        }
        for ext in extensiones:
            (temporal / ("COMUNAS" + ext)).replace(salida / ("COMUNAS" + ext))
        (salida / "dpa.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    print(f"DPA: {registros} registros, origen EPSG:5360 y UTF-8 verificados.", flush=True)
    return metadata


if __name__ == "__main__":
    preparar(json.loads((BASE / "sources.json").read_text(encoding="utf-8")))
