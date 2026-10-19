-- adaptado del ejercicio 1.5 del lab 05; conserva evidencia antes de actualizar
BEGIN;

CREATE TABLE __ESQUEMA__.osm_reparaciones AS
WITH invalidas AS MATERIALIZED (
    SELECT id, osm_id, osm_way_id, building,
           geom AS geom_original, ST_IsValidDetail(geom) AS diagnostico
    FROM __ESQUEMA__.osm_poligonos
    WHERE NOT (ST_IsValidDetail(geom)).valid
), corregidas AS MATERIALIZED (
    SELECT *, ST_MakeValid(geom_original) AS reparada FROM invalidas
)
SELECT id, osm_id, osm_way_id, building, (diagnostico).reason AS motivo,
       geom_original,
       ST_Multi(ST_CollectionExtract(reparada, 3)) AS geom_reparada,
       ST_CollectionExtract(reparada, 2) AS residuo_lineal,
       ST_CollectionExtract(reparada, 1) AS residuo_puntual,
       ST_GeometryType(reparada) AS tipo_makevalid
FROM corregidas;

ALTER TABLE __ESQUEMA__.osm_reparaciones ADD PRIMARY KEY (id);

UPDATE __ESQUEMA__.osm_poligonos p
SET geom = r.geom_reparada
FROM __ESQUEMA__.osm_reparaciones r
WHERE p.id = r.id;

ANALYZE __ESQUEMA__.osm_poligonos;
ANALYZE __ESQUEMA__.osm_reparaciones;

WITH detalle AS MATERIALIZED (
    SELECT id, osm_id, osm_way_id, motivo, building,
           ST_GeometryType(geom_original) AS tipo_antes, tipo_makevalid,
           ST_GeometryType(geom_reparada) AS tipo_despues,
           ST_NumGeometries(geom_original) AS componentes_antes,
           ST_NumGeometries(geom_reparada) AS componentes_despues,
           ST_NPoints(geom_original) AS vertices_antes,
           ST_NPoints(geom_reparada) AS vertices_despues,
           ST_NumGeometries(residuo_lineal) AS componentes_lineales_excluidos,
           ST_NumGeometries(residuo_puntual) AS componentes_puntuales_excluidos,
           ST_Area(geom_original) AS area_original_no_fiable_m2,
           ST_Area(geom_reparada) AS area_reparada_m2,
           ST_Area(geom_reparada) - ST_Area(geom_original) AS cambio_area_m2,
           (ST_IsValidDetail(geom_reparada)).valid AS valida_despues,
           ST_IsEmpty(geom_reparada) AS vacia_despues,
           CASE WHEN NOT ST_IsEmpty(geom_reparada) THEN
               ST_Covers(geom_reparada, ST_PointOnSurface(geom_reparada))
           END AS punto_interior_cubierto
    FROM __ESQUEMA__.osm_reparaciones
)
SELECT jsonb_build_object(
    'metodo', 'ST_MakeValid (linework) -> ST_CollectionExtract(3) -> ST_Multi',
    'tabla_evidencia', 'osm_reparaciones',
    'advertencia_area', 'El área original inválida es diagnóstica; no acredita superficie real.',
    'resumen', (SELECT jsonb_build_object(
        'objetos_reparados', count(*),
        'edificios_reparados', count(*) FILTER (WHERE building IS NOT NULL),
        'invalidos_despues', count(*) FILTER (WHERE NOT valida_despues),
        'vacios_despues', count(*) FILTER (WHERE vacia_despues),
        'componentes_antes', COALESCE(sum(componentes_antes), 0),
        'componentes_despues', COALESCE(sum(componentes_despues), 0),
        'componentes_lineales_excluidos', COALESCE(sum(componentes_lineales_excluidos), 0),
        'componentes_puntuales_excluidos', COALESCE(sum(componentes_puntuales_excluidos), 0),
        'puntos_interiores_cubiertos', count(*) FILTER (WHERE punto_interior_cubierto),
        'area_original_no_fiable_m2', COALESCE(sum(area_original_no_fiable_m2), 0),
        'area_reparada_m2', COALESCE(sum(area_reparada_m2), 0),
        'cambio_area_m2', COALESCE(sum(cambio_area_m2), 0)
    ) FROM detalle),
    'detalle', COALESCE((SELECT jsonb_agg(to_jsonb(d) ORDER BY id) FROM detalle d), '[]'::jsonb)
);

COMMIT;
