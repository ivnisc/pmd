-- pasadas sumadas por parada: no equivalen a vehículos únicos
WITH franjas AS (
    SELECT n.noche,f.franja,f.horas FROM (VALUES (DATE '2026-10-16'),(DATE '2026-10-17')) n(noche)
    CROSS JOIN (VALUES ('noche',2),('madrugada',6)) f(franja,horas)
), continuidad AS (
    SELECT noche,franja,route_id,count(DISTINCT hora) AS horas
    FROM mv_oferta_nocturna GROUP BY noche,franja,route_id
)
SELECT f.noche,f.franja,f.horas,count(DISTINCT o.route_id) AS rutas,
       (SELECT count(*) FROM continuidad c WHERE c.noche=f.noche AND c.franja=f.franja
          AND c.horas=f.horas) AS rutas_en_todas_las_horas,
       count(DISTINCT o.stop_id) AS paradas_con_oferta,
       round(COALESCE(sum(o.pasadas_previstas),0),3) AS pasadas_previstas,
       round(COALESCE(sum(o.pasadas_dia_previo),0),3) AS pasadas_dia_previo,
       round(COALESCE(sum(o.pasadas_previstas),0)/f.horas/
             (SELECT count(*) FROM paraderos_gtfs_bus),3) AS media_pasadas_hora_parada
FROM franjas f LEFT JOIN mv_oferta_nocturna o USING(noche,franja)
GROUP BY f.noche,f.franja,f.horas
ORDER BY f.noche,CASE f.franja WHEN 'noche' THEN 0 ELSE 1 END;
