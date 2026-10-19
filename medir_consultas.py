#!/usr/bin/env python3
"""Mide subdivisión y contrasta índices sin alterar las tablas de trabajo."""

import json
from pathlib import Path
import statistics

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from conexion import engine, explicar


BASE = Path(__file__).resolve().parent


def plan(nombre):
    sql = (BASE / f"{nombre}.sql").read_text(encoding="utf-8")
    return explicar(sql)


def sin_indice(nombre, indice):
    sql = (BASE / f"{nombre}.sql").read_text(encoding="utf-8")
    resultado = {"indice_retirado": indice, "limite_ms": 10000}
    try:
        with engine.connect() as conn:
            transaccion = conn.begin()
            try:
                conn.execute(text("SET LOCAL lock_timeout='2s'"))
                conn.execute(text("SET LOCAL statement_timeout='10s'"))
                conn.execute(text(f"DROP INDEX public.{indice}"))
                resultado["plan"] = conn.execute(text(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql
                )).scalar_one()[0]
            finally:
                transaccion.rollback()
        resultado["estado"] = "completado"
    except DBAPIError as exc:
        if getattr(exc.orig, "pgcode", None) != "57014" or "statement timeout" not in str(exc.orig):
            raise
        resultado["estado"] = "timeout"
        resultado["diagnostico"] = str(exc.orig).strip()
    with engine.connect() as conn:
        resultado["indice_restaurado"] = conn.execute(text(
            "SELECT to_regclass(:indice) IS NOT NULL"
        ), {"indice": f"public.{indice}"}).scalar_one()
    if not resultado["indice_restaurado"]:
        raise RuntimeError(f"No se restauró {indice}")
    (BASE / f"{nombre}_sin_indice.json").write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(nombre, resultado["estado"], flush=True)


def main():
    with engine.connect() as conn:
        configuracion = conn.execute(text("""
        SELECT jsonb_build_object('version',version(),'jit',current_setting('jit'),
          'shared_buffers',current_setting('shared_buffers'),
          'work_mem',current_setting('work_mem'),
          'max_parallel_workers_per_gather',current_setting('max_parallel_workers_per_gather'),
          'fecha_utc',timezone('UTC',clock_timestamp()));
        """)).scalar_one()
    nombres = ("q4_km_comuna", "q4_km_comuna_sub")
    muestras = {n: [] for n in nombres}
    for nombre in nombres:
        plan(nombre)
    for repeticion in range(5):
        orden = nombres if repeticion % 2 == 0 else nombres[::-1]
        for nombre in orden:
            muestras[nombre].append(plan(nombre)["Execution Time"])
        print(f"Q4: medición pareada {repeticion+1}/5", flush=True)
    with engine.connect() as conn:
        transaccion = conn.begin()
        try:
            conn.execute(text("""
                CREATE TEMP TABLE cronometro AS SELECT clock_timestamp() AS inicio;
                CREATE TEMP TABLE fragmentos AS
                SELECT c.cut_com,s.parte,s.geom FROM comunas_estudio c
                CROSS JOIN LATERAL ST_Subdivide(c.geom,128) WITH ORDINALITY s(geom,parte);
                ALTER TABLE fragmentos ADD PRIMARY KEY(cut_com,parte);
                CREATE INDEX ON fragmentos USING gist(geom);
                ANALYZE fragmentos;
            """))
            creacion_ms = float(conn.execute(text("""
                SELECT extract(epoch FROM (clock_timestamp()-inicio))*1000 FROM cronometro
            """)).scalar_one())
        finally:
            transaccion.rollback()
    resumen = {
        "configuracion": configuracion,
        "protocolo": "Una ejecución previa por variante para cargar los datos en caché; "
                     "cinco mediciones alternando orden. "
                     "Execution Time de EXPLAIN ANALYZE BUFFERS, con datos en caché; "
                     "medidas mediante SQLAlchemy, sin incluir planificación, cliente "
                     "ni creación de fragmentos.",
        "creacion_fragmentos_con_indices_analyze_ms": creacion_ms,
        "variantes": {n: {"muestras_ms": v, "mediana_ms": statistics.median(v),
                           "min_ms": min(v), "max_ms": max(v)} for n,v in muestras.items()},
    }
    (BASE / "q4_mediciones.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    sin_indice("q2_cobertura", "idx_paraderos_gtfs_geom")
    sin_indice("q5_salud_cercana", "idx_amenidades_geom")


if __name__ == "__main__":
    main()
