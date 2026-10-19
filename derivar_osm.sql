-- adaptado del ejercicio 2.1 del lab 05; caja aplicada sobre geometrías completas
BEGIN;

CREATE TABLE __ESQUEMA__.calles AS
SELECT id, osm_id, name, highway,
       other_tags -> 'maxspeed' AS maxspeed, other_tags -> 'oneway' AS oneway,
       ST_Length(geom) AS largo_m, geom
FROM __ESQUEMA__.osm_lineas
WHERE highway IS NOT NULL AND NOT ST_IsEmpty(geom);
ALTER TABLE __ESQUEMA__.calles ADD PRIMARY KEY (id);
CREATE INDEX idx_calles_geom ON __ESQUEMA__.calles USING gist (geom);

CREATE TABLE __ESQUEMA__.edificios AS
WITH candidatos AS (
    SELECT id, COALESCE(osm_id, osm_way_id) AS osm_id,
           CASE WHEN osm_id IS NOT NULL THEN 'relation' ELSE 'way' END AS osm_tipo,
           name, building, other_tags -> 'building:levels' AS pisos,
           ST_Area(geom) AS area_m2, geom,
           ST_PointOnSurface(geom)::geometry(Point,5361) AS punto
    FROM __ESQUEMA__.osm_poligonos
    WHERE building IS NOT NULL AND building <> 'no' AND NOT ST_IsEmpty(geom)
)
SELECT * FROM candidatos
WHERE ST_Covers(ST_MakeEnvelope(__BBOX__,4326), ST_Transform(punto,4326));
ALTER TABLE __ESQUEMA__.edificios ADD PRIMARY KEY (id);
CREATE INDEX idx_edificios_geom ON __ESQUEMA__.edificios USING gist (geom);
CREATE INDEX idx_edificios_punto ON __ESQUEMA__.edificios USING gist (punto);

CREATE TABLE __ESQUEMA__.paraderos_osm AS
SELECT id, osm_id, name, geom
FROM __ESQUEMA__.osm_puntos
WHERE highway = 'bus_stop' AND NOT ST_IsEmpty(geom)
  AND ST_Covers(ST_MakeEnvelope(__BBOX__,4326), ST_Transform(geom,4326));
ALTER TABLE __ESQUEMA__.paraderos_osm ADD PRIMARY KEY (id);
CREATE INDEX idx_paraderos_osm_geom ON __ESQUEMA__.paraderos_osm USING gist (geom);

CREATE TABLE __ESQUEMA__.amenidades AS
WITH objetos AS (
    SELECT id, osm_id, 'node'::text AS osm_tipo, name,
           other_tags -> 'amenity' AS amenity, geom
    FROM __ESQUEMA__.osm_puntos
    WHERE other_tags ? 'amenity' AND NOT ST_IsEmpty(geom)
    UNION ALL
    SELECT id, COALESCE(osm_id, osm_way_id),
           CASE WHEN osm_id IS NOT NULL THEN 'relation' ELSE 'way' END,
           name, amenity, ST_PointOnSurface(geom)::geometry(Point,5361)
    FROM __ESQUEMA__.osm_poligonos
    WHERE amenity IS NOT NULL AND NOT ST_IsEmpty(geom)
)
SELECT * FROM objetos
WHERE ST_Covers(ST_MakeEnvelope(__BBOX__,4326), ST_Transform(geom,4326));
ALTER TABLE __ESQUEMA__.amenidades ADD PRIMARY KEY (osm_tipo, osm_id);
CREATE INDEX idx_amenidades_geom ON __ESQUEMA__.amenidades USING gist (geom);

ANALYZE __ESQUEMA__.calles;
ANALYZE __ESQUEMA__.edificios;
ANALYZE __ESQUEMA__.paraderos_osm;
ANALYZE __ESQUEMA__.amenidades;

WITH geometrias AS (
    SELECT 'calles' AS tabla, 'geom' AS columna, geom FROM __ESQUEMA__.calles
    UNION ALL SELECT 'edificios', 'geom', geom FROM __ESQUEMA__.edificios
    UNION ALL SELECT 'edificios', 'punto', punto FROM __ESQUEMA__.edificios
    UNION ALL SELECT 'paraderos_osm', 'geom', geom FROM __ESQUEMA__.paraderos_osm
    UNION ALL SELECT 'amenidades', 'geom', geom FROM __ESQUEMA__.amenidades
), resumen AS (
    SELECT tabla, columna, count(*) AS filas,
           count(*) FILTER (WHERE geom IS NULL) AS nulos,
           count(*) FILTER (WHERE ST_IsEmpty(geom)) AS vacios,
           count(*) FILTER (WHERE NOT (ST_IsValidDetail(geom)).valid) AS invalidos,
           array_agg(DISTINCT ST_SRID(geom)) AS srids,
           array_agg(DISTINCT ST_GeometryType(geom)) AS tipos,
           count(*) FILTER (WHERE CASE WHEN ST_GeometryType(geom) = 'ST_Point' THEN
               NOT ST_Covers(ST_MakeEnvelope(__BBOX__,4326), ST_Transform(geom,4326))
               ELSE false END) AS puntos_fuera_caja
    FROM geometrias GROUP BY tabla, columna
)
SELECT jsonb_build_object(
    'esquema_inspeccionado', '__ESQUEMA__',
    'capas', (SELECT jsonb_agg(to_jsonb(r) ORDER BY tabla, columna) FROM resumen r),
    'puntos_interiores_fuera_poligono', (
        SELECT count(*) FROM __ESQUEMA__.edificios WHERE NOT ST_Covers(geom,punto)
    ),
    'exclusiones', jsonb_build_object(
        'building_no', (SELECT count(*) FROM __ESQUEMA__.osm_poligonos WHERE building = 'no'),
        'edificios_punto_fuera_caja', (
            SELECT count(*) - (SELECT count(*) FROM __ESQUEMA__.edificios)
            FROM __ESQUEMA__.osm_poligonos
            WHERE building IS NOT NULL AND building <> 'no' AND NOT ST_IsEmpty(geom)
        ),
        'amenidades_poligono_punto_fuera_caja', (
            SELECT count(*) - (SELECT count(*) FROM __ESQUEMA__.amenidades WHERE osm_tipo <> 'node')
            FROM __ESQUEMA__.osm_poligonos WHERE amenity IS NOT NULL AND NOT ST_IsEmpty(geom)
        )
    ),
    'amenidades_por_origen', (
        SELECT jsonb_object_agg(osm_tipo, n)
        FROM (SELECT osm_tipo, count(*) AS n FROM __ESQUEMA__.amenidades GROUP BY osm_tipo) x
    ),
    'indices', (
        SELECT jsonb_agg(jsonb_build_object(
            'tabla', t.relname, 'indice', i.relname, 'metodo', a.amname,
            'primario', x.indisprimary, 'definicion', pg_get_indexdef(i.oid)
        ) ORDER BY t.relname, i.relname)
        FROM pg_index x JOIN pg_class t ON t.oid = x.indrelid
        JOIN pg_class i ON i.oid = x.indexrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_am a ON a.oid = i.relam
        WHERE n.nspname = '__ESQUEMA__'
          AND t.relname IN ('calles','edificios','paraderos_osm','amenidades')
    )
);

COMMIT;
