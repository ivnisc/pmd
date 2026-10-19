-- hexágonos de lado 500 m; agregaciones separadas para evitar multiplicaciones
-- bordes geográficos densificados a 0,001 grados antes de reproyectar
DROP MATERIALIZED VIEW IF EXISTS mv_grilla;
CREATE MATERIALIZED VIEW mv_grilla AS
WITH caja AS (
    SELECT ST_Transform(ST_Segmentize(ST_MakeEnvelope(-70.75,-33.52,-70.52,-33.36,4326),0.001),5361) AS geom
), celdas AS MATERIALIZED (
    SELECT h.i,h.j,ST_Intersection(h.geom,b.geom)::geometry(Polygon,5361) AS geom
    FROM caja b CROSS JOIN LATERAL ST_HexagonGrid(500,b.geom) h
    WHERE ST_Intersects(h.geom,b.geom)
      AND ST_Area(ST_Intersection(h.geom,b.geom))>0
), asignados AS (
    SELECT DISTINCT ON (e.id) e.id,h.i,h.j
    FROM edificios e JOIN celdas h ON ST_Covers(h.geom,e.punto)
    ORDER BY e.id,h.i,h.j
), edificios_celda AS (
    SELECT i,j,count(*) AS edificios FROM asignados GROUP BY i,j
), rutas_celda AS (
    SELECT h.i,h.j,count(DISTINCT s.route_id) AS rutas
    FROM celdas h JOIN recorridos r ON ST_Intersects(h.geom,r.geom)
    JOIN rutas_shapes s USING(shape_id)
    GROUP BY h.i,h.j
)
SELECT h.i,h.j,h.geom,ST_Area(h.geom) AS area_m2,
       COALESCE(e.edificios,0) AS edificios,COALESCE(r.rutas,0) AS rutas
FROM celdas h LEFT JOIN edificios_celda e USING(i,j)
LEFT JOIN rutas_celda r USING(i,j);
CREATE UNIQUE INDEX mv_grilla_ij_idx ON mv_grilla(i,j);
CREATE INDEX mv_grilla_geom_idx ON mv_grilla USING gist(geom);
ANALYZE mv_grilla;
