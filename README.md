# Tarea 1: OSM y GTFS en Santiago

Carga y análisis geoespacial con PostgreSQL/PostGIS. Las fuentes se guardan en `data/` y no se versionan.

## Requisitos

- Docker con Compose v2.
- Python 3.14; versión utilizada: 3.14.6.
- Acceso a Internet para descargar fuentes, instalar dependencias y construir la imagen.
- Espacio para las fuentes, el volumen PostgreSQL y el GeoPackage nacional temporal de la preparación OSM.

GDAL, PostGIS y las herramientas de carga se instalan dentro de Docker. No se necesita el repositorio de los laboratorios.

## Fuentes

| Fuente | Archivo | Versión o fecha del contenido | Descarga |
|---|---|---|---|
| [OSM / Geofabrik](https://download.geofabrik.de/south-america/chile.html) | `chile-261012.osm.pbf` | Snapshot 12-10-2026, 20:21:35 UTC | 13-10-2026 |
| [GTFS / DTPM](https://www.dtpm.cl/index.php/gtfs-vigente?width=wide) | `GTFS_20261003.zip` | `V168.20261003`; vigencia 03-10 a 31-12-2026 | 13-10-2026 |
| [DPA / IDE Chile](https://datos.gob.cl/dataset/categoria-geoespacial-limites-y-fronteras) | `DPA_2023.zip` | DPA 2023; origen EPSG:5360 | 13-10-2026 |

Los archivos y sus SHA-256 están fijados en [sources.json](sources.json). El cargador rechaza fuentes con un hash diferente. Debe usarse el snapshot OSM indicado, no `chile-latest`.

## Reproducción

Ejecutar desde la raíz del repositorio.

### 1. Preparar el entorno

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
mkdir -p data/interim
```

### 2. Descargar las fuentes

```sh
curl --fail --location --output data/chile-261012.osm.pbf https://download.geofabrik.de/south-america/chile-261012.osm.pbf
curl --fail --location --output data/GTFS_20261003.zip https://www.dtpm.cl/descargas/gtfs/GTFS_20261003.zip
curl --fail --location --output data/DPA_2023.zip https://www.geoportal.cl/geoportal/catalog/download/912598ad-ac92-35f6-8045-098f214bd9c2
```

### 3. Levantar y cargar la base

```sh
docker compose up -d --build
.venv/bin/python cargar.py
```

`cargar.py` espera a PostgreSQL, prepara las tres fuentes, carga, repara, deriva las capas, crea índices y ejecuta `ANALYZE`. Publica las 25 tablas después de superar los controles. Al repetir la carga sustituye las tablas propias y elimina las dos vistas analíticas; después deben ejecutarse nuevamente los análisis y mapas.

La conexión usa `127.0.0.1:5435`, usuario/base `t1` y contraseña `t12026`, definidos en `docker-compose.yml`. Si se cambia el puerto, exportar `T1_DB_PORT` antes de ejecutar Compose y los scripts Python. El volumen se llama `t1-pgdata`; `docker compose down` detiene la base sin eliminarlo.

### 4. Generar resultados, planes y mapas

```sh
.venv/bin/python analizar.py 1 2 3 4 5 6 7 --planes
.venv/bin/python mapear.py 6 7
.venv/bin/python medir_consultas.py
.venv/bin/python auditar_indices.py --contexto "Carga completa, Q1–Q7, mapas y mediciones"
```

- `analizar.py` ejecuta los archivos SQL y guarda resultados CSV; `--planes` genera planes TXT/JSON para Q2, Q4 y Q5.
- `mapear.py` genera `mapa_q6.pdf`, `mapa_q7.pdf` y sus capas GeoJSON.
- `medir_consultas.py` realiza una ejecución previa para cargar los datos en caché y cinco mediciones alternadas de Q4. También ejecuta los controles Q2/Q5 sin índice, dentro de transacciones que se revierten. Ejecutarlo sin otras cargas concurrentes.
- `auditar_indices.py` exporta `indices_uso.csv` e `indices_uso.json` con estadísticas y contexto de observación.

Las salidas se escriben en la raíz y se sobrescriben al repetir los comandos. Fuentes, intermediarios y previsualizaciones PNG quedan en `data/`. Los tiempos de ejecución dependen del entorno y de la caché.

## Tablas, conteos e índices

Conteos esperados para las fuentes fijadas. Las claves primarias son B-tree; las capas geométricas tienen GiST y `ANALYZE`. Las dos vistas materializadas se crean durante el análisis de Q6/Q7. Las definiciones completas de índices se obtienen al ejecutar `auditar_indices.py`.

| Tabla | Filas | Índices |
|---|---:|---|
| `osm_puntos` | 255.799 | PK `id`; GiST `geom` |
| `osm_lineas` | 170.286 | PK `id`; GiST `geom` |
| `osm_poligonos` | 146.862 | PK `id`; GiST `geom` |
| `osm_reparaciones` | 16 | PK `id`; conserva identidad OSM y evidencia geométrica |
| `calles` | 101.204 | PK; GiST `geom` |
| `edificios` | 118.888 | PK; GiST `geom` y `punto` |
| `paraderos_osm` | 6.568 | PK; GiST `geom` |
| `amenidades` | 20.847 | PK `(osm_tipo,osm_id)`; GiST `geom` |
| `comunas_cl` | 345 | PK; único `cut_com`; GiST `geom` |
| `comunas_estudio` | 30 | PK `cut_com`; GiST `geom` |
| `comunas_sub` | 182 | PK `(cut_com,parte)`; GiST `geom` |
| `gtfs_stops` | 18.455 | PK `stop_id` |
| `gtfs_shapes` | 456.573 | PK `(shape_id,shape_pt_sequence)` |
| `gtfs_routes` | 428 | PK `route_id` |
| `gtfs_trips` | 26.159 | PK `trip_id`; B-tree `route_id`, `shape_id` |
| `gtfs_stop_times` | 1.098.529 | PK `(trip_id,stop_sequence)`; B-tree `stop_id` |
| `gtfs_calendar` | 6 | PK `service_id` |
| `gtfs_calendar_dates` | 12 | PK `(service_id,date)`; B-tree `date` |
| `gtfs_frequencies` | 14.542 | PK `(trip_id,start_time)` |
| `paraderos_gtfs` | 6.812 | PK `stop_id`; GiST `geom` |
| `paraderos_gtfs_bus` | 6.569 | PK `stop_id`; GiST `geom` |
| `recorridos_completos` | 981 | PK `shape_id`; GiST `geom` |
| `recorridos` | 708 | PK `shape_id`; GiST `geom` |
| `rutas_shapes` | 859 | PK `(route_id,shape_id)`; B-tree `shape_id` |
| `ruta_paraderos` | 40.473 | PK `(route_id,stop_id)`; B-tree `stop_id` |
| `mv_grilla` (vista materializada) | 636 | Único `(i,j)`; GiST `geom`; `ANALYZE` |
| `mv_oferta_nocturna` (vista materializada) | 207.281 | Único noche/franja/hora/ruta/parada; GiST `geom`; `ANALYZE` |


## Decisiones de carga y problemas encontrados

- **SRID:** geometrías de trabajo en EPSG:5361. OSM/GTFS se transforman desde 4326 y DPA desde 5360. El recorte usa la caja del enunciado; sus bordes se densifican antes de reproyectar.
- **Edificios:** se conserva el polígono y se usa `ST_PointOnSurface` para asignaciones y distancias. Se excluyen `building=no` y puntos interiores fuera de la caja.
- **Reparaciones:** 16 polígonos OSM reparados con `ST_MakeValid`, extracción poligonal y `ST_Multi`; cero inválidos o vacíos después. Los originales y residuos se conservan en `osm_reparaciones`.
- **GTFS:** ocho CSV cargados mediante `COPY`, incluidos 1.098.529 registros de `stop_times`. Se conserva una LineString completa por `shape_id`, ordenada por secuencia, y las asociaciones distintas con rutas. Se mantienen sentidos y variantes; las longitudes no se multiplican por viajes y Q6 cuenta rutas distintas.
- **Filtro OSM:** aplicar el filtro durante la reconstrucción del PBF perdía vértices. Se corrigió reconstruyendo primero el archivo completo y filtrando después.
- **Búsqueda KNN:** ordenar inicialmente por distancia e identidad impedía usar el GiST. Se corrigió resolviendo primero la distancia mínima y luego los empates por identidad.
