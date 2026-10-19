#!/usr/bin/env python3
"""Carga OSM, DPA y GTFS y deriva sus capas; basada en los Labs 03 y 05."""

import csv
from collections import Counter
import io
import json
from pathlib import Path
import subprocess
import sys
import time

import preparar_datos as osm
import preparar_dpa
import preparar_gtfs


BASE = Path(__file__).resolve().parent
TABLAS = {
    "points": ("osm_puntos", "ST_Point"),
    "lines": ("osm_lineas", "ST_LineString"),
    "multipolygons": ("osm_poligonos", "ST_MultiPolygon"),
}
DERIVADAS = ("calles", "edificios", "paraderos_osm", "amenidades")


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
    print("Esperando PostgreSQL...", flush=True)
    for intento in range(30):
        try:
            db("pg_isready", "-h", "127.0.0.1", "-q", capture_output=True)
            break
        except subprocess.CalledProcessError:
            if intento == 29:
                raise ValueError("PostgreSQL no estuvo disponible; revisa docker compose up -d.")
            time.sleep(1)
    subprocess.run([sys.executable, str(BASE / "preparar_datos.py")], check=True)
    metadata = json.loads(
        (BASE / "data/interim/osm_santiago-centro.json").read_text(encoding="utf-8")
    )
    manifiesto = json.loads((BASE / "sources.json").read_text(encoding="utf-8"))
    metadata_dpa = preparar_dpa.preparar(manifiesto)
    metadata_gtfs = preparar_gtfs.preparar(manifiesto)
    psql("DROP SCHEMA IF EXISTS carga_t1 CASCADE; CREATE SCHEMA carga_t1;")
    tiempos = {}
    for capa, (tabla, _) in TABLAS.items():
        print(f"Cargando {capa} en carga_t1.{tabla}...", flush=True)
        inicio = time.perf_counter()
        log = BASE / "data/interim" / f"carga_{tabla}.log"
        with log.open("w", encoding="utf-8") as registro:
            db(
                "ogr2ogr", "-f", "PostgreSQL", "PG:host=127.0.0.1",
                "/interim/osm_santiago-centro.gpkg", capa,
                "-nln", f"carga_t1.{tabla}",
                "-lco", "GEOMETRY_NAME=geom", "-lco", "SPATIAL_INDEX=GIST",
                "-lco", "COLUMN_TYPES=other_tags=hstore", "-lco", "FID=id",
                "--config", "PG_USE_COPY", "YES",
                stdout=registro, stderr=subprocess.STDOUT,
            )
        psql(f"ANALYZE carga_t1.{tabla};")
        tiempos[tabla] = round(time.perf_counter() - inicio, 3)
        print(f"{tabla}: carga e índices en {tiempos[tabla]} s", flush=True)

    print("Auditando las tablas temporales...", flush=True)
    auditoria_antes = auditar("carga_t1")
    validar(auditoria_antes, metadata["counts"])
    print("Aplicando la reparación del Lab 05...", flush=True)
    sql_reparacion = (BASE / "reparar_osm.sql").read_text(encoding="utf-8")
    reparacion = json.loads(psql(sql_reparacion.replace("__ESQUEMA__", "carga_t1")))
    auditoria_despues = auditar("carga_t1")
    validar(auditoria_despues, metadata["counts"])
    if any(c["invalidos"] for c in auditoria_despues["capas"]):
        raise ValueError("Quedan geometrías inválidas; las tablas públicas no se sustituyeron.")
    if reparacion["resumen"]["objetos_reparados"] != sum(
        c["invalidos"] for c in auditoria_antes["capas"] if c["tabla"] == "osm_poligonos"
    ):
        raise ValueError("La evidencia de reparaciones no coincide con la auditoría previa.")
    print("Creando las cuatro capas OSM del Lab 05...", flush=True)
    sql_derivadas = (BASE / "derivar_osm.sql").read_text(encoding="utf-8")
    bbox = ",".join(map(str, metadata["bbox_epsg4326"]))
    capas = json.loads(psql(sql_derivadas.replace("__ESQUEMA__", "carga_t1").replace("__BBOX__", bbox)))
    tipos_derivados = {
        ("calles", "geom"): "ST_LineString", ("edificios", "geom"): "ST_MultiPolygon",
        ("edificios", "punto"): "ST_Point", ("paraderos_osm", "geom"): "ST_Point",
        ("amenidades", "geom"): "ST_Point",
    }
    if {(c["tabla"], c["columna"]) for c in capas["capas"]} != set(tipos_derivados):
        raise ValueError("Faltan capas OSM derivadas.")
    for c in capas["capas"]:
        if c["srids"] != [5361] or c["tipos"] != [tipos_derivados[(c["tabla"], c["columna"])]]:
            raise ValueError(f"Tipo o SRID incorrecto en capa derivada: {c}")
        if any(c[k] for k in ("nulos", "vacios", "invalidos", "puntos_fuera_caja")):
            raise ValueError(f"Geometría incorrecta en capa derivada: {c}")
    if capas["puntos_interiores_fuera_poligono"]:
        raise ValueError("Hay puntos interiores fuera del edificio correspondiente.")
    if sum(i["metodo"] == "gist" for i in capas["indices"]) != 5:
        raise ValueError("Faltan índices GiST en las capas OSM derivadas.")
    print("Cargando DPA con shp2pgsql, de EPSG:5360 a EPSG:5361...", flush=True)
    ruta_dpa = BASE / "data/interim/dpa"
    with (ruta_dpa / "comunas_cl.sql").open("w", encoding="utf-8") as salida, (ruta_dpa / "carga.log").open("w") as registro:
        db("shp2pgsql", "-D", "-s", "5360:5361", "-I", "-W", "UTF-8", "-g", "geom",
           "-N", "abort", "/interim/dpa/COMUNAS", "carga_t1.comunas_cl",
           stdout=salida, stderr=registro)
    with (ruta_dpa / "carga.log").open("a") as registro:
        db("psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-f", "/interim/dpa/comunas_cl.sql",
           stdout=registro, stderr=subprocess.STDOUT)
    sql_dpa = (BASE / "derivar_dpa.sql").read_text(encoding="utf-8")
    dpa = json.loads(psql(sql_dpa.replace("__ESQUEMA__", "carga_t1").replace("__BBOX__", bbox)))
    perfiles_dpa = {c["tabla"]: c for c in dpa["capas"]}
    if set(perfiles_dpa) != {"comunas_cl", "comunas_estudio", "comunas_sub"}:
        raise ValueError("Faltan capas de la DPA.")
    if perfiles_dpa["comunas_cl"]["filas"] != metadata_dpa["dbf_records"] or dpa["region_05"] != 38 or not dpa["nunoa_utf8_correcto"]:
        raise ValueError("La DPA no supera el control de registros o codificación del Lab 03.")
    for c in dpa["capas"]:
        if c["srids"] != [5361] or not set(c["tipos"]) <= {"ST_Polygon", "ST_MultiPolygon"}:
            raise ValueError(f"Tipo o SRID inesperado en DPA: {c}")
        if any(c[k] for k in ("invalidos", "nulos", "vacios")):
            raise ValueError(f"Geometría incorrecta en DPA: {c}")
    if perfiles_dpa["comunas_sub"]["max_vertices"] > 128:
        raise ValueError("La subdivisión excede los 128 vértices por fragmento.")
    if len(dpa["comunas_seleccionadas"]) != perfiles_dpa["comunas_estudio"]["filas"] or any(
        c["diferencia_area_m2"] > 0.01 for c in dpa["comunas_seleccionadas"]
    ):
        raise ValueError("La subdivisión no conserva las áreas de las comunas seleccionadas.")
    if sum(i["metodo"] == "gist" for i in dpa["indices"]) != 3:
        raise ValueError("Faltan índices GiST en la DPA.")
    print("Cargando los ocho CSV GTFS mediante COPY...", flush=True)
    sql_gtfs = (BASE / "cargar_gtfs.sql").read_text(encoding="utf-8")
    psql(sql_gtfs.replace("__ESQUEMA__", "carga_t1"))
    for nombre in preparar_gtfs.ARCHIVOS:
        columnas = ",".join(f'"{c}"' for c in metadata_gtfs["headers"][nombre])
        psql(f"COPY carga_t1.gtfs_{nombre} ({columnas}) FROM '/interim/gtfs/{nombre}.txt' "
             "WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');")
        print(f"GTFS {nombre}: COPY completado.", flush=True)
    sql_gtfs = (BASE / "derivar_gtfs.sql").read_text(encoding="utf-8")
    gtfs = json.loads(psql(sql_gtfs.replace("__ESQUEMA__", "carga_t1").replace("__BBOX__", bbox)))
    observados = manifiesto["sources"]["gtfs"]["observed_counts"]
    esperados = {n: observados["shape_points" if n == "shapes" else n]
                 for n in preparar_gtfs.ARCHIVOS}
    if gtfs["filas_fuente"] != esperados:
        raise ValueError("Los conteos cargados no coinciden con los CSV GTFS inspeccionados.")
    tipos_gtfs = {"paraderos_gtfs": "ST_Point", "paraderos_gtfs_bus": "ST_Point",
                  "recorridos_completos": "ST_LineString", "recorridos": "ST_MultiLineString"}
    if {c["tabla"] for c in gtfs["capas"]} != set(tipos_gtfs):
        raise ValueError("Faltan capas GTFS.")
    conteos_gtfs = {c["tabla"]: c["filas"] for c in gtfs["capas"]}
    if conteos_gtfs["paraderos_gtfs"] != observados["stops_bbox_location_type_0_or_empty"] or conteos_gtfs["recorridos_completos"] != observados["shapes"]:
        raise ValueError("Las paradas seleccionadas o los shapes completos no coinciden con la fuente inspeccionada.")
    for c in gtfs["capas"]:
        if c["srids"] != [5361] or c["tipos"] != [tipos_gtfs[c["tabla"]]]:
            raise ValueError(f"Tipo o SRID inesperado en GTFS: {c}")
        if any(c[k] for k in ("invalidos", "nulos", "vacios")):
            raise ValueError(f"Geometría incorrecta en GTFS: {c}")
    if gtfs["control_trazados"]["vertices_perdidos"] or gtfs["control_trazados"]["menos_de_dos_puntos"]:
        raise ValueError("Hay trazados GTFS incompletos.")
    if any(gtfs["control_temporal"][k] for k in (
        "ventanas_invalidas", "ventanas_solapadas", "bus_sin_frecuencias", "exact_times_no_cero"
    )):
        raise ValueError("La programación temporal no satisface los controles de Q7.")
    if sum(i["metodo"] == "gist" for i in gtfs["indices"]) != 4:
        raise ValueError("Faltan índices GiST en GTFS.")
    sentencias = ["BEGIN;"]
    publicadas = list(DERIVADAS) + [tabla for tabla, _ in TABLAS.values()] + [
        "osm_reparaciones", "comunas_sub", "comunas_estudio", "comunas_cl",
    ] + list(preparar_gtfs.DERIVADAS) + ["gtfs_" + n for n in preparar_gtfs.ARCHIVOS]
    sentencias.append("DROP MATERIALIZED VIEW IF EXISTS public.mv_oferta_nocturna;")
    sentencias.append("DROP MATERIALIZED VIEW IF EXISTS public.mv_grilla;")
    sentencias.append("DROP TABLE IF EXISTS " + ", ".join(f"public.{t}" for t in publicadas) + ";")
    for tabla in publicadas:
        sentencias.append(f"ALTER TABLE carga_t1.{tabla} SET SCHEMA public;")
    sentencias.extend(["DROP SCHEMA carga_t1;", "COMMIT;"])
    psql("\n".join(sentencias))

    auditoria = auditoria_antes
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
    auditoria["esquema_inspeccionado"] = "carga_t1"
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
    detalle = reparacion.pop("detalle")
    reparacion["archivo_detalle"] = "reparaciones_osm.csv"
    csv_reparaciones = io.StringIO(newline="")
    escritor_reparaciones = csv.DictWriter(csv_reparaciones, fieldnames=[
        "id", "osm_id", "osm_way_id", "building", "motivo", "tipo_antes", "tipo_makevalid",
        "tipo_despues", "componentes_antes", "componentes_despues", "vertices_antes",
        "vertices_despues", "componentes_lineales_excluidos", "componentes_puntuales_excluidos",
        "area_original_no_fiable_m2", "area_reparada_m2", "cambio_area_m2",
        "valida_despues", "vacia_despues", "punto_interior_cubierto",
    ], lineterminator="\n")
    escritor_reparaciones.writeheader()
    escritor_reparaciones.writerows(detalle)
    (BASE / "reparaciones_osm.csv").write_text(csv_reparaciones.getvalue(), encoding="utf-8")

    auditoria_despues = auditar("public")
    validar(auditoria_despues, metadata["counts"])
    auditoria_despues["fuente"] = auditoria["fuente"]
    auditoria_despues["etapa"] = "despues_de_reparaciones"
    auditoria_despues["esquema_inspeccionado"] = "public"
    auditoria_despues["reparacion"] = reparacion
    (BASE / "auditoria_osm_despues.json").write_text(
        json.dumps(auditoria_despues, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    capas["fuente"] = auditoria["fuente"]
    capas["bbox_epsg4326"] = metadata["bbox_epsg4326"]
    capas["criterio_area"] = "Puntos y puntos interiores dentro de la caja; calles completas del extracto."
    (BASE / "auditoria_capas_osm.json").write_text(
        json.dumps(capas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    dpa["fuente"] = metadata_dpa
    dpa["bbox_epsg4326"] = metadata["bbox_epsg4326"]
    dpa["segmento_maximo_borde_grados"] = 0.001
    dpa["versiones"] = auditoria_despues["versiones"]
    dpa["criterio_area"] = "Comunas completas que intersectan la caja; fragmentos de esas comunas completas."
    (BASE / "auditoria_dpa.json").write_text(
        json.dumps(dpa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    gtfs["fuente"] = metadata_gtfs
    gtfs["bbox_epsg4326"] = metadata["bbox_epsg4326"]
    gtfs["segmento_maximo_borde_grados"] = 0.001
    gtfs["criterio"] = "Paradas/plataformas tipo 0 declaradas; shapes completos antes del recorte; recorridos analíticos con referencia desde viajes; asociaciones distintas por ruta."
    (BASE / "auditoria_gtfs.json").write_text(
        json.dumps(gtfs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for c in auditoria_despues["capas"]:
        print(f"{c['tabla']}: {c['filas']:,} filas; {c['invalidos']} inválidas; {c['vacios']} vacías")
    print(f"Reparados {reparacion['resumen']['objetos_reparados']} objetos; evidencia en osm_reparaciones.")
    print("Auditorías anterior y posterior guardadas; originales y residuos conservados.")
    for c in capas["capas"]:
        if c["columna"] == "geom":
            print(f"{c['tabla']}: {c['filas']:,} objetos derivados.")
    for c in dpa["capas"]:
        print(f"{c['tabla']}: {c['filas']:,} geometrías; {c['invalidos']} inválidas.")
    for c in gtfs["capas"]:
        print(f"{c['tabla']}: {c['filas']:,} geometrías; {c['invalidos']} inválidas.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(f"Error de carga: {error}", file=sys.stderr)
        if error.stderr:
            print(error.stderr, file=sys.stderr)
        print("Revisa los registros de carga en data/interim/ y data/interim/dpa/.", file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, KeyError) as error:
        print(f"Error de validación: {error}", file=sys.stderr)
        sys.exit(1)
