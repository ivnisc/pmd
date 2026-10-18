#!/usr/bin/env python3
"""Carga OSM y audita sus geometrías; adaptado del notebook del Lab 05."""

import csv
from collections import Counter
import io
import json
from pathlib import Path
import subprocess
import sys
import time

import preparar_datos as osm


BASE = Path(__file__).resolve().parent
TABLAS = {
    "points": ("osm_puntos", "ST_Point"),
    "lines": ("osm_lineas", "ST_LineString"),
    "multipolygons": ("osm_poligonos", "ST_MultiPolygon"),
}


def db(*args, **kwargs):
    return osm.compose(
        "exec", "-T", "db", "sh", "-c",
        'export PGUSER="$POSTGRES_USER" PGDATABASE="$POSTGRES_DB" '
        'PGPASSWORD="$POSTGRES_PASSWORD"; exec "$@"',
        "sh", *args, **kwargs,
    )


def psql(sql):
    return db(
        "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
        input=sql, capture_output=True, text=True,
    ).stdout.strip()


def auditar(esquema):
    sql = (BASE / "auditar_osm.sql").read_text(encoding="utf-8")
    return json.loads(psql(sql.replace("__ESQUEMA__", esquema)))


def validar(auditoria, conteos):
    capas = {c["tabla"]: c for c in auditoria["capas"]}
    tags = {t["tabla"]: t["tipo"] for t in auditoria["tags"]}
    for capa, (tabla, tipo) in TABLAS.items():
        c = capas[tabla]
        if c["filas"] != conteos[capa] or c["srids"] != [5361]:
            raise ValueError(f"Conteo o SRID inesperado en {tabla}: {c}")
        if c["tipos"] != [tipo] or c["nulos"] != 0 or tags.get(tabla) != "hstore":
            raise ValueError(f"Geometría o etiquetas inesperadas en {tabla}: {c}")
        indices = [i for i in auditoria["indices"] if i["tabla"] == tabla]
        if not any(i["primario"] for i in indices):
            raise ValueError(f"Falta clave primaria en {tabla}.")
        if not any(i["metodo"] == "gist" for i in indices):
            raise ValueError(f"Falta índice espacial en {tabla}.")


def main():
    subprocess.run([sys.executable, str(BASE / "preparar_datos.py")], check=True)
    metadata = json.loads(
        (BASE / "data/interim/osm_santiago-centro.json").read_text(encoding="utf-8")
    )
    psql("DROP SCHEMA IF EXISTS carga_osm CASCADE; CREATE SCHEMA carga_osm;")
    tiempos = {}
    for capa, (tabla, _) in TABLAS.items():
        print(f"Cargando {capa} en carga_osm.{tabla}...", flush=True)
        inicio = time.perf_counter()
        log = BASE / "data/interim" / f"carga_{tabla}.log"
        with log.open("w", encoding="utf-8") as registro:
            db(
                "ogr2ogr", "-f", "PostgreSQL", "PG:host=127.0.0.1",
                "/interim/osm_santiago-centro.gpkg", capa,
                "-nln", f"carga_osm.{tabla}",
                "-lco", "GEOMETRY_NAME=geom", "-lco", "SPATIAL_INDEX=GIST",
                "-lco", "COLUMN_TYPES=other_tags=hstore", "-lco", "FID=id",
                "--config", "PG_USE_COPY", "YES",
                stdout=registro, stderr=subprocess.STDOUT,
            )
        psql(f"ANALYZE carga_osm.{tabla};")
        tiempos[tabla] = round(time.perf_counter() - inicio, 3)
        print(f"{tabla}: carga e índices en {tiempos[tabla]} s", flush=True)

    print("Auditando las tablas temporales...", flush=True)
    validar(auditar("carga_osm"), metadata["counts"])
    sentencias = ["BEGIN;"]
    sentencias.append("DROP TABLE IF EXISTS public.osm_puntos, public.osm_lineas, public.osm_poligonos;")
    for tabla, _ in TABLAS.values():
        sentencias.append(f"ALTER TABLE carga_osm.{tabla} SET SCHEMA public;")
    sentencias.extend(["DROP SCHEMA carga_osm;", "COMMIT;"])
    psql("\n".join(sentencias))

    auditoria = auditar("public")
    validar(auditoria, metadata["counts"])
    invalidos = auditoria.pop("invalidos")
    motivos = Counter((r["tabla"], r["motivo"]) for r in invalidos)
    auditoria["motivos"] = [
        {"tabla": tabla, "motivo": motivo, "filas": n}
        for (tabla, motivo), n in sorted(motivos.items())
    ]
    auditoria["archivo_invalidos"] = "geometrias_osm_invalidas.csv"
    auditoria["fuente"] = {
        "pbf": metadata["source_file"],
        "pbf_sha256": metadata["source_sha256"],
        "gpkg_sha256": metadata["output_sha256"],
        "extraction_method": metadata["extraction_method"],
    }
    auditoria["etapa"] = "antes_de_reparaciones"
    auditoria["carga_segundos"] = tiempos
    (BASE / "auditoria_osm_antes.json").write_text(
        json.dumps(auditoria, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    csv_salida = io.StringIO(newline="")
    escritor = csv.DictWriter(csv_salida, fieldnames=[
        "tabla", "id", "osm_id", "osm_way_id", "motivo", "ubicacion", "area_m2_original"
    ], lineterminator="\n")
    escritor.writeheader()
    escritor.writerows(invalidos)
    (BASE / "geometrias_osm_invalidas.csv").write_text(csv_salida.getvalue(), encoding="utf-8")
    for c in auditoria["capas"]:
        print(f"{c['tabla']}: {c['filas']:,} filas; {c['invalidos']} inválidas; {c['vacios']} vacías")
    print("Auditoría guardada antes de reparaciones; geometrías originales conservadas.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(f"Error de carga: {error}", file=sys.stderr)
        if error.stderr:
            print(error.stderr, file=sys.stderr)
        print("Revisa los registros de data/interim/carga_osm_*.log.", file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, KeyError) as error:
        print(f"Error de validación: {error}", file=sys.stderr)
        sys.exit(1)
