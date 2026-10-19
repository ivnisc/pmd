-- sectores son celdas de 500 m con objetos OSM residenciales, no habitantes
WITH residenciales AS (
    SELECT DISTINCT ON(e.id) e.id,h.i,h.j
    FROM edificios e JOIN mv_grilla h ON ST_Covers(h.geom,e.punto)
    WHERE e.building IN ('house','apartments','residential','semidetached_house','detached','terrace')
    ORDER BY e.id,h.i,h.j
), edificios_celda AS (
    SELECT i,j,count(*) AS edificios_residenciales FROM residenciales GROUP BY i,j
), paradas AS MATERIALIZED (
    SELECT DISTINCT ON(p.stop_id) p.stop_id,h.i,h.j
    FROM paraderos_gtfs_bus p JOIN mv_grilla h ON ST_Covers(h.geom,p.geom)
    ORDER BY p.stop_id,h.i,h.j
), base AS (
    SELECT i,j,count(*) AS paradas_bus FROM paradas GROUP BY i,j
), oferta AS (
    SELECT o.noche,o.franja,p.i,p.j,count(DISTINCT o.route_id) AS rutas,
           count(DISTINCT o.hora) AS horas_con_oferta,
           count(DISTINCT o.stop_id) AS paradas_con_oferta,sum(o.pasadas_previstas) AS pasadas
    FROM mv_oferta_nocturna o JOIN paradas p USING(stop_id)
    GROUP BY o.noche,o.franja,p.i,p.j
), franjas AS (
    SELECT n.noche,f.franja,f.horas FROM (VALUES (DATE '2026-10-16'),(DATE '2026-10-17')) n(noche)
    CROSS JOIN (VALUES ('noche',2),('madrugada',6)) f(franja,horas)
)
SELECT f.noche,f.franja,e.i,e.j,c.comuna AS comuna_referencia,e.edificios_residenciales,
       COALESCE(b.paradas_bus,0) AS paradas_bus_en_celda,
       COALESCE(o.paradas_con_oferta,0) AS paradas_con_oferta,
       COALESCE(o.rutas,0) AS rutas_con_oferta,
       COALESCE(o.horas_con_oferta,0) AS horas_con_oferta,
       round(COALESCE(o.pasadas,0),3) AS pasadas_previstas,
       round(COALESCE(o.pasadas,0)/f.horas/NULLIF(b.paradas_bus,0),3) AS media_pasadas_hora_parada
FROM edificios_celda e JOIN mv_grilla h USING(i,j)
CROSS JOIN franjas f LEFT JOIN base b USING(i,j)
LEFT JOIN oferta o USING(noche,franja,i,j)
LEFT JOIN LATERAL (
    SELECT c.comuna FROM comunas_estudio c WHERE ST_Covers(c.geom,ST_PointOnSurface(h.geom))
    ORDER BY c.cut_com LIMIT 1
) c ON true
ORDER BY f.noche,CASE f.franja WHEN 'noche' THEN 0 ELSE 1 END,e.i,e.j;
