-- distinguir servicio en plena madrugada de últimas y primeras pasadas del día
SELECT noche,franja,hora,count(DISTINCT route_id) AS rutas,
       count(DISTINCT stop_id) AS paradas_con_oferta,
       round(sum(pasadas_previstas),3) AS pasadas_previstas,
       round(sum(pasadas_dia_previo),3) AS pasadas_dia_previo,
       round(sum(pasadas_previstas)/(SELECT count(*) FROM paraderos_gtfs_bus),3)
           AS media_pasadas_hora_parada
FROM mv_oferta_nocturna
GROUP BY noche,franja,hora ORDER BY noche,hora;
