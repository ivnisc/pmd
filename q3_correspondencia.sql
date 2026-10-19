-- ausencia de vecinos a distancia menor o igual a 50 m, en ambos sentidos
WITH faltantes AS (
    SELECT 'GTFS a OSM' AS sentido,count(*) AS total,
           count(*) FILTER (WHERE NOT EXISTS (
               SELECT FROM paraderos_osm o WHERE ST_DWithin(g.geom,o.geom,50)
           )) AS sin_correspondencia
    FROM paraderos_gtfs g
    UNION ALL
    SELECT 'OSM a GTFS',count(*),count(*) FILTER (WHERE NOT EXISTS (
        SELECT FROM paraderos_gtfs g WHERE ST_DWithin(o.geom,g.geom,50)
    )) FROM paraderos_osm o
    UNION ALL
    SELECT 'GTFS buses a OSM',count(*),count(*) FILTER (WHERE NOT EXISTS (
        SELECT FROM paraderos_osm o WHERE ST_DWithin(g.geom,o.geom,50)
    )) FROM paraderos_gtfs_bus g
    UNION ALL
    SELECT 'OSM a GTFS buses',count(*),count(*) FILTER (WHERE NOT EXISTS (
        SELECT FROM paraderos_gtfs_bus g WHERE ST_DWithin(o.geom,g.geom,50)
    )) FROM paraderos_osm o
)
SELECT sentido,total,sin_correspondencia,
       round(100.0*sin_correspondencia/NULLIF(total,0),3) AS porcentaje
FROM faltantes ORDER BY sentido;
