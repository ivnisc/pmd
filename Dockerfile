# adaptado del laboratorio 05 de ein102b
FROM postgres:16-bookworm@sha256:0ea6700a3b4f0ae6ce746519073558aed4d88a79d8d07622a9a644946c7319c4

RUN apt-get update \
 && apt-get install -y --no-install-recommends gdal-bin postgis postgresql-16-postgis-3 \
 && rm -rf /var/lib/apt/lists/* \
 && printf '%s\n' \
    'CREATE EXTENSION IF NOT EXISTS postgis;' \
    'CREATE EXTENSION IF NOT EXISTS hstore;' \
    > /docker-entrypoint-initdb.d/10_extensiones.sql
