"""Conexión y funciones SQL de los Labs 04 y 05, adaptadas a T1."""

import os

import pandas as pd
from sqlalchemy import URL, create_engine, text


URL_DB = URL.create(
    "postgresql+psycopg2", username="t1", password="t12026",
    host="127.0.0.1", port=int(os.environ.get("T1_DB_PORT", "5435")), database="t1",
)
engine = create_engine(URL_DB)


def consulta(sql, **params):
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params, coerce_float=False)


def ejecutar(sql):
    with engine.begin() as conn:
        conn.execute(text(sql))


def explicar(sql, formato="json"):
    opcion = ", FORMAT JSON" if formato == "json" else ""
    with engine.connect() as conn:
        resultado = conn.execute(text(f"EXPLAIN (ANALYZE, BUFFERS{opcion}) " + sql))
        if formato == "json":
            return resultado.scalar_one()[0]
        return "\n".join(resultado.scalars())
