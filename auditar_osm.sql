-- diagnóstico previo a reparaciones; parte de las comprobaciones del lab 05
WITH objetos AS (
    SELECT 'osm_puntos' AS tabla, id, osm_id, NULL::text AS osm_way_id, geom
    FROM __ESQUEMA__.osm_puntos
    UNION ALL
    SELECT 'osm_lineas', id, osm_id, NULL::text, geom
    FROM __ESQUEMA__.osm_lineas
    UNION ALL
    SELECT 'osm_poligonos', id, osm_id, osm_way_id, geom
    FROM __ESQUEMA__.osm_poligonos
), diagnostico AS MATERIALIZED (
    SELECT tabla, id, osm_id, osm_way_id,
           ST_SRID(geom) AS srid, ST_GeometryType(geom) AS tipo,
           geom IS NULL AS nula, ST_IsEmpty(geom) AS vacia,
           ST_IsValidDetail(geom) AS revision,
           CASE WHEN ST_Dimension(geom) = 2 THEN ST_Area(geom) END AS area_m2_original
    FROM objetos
), resumen AS (
    SELECT tabla, count(*) AS filas,
           array_agg(DISTINCT srid ORDER BY srid) AS srids,
           array_agg(DISTINCT tipo ORDER BY tipo) AS tipos,
           count(*) FILTER (WHERE nula) AS nulos,
           count(*) FILTER (WHERE vacia) AS vacios,
           count(*) FILTER (WHERE NOT (revision).valid) AS invalidos
    FROM diagnostico GROUP BY tabla
)
SELECT jsonb_build_object(
    'capas', (SELECT jsonb_agg(to_jsonb(r) ORDER BY tabla) FROM resumen r),
    'invalidos', COALESCE((
        SELECT jsonb_agg(jsonb_build_object(
            'tabla', tabla, 'id', id, 'osm_id', osm_id, 'osm_way_id', osm_way_id,
            'motivo', (revision).reason,
            'ubicacion', ST_AsEWKT((revision).location),
            'area_m2_original', area_m2_original
        ) ORDER BY tabla, id)
        FROM diagnostico WHERE NOT (revision).valid
    ), '[]'::jsonb),
    'indices', (
        SELECT jsonb_agg(jsonb_build_object(
            'tabla', t.relname, 'indice', i.relname, 'metodo', a.amname,
            'primario', x.indisprimary, 'definicion', pg_get_indexdef(i.oid),
            'bytes', pg_relation_size(i.oid)
        ) ORDER BY t.relname, i.relname)
        FROM pg_index x
        JOIN pg_class t ON t.oid = x.indrelid
        JOIN pg_class i ON i.oid = x.indexrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_am a ON a.oid = i.relam
        WHERE n.nspname = '__ESQUEMA__'
          AND t.relname IN ('osm_puntos', 'osm_lineas', 'osm_poligonos')
    ),
    'tags', (
        SELECT jsonb_agg(jsonb_build_object(
            'tabla', table_name, 'tipo', udt_name
        ) ORDER BY table_name)
        FROM information_schema.columns
        WHERE table_schema = '__ESQUEMA__' AND column_name = 'other_tags'
          AND table_name IN ('osm_puntos', 'osm_lineas', 'osm_poligonos')
    ),
    'versiones', jsonb_build_object(
        'postgres', current_setting('server_version'),
        'postgis', postgis_full_version()
    )
);
