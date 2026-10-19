-- paraderos observados en la caja; área comunal completa y contraste recortado
WITH caja AS (
    SELECT ST_Transform(ST_Segmentize(ST_MakeEnvelope(-70.75,-33.52,-70.52,-33.36,4326),0.001),5361) AS geom
), puntos AS (
    SELECT 'gtfs' AS fuente, geom FROM paraderos_gtfs
    UNION ALL
    SELECT 'gtfs_bus', geom FROM paraderos_gtfs_bus
    UNION ALL
    SELECT 'osm', geom FROM paraderos_osm
), conteos AS (
    SELECT c.cut_com,
           count(*) FILTER (WHERE p.fuente='gtfs') AS paraderos_gtfs,
           count(*) FILTER (WHERE p.fuente='gtfs_bus') AS paraderos_gtfs_bus,
           count(*) FILTER (WHERE p.fuente='osm') AS paraderos_osm
    FROM comunas_estudio c
    LEFT JOIN puntos p ON ST_Contains(c.geom,p.geom)
    GROUP BY c.cut_com
), medidas AS (
    SELECT c.cut_com,c.comuna,c.area_m2/1e6 AS area_comuna_km2,
           ST_Area(ST_Intersection(c.geom,b.geom))/1e6 AS area_en_caja_km2,
           n.paraderos_gtfs,n.paraderos_gtfs_bus,n.paraderos_osm
    FROM comunas_estudio c
    JOIN conteos n USING (cut_com)
    CROSS JOIN caja b
)
SELECT cut_com,comuna,
       round(area_comuna_km2::numeric,6) AS area_comuna_km2,
       round(area_en_caja_km2::numeric,6) AS area_en_caja_km2,
       round((100*area_en_caja_km2/area_comuna_km2)::numeric,2)
           AS porcentaje_area_en_caja,
       paraderos_gtfs,
       round((paraderos_gtfs/area_comuna_km2)::numeric,3)
           AS densidad_gtfs_comuna_km2,
       round((paraderos_gtfs/NULLIF(area_en_caja_km2,0))::numeric,3)
           AS densidad_gtfs_caja_km2,
       paraderos_gtfs_bus,
       round((paraderos_gtfs_bus/area_comuna_km2)::numeric,3)
           AS densidad_gtfs_bus_comuna_km2,
       round((paraderos_gtfs_bus/NULLIF(area_en_caja_km2,0))::numeric,3)
           AS densidad_gtfs_bus_caja_km2,
       paraderos_osm,
       round((paraderos_osm/area_comuna_km2)::numeric,3)
           AS densidad_osm_comuna_km2,
       round((paraderos_osm/NULLIF(area_en_caja_km2,0))::numeric,3)
           AS densidad_osm_caja_km2
FROM medidas
ORDER BY paraderos_gtfs DESC,cut_com;
