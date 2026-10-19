-- anti-joins del lab 05; distancia al punto interior y control del borde
WITH evaluados AS MATERIALIZED (
    SELECT e.id,e.punto,
           NOT EXISTS (SELECT FROM paraderos_gtfs p
                       WHERE ST_DWithin(e.punto,p.geom,500)) AS sin_gtfs,
           NOT EXISTS (SELECT FROM paraderos_gtfs_bus p
                       WHERE ST_DWithin(e.punto,p.geom,500)) AS sin_bus,
           NOT EXISTS (SELECT FROM paraderos_osm p
                       WHERE ST_DWithin(e.punto,p.geom,500)) AS sin_osm,
           ST_DWithin(e.punto,ST_Boundary(ST_Transform(ST_Segmentize(ST_MakeEnvelope(-70.75,-33.52,-70.52,-33.36,4326),0.001),5361)),500) AS borde
    FROM edificios e
), conteos AS (
    SELECT c.cut_com,c.comuna,count(e.id) AS edificios,
           count(*) FILTER (WHERE e.sin_gtfs) AS sin_gtfs_500m,
           count(*) FILTER (WHERE e.sin_bus) AS sin_gtfs_bus_500m,
           count(*) FILTER (WHERE e.sin_osm) AS sin_osm_500m,
           count(*) FILTER (WHERE e.borde) AS edificios_borde_500m,
           count(*) FILTER (WHERE e.borde AND e.sin_gtfs) AS sin_gtfs_en_borde,
           count(*) FILTER (WHERE e.borde AND e.sin_osm) AS sin_osm_en_borde
    FROM comunas_estudio c
    LEFT JOIN evaluados e ON ST_Contains(c.geom,e.punto)
    GROUP BY c.cut_com,c.comuna
)
SELECT cut_com,comuna,edificios,sin_gtfs_500m,
       round(100.0*sin_gtfs_500m/NULLIF(edificios,0),3) AS pct_sin_gtfs,
       sin_gtfs_bus_500m,
       round(100.0*sin_gtfs_bus_500m/NULLIF(edificios,0),3) AS pct_sin_gtfs_bus,
       sin_osm_500m,
       round(100.0*sin_osm_500m/NULLIF(edificios,0),3) AS pct_sin_osm,
       round(100.0*(sin_osm_500m-sin_gtfs_500m)/NULLIF(edificios,0),3)
           AS diferencia_osm_gtfs_pp,
       edificios_borde_500m,sin_gtfs_en_borde,sin_osm_en_borde
FROM conteos
ORDER BY pct_sin_gtfs DESC NULLS LAST,cut_com;
