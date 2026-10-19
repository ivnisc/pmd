-- recorridos con alguna oferta, cualquiera sea su nombre comercial
WITH paradas_ruta AS (
    SELECT r.route_id,count(DISTINCT p.stop_id) AS paradas_en_caja
    FROM gtfs_routes r JOIN ruta_paraderos rp USING(route_id)
    JOIN paraderos_gtfs_bus p USING(stop_id)
    WHERE r.route_type=3 GROUP BY r.route_id
)
SELECT o.noche,o.franja,r.route_id,r.route_short_name,r.route_long_name,
       b.paradas_en_caja,count(DISTINCT o.stop_id) AS paradas_con_oferta,
       count(DISTINCT o.hora) AS n_horas_con_oferta,
       array_agg(DISTINCT to_char(o.hora,'HH24:MI') ORDER BY to_char(o.hora,'HH24:MI')) AS horas_con_oferta,
       round(sum(o.pasadas_previstas),3) AS pasadas_previstas,
       round(sum(o.pasadas_previstas)/b.paradas_en_caja/
             (extract(epoch FROM(o.fin-o.inicio))/3600),3) AS media_pasadas_hora_parada
FROM mv_oferta_nocturna o JOIN gtfs_routes r USING(route_id)
JOIN paradas_ruta b USING(route_id)
GROUP BY o.noche,o.franja,r.route_id,r.route_short_name,r.route_long_name,
         b.paradas_en_caja,o.inicio,o.fin
ORDER BY o.noche,CASE o.franja WHEN 'noche' THEN 0 ELSE 1 END,r.route_id;
