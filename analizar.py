#!/usr/bin/env python3
"""Ejecuta consultas de la tarea y guarda CSV y planes mediante PostGIS local."""

import argparse
import json
from pathlib import Path

from conexion import consulta, ejecutar, explicar


BASE = Path(__file__).resolve().parent
CONSULTAS = {
    1: ("q1_paraderos_comuna",),
    2: ("q2_cobertura",),
    3: ("q3_correspondencia",),
    4: ("q4_km_comuna", "q4_km_comuna_sub", "q4_tramos"),
    5: ("q5_salud_cercana",),
    6: ("q6_grilla", "q6_top10"),
    7: ("q7_resumen", "q7_horas", "q7_rutas", "q7_sectores"),
}


def analizar(nombre, planes=False):
    sql = (BASE / f"{nombre}.sql").read_text(encoding="utf-8")
    resultado = consulta(sql)
    resultado.to_csv(BASE / f"{nombre}.csv", index=False, encoding="utf-8")
    print(f"{nombre}: CSV guardado", flush=True)
    if planes:
        plan = explicar(sql)
        (BASE / f"{nombre}_plan.json").write_text(
            json.dumps([plan], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        texto = explicar(sql, formato="texto")
        (BASE / f"{nombre}_plan.txt").write_text(texto + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("preguntas", nargs="+", type=int, choices=CONSULTAS)
    parser.add_argument("--planes", action="store_true")
    args = parser.parse_args()
    for pregunta in args.preguntas:
        if pregunta == 6 or (
            pregunta == 7
            and consulta("SELECT to_regclass('public.mv_grilla') IS NULL").iloc[0,0]
        ):
            ejecutar((BASE / "preparar_grilla.sql").read_text(encoding="utf-8"))
        if pregunta == 7:
            ejecutar((BASE / "preparar_q7.sql").read_text(encoding="utf-8"))
        for nombre in CONSULTAS[pregunta]:
            analizar(nombre, args.planes and pregunta in (2, 4, 5) and nombre != "q4_tramos")


if __name__ == "__main__":
    main()
