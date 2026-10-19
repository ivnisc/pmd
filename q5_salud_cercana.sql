-- knn con el filtro de salud dentro del lateral, como en los labs 04 y 05
SELECT '514' AS route_short_name,p.stop_id,p.stop_name,
       a.osm_tipo,a.osm_id,a.name AS nombre_salud,a.amenity,
       round(ST_Distance(p.geom,a.geom)::numeric,3) AS distancia_m
FROM paraderos_gtfs p
CROSS JOIN LATERAL (
    SELECT k.* FROM (
        SELECT a.osm_tipo,a.osm_id,a.name,a.amenity,a.geom
        FROM amenidades a
        WHERE a.amenity IN ('pharmacy','hospital','clinic','doctors')
        ORDER BY a.geom <-> p.geom
        FETCH FIRST 1 ROW WITH TIES
    ) k
    ORDER BY k.osm_tipo,k.osm_id
    LIMIT 1
) a
WHERE EXISTS (
    SELECT FROM ruta_paraderos rp JOIN gtfs_routes r USING(route_id)
    WHERE rp.stop_id=p.stop_id AND r.route_short_name='514'
)
ORDER BY distancia_m DESC,p.stop_id;
