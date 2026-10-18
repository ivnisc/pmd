#!/usr/bin/env python3
"""Prepara OSM de Santiago centro; adaptado de ein102b/05/preparar_datos.py."""

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import time


BASE = Path(__file__).resolve().parent
DESTINO = BASE / "data" / "interim"
CAPAS = ("points", "lines", "multipolygons")


def sha256(ruta):
    with ruta.open("rb") as archivo:
        return hashlib.file_digest(archivo, "sha256").hexdigest()


def compose(*args, **kwargs):
    return subprocess.run(
        ["docker", "compose", *args], cwd=BASE, check=True, **kwargs
    )


def verificar(gpkg, srid):
    with closing(sqlite3.connect(gpkg.as_uri() + "?mode=ro", uri=True)) as con:
        if con.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise ValueError("El GeoPackage no supera la comprobación de integridad.")
        capas = {
            nombre: (srid_c, srid_g, tipo)
            for nombre, srid_c, srid_g, tipo in con.execute(
                "SELECT c.table_name, c.srs_id, g.srs_id, g.geometry_type_name "
                "FROM gpkg_contents c JOIN gpkg_geometry_columns g "
                "ON c.table_name = g.table_name WHERE c.data_type = 'features'"
            )
        }
        for capa in CAPAS:
            if capa not in capas or capas[capa][:2] != (srid, srid):
                raise ValueError(f"Capa ausente o SRID incorrecto: {capa}.")
        conteos = {
            capa: con.execute(f'SELECT count(*) FROM "{capa}"').fetchone()[0]
            for capa in CAPAS
        }
        if min(conteos.values()) == 0 or sum(conteos.values()) < 1000:
            raise ValueError(f"Extracto vacío o inesperadamente pequeño: {conteos}.")
    return conteos


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zona", choices=["santiago-centro"], default="santiago-centro")
    parser.add_argument("--forzar", action="store_true", help="regenerar el extracto")
    args = parser.parse_args()

    manifiesto = json.loads((BASE / "sources.json").read_text(encoding="utf-8"))
    zona = manifiesto["study_area"]
    if zona["name"] != args.zona:
        raise ValueError("La zona no coincide con sources.json.")
    fuente = manifiesto["sources"]["osm"]
    pbf = (BASE / fuente["input_path"]).resolve()
    relativa = pbf.relative_to(BASE / "data")
    print(f"Fuente: {pbf.name}; comprobando SHA-256...", flush=True)
    if sha256(pbf) != fuente["sha256"]:
        raise ValueError("El PBF no coincide con el hash de sources.json.")

    version = compose(
        "exec", "-T", "db", "ogr2ogr", "--version", capture_output=True, text=True
    ).stdout.strip()
    parametros = {
        "source_sha256": fuente["sha256"],
        "bbox_epsg4326": zona["bbox_epsg4326"],
        "srid": zona["working_srid"],
        "gdal_version": version,
    }
    DESTINO.mkdir(parents=True, exist_ok=True)
    gpkg = DESTINO / f"osm_{args.zona}.gpkg"
    metadata = gpkg.with_suffix(".json")
    log = DESTINO / f"osm_{args.zona}.log"

    if gpkg.exists() and not args.forzar:
        if not metadata.exists():
            raise ValueError("Falta la trazabilidad del extracto; usa --forzar.")
        anterior = json.loads(metadata.read_text(encoding="utf-8"))
        if any(anterior.get(k) != v for k, v in parametros.items()):
            raise ValueError("Cambió la fuente o la configuración; usa --forzar.")
        if sha256(gpkg) != anterior.get("output_sha256"):
            raise ValueError("El GeoPackage fue modificado; usa --forzar.")
        conteos = verificar(gpkg, zona["working_srid"])
        if conteos != anterior.get("counts"):
            raise ValueError("Los conteos no coinciden con la trazabilidad.")
        print(f"Se conserva el extracto verificado: {gpkg}", flush=True)
    else:
        print(f"{version}\nConvirtiendo {args.zona}; registro: {log}", flush=True)
        inicio = time.perf_counter()
        with TemporaryDirectory(prefix=".osm-", dir=DESTINO) as temporal:
            parcial = Path(temporal) / gpkg.name
            log_parcial = Path(temporal) / log.name
            salida_contenedor = "/interim/" + parcial.relative_to(DESTINO).as_posix()
            try:
                with log_parcial.open("w", encoding="utf-8") as registro:
                    compose(
                        "exec", "-T", "db", "ogr2ogr", "-f", "GPKG",
                        salida_contenedor, "/data/" + relativa.as_posix(), *CAPAS,
                        "-spat", *map(str, zona["bbox_epsg4326"]),
                        "-t_srs", f"EPSG:{zona['working_srid']}", "-progress",
                        "--config", "OSM_MAX_TMPFILE_SIZE", "4000",
                        stdout=registro, stderr=subprocess.STDOUT,
                    )
                conteos = verificar(parcial, zona["working_srid"])
            except (OSError, ValueError, sqlite3.Error, subprocess.CalledProcessError):
                if log_parcial.exists():
                    log_parcial.replace(log.with_suffix(".fallo.log"))
                raise
            datos = {
                **parametros,
                "source_file": fuente["filename"],
                "counts": conteos,
                "output_sha256": sha256(parcial),
                "output_bytes": parcial.stat().st_size,
                "elapsed_seconds": round(time.perf_counter() - inicio, 3),
            }
            metadata_parcial = Path(temporal) / metadata.name
            metadata_parcial.write_text(
                json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            parcial.replace(gpkg)
            metadata_parcial.replace(metadata)
            log_parcial.replace(log)

    print(
        f"Verificación OK: {conteos['points']:,} puntos; {conteos['lines']:,} líneas; "
        f"{conteos['multipolygons']:,} polígonos; SRID {zona['working_srid']}.",
        flush=True,
    )
    if log.is_file():
        avisos = log.read_text().count("Warning ")
        if avisos:
            print(f"El registro GDAL contiene {avisos} mensajes de advertencia: {log}")
    print("El filtro -spat no recorta las geometrías en el borde de la caja.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, sqlite3.Error, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        print("Si falló ogr2ogr, revisa el registro en data/interim/.", file=sys.stderr)
        sys.exit(1)
