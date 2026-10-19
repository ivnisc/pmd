"""Exporta pg_stat_user_indexes después de ejecutar los análisis."""

import argparse
import json
from pathlib import Path

from conexion import consulta

BASE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contexto", default="Base de trabajo; carga y consultas acumuladas.")
    args = parser.parse_args()
    datos = consulta((BASE / "auditar_indices.sql").read_text())
    datos.to_csv(BASE / "indices_uso.csv", index=False)
    contexto = consulta("""
        SELECT current_timestamp AS observado_en,version() AS servidor,
               current_database() AS base,stats_reset
        FROM pg_stat_database WHERE datname=current_database()
    """).iloc[0].to_dict()
    contexto = {k: (None if v is None else str(v)) for k, v in contexto.items()}
    contexto.update(
        indices=len(datos), sin_lecturas=int(datos.idx_scan.eq(0).sum()),
        carga_observada=args.contexto,
        alcance="Contadores acumulados desde creación/reinicio de estadísticas de cada índice; "
                "incluyen carga, auditorías y consultas ejecutadas. No son una medición de tiempo "
                "ni una prueba de inutilidad general. Eliminar/recrear un índice reinicia su contador.",
    )
    (BASE / "indices_uso.json").write_text(json.dumps(contexto, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(datos)} índices; {contexto['sin_lecturas']} sin lecturas registradas.")


if __name__ == "__main__":
    main()
