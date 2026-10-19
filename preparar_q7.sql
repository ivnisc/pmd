-- oferta media por parada y ruta; tiempos locales, sin generar salidas exactas
DROP MATERIALIZED VIEW IF EXISTS mv_oferta_nocturna;
CREATE MATERIALIZED VIEW mv_oferta_nocturna AS
WITH noches(noche) AS (
    VALUES (DATE '2026-10-16'),(DATE '2026-10-17')
), franjas AS (
    SELECT noche,f.franja,noche+f.desde*INTERVAL '1 hour' AS inicio,
           noche+f.hasta*INTERVAL '1 hour' AS fin
    FROM noches CROSS JOIN (VALUES ('noche',22,24),('madrugada',24,30)) f(franja,desde,hasta)
), tiempos AS (
    SELECT s.trip_id,s.stop_id,s.stop_sequence,s.pickup_type,
           split_part(s.departure_time,':',1)::int*3600+
           split_part(s.departure_time,':',2)::int*60+
           split_part(s.departure_time,':',3)::int AS salida_s
    FROM gtfs_stop_times s JOIN gtfs_trips t USING(trip_id)
    JOIN gtfs_routes r USING(route_id) WHERE r.route_type=3
), relativos AS MATERIALIZED (
    SELECT *,salida_s-first_value(salida_s) OVER (
        PARTITION BY trip_id ORDER BY stop_sequence
    ) AS desfase_s FROM tiempos
), dias AS (
    SELECT d::date AS fecha FROM generate_series(
        (SELECT min(inicio)::date-ceil(max(r.desfase_s)/86400.0)::int
         FROM franjas CROSS JOIN relativos r),
        (SELECT max(fin)::date FROM franjas),INTERVAL '1 day'
    ) d
), servicios AS (
    SELECT d.fecha,c.service_id FROM dias d CROSS JOIN gtfs_calendar c
    LEFT JOIN gtfs_calendar_dates e ON e.service_id=c.service_id AND e.date=d.fecha
    WHERE e.exception_type=1 OR (
        COALESCE(e.exception_type,0)<>2 AND d.fecha BETWEEN c.start_date AND c.end_date
        AND (ARRAY[c.monday,c.tuesday,c.wednesday,c.thursday,c.friday,c.saturday,c.sunday])[
            extract(isodow FROM d.fecha)::int]=1
    )
), intervalos AS (
    SELECT d.fecha,t.route_id,s.stop_id,
           d.fecha+(s.desfase_s+split_part(f.start_time,':',1)::int*3600+
                    split_part(f.start_time,':',2)::int*60+
                    split_part(f.start_time,':',3)::int)*INTERVAL '1 second' AS inicio,
           d.fecha+(s.desfase_s+split_part(f.end_time,':',1)::int*3600+
                    split_part(f.end_time,':',2)::int*60+
                    split_part(f.end_time,':',3)::int)*INTERVAL '1 second' AS fin,
           f.headway_secs
    FROM servicios d JOIN gtfs_trips t USING(service_id)
    JOIN gtfs_frequencies f USING(trip_id)
    JOIN relativos s USING(trip_id)
    JOIN paraderos_gtfs_bus p USING(stop_id)
    WHERE COALESCE(s.pickup_type,0)=0
), aportes AS (
    SELECT b.noche,b.franja,b.inicio,b.fin,h.hora,a.route_id,a.stop_id,
           extract(epoch FROM (least(a.fin,h.hora+INTERVAL '1 hour')-greatest(a.inicio,h.hora)))
               /a.headway_secs AS pasadas,
           a.fecha<b.inicio::date AS dia_previo
    FROM intervalos a JOIN franjas b ON a.inicio<b.fin AND a.fin>b.inicio
    CROSS JOIN LATERAL generate_series(b.inicio,b.fin-INTERVAL '1 hour',INTERVAL '1 hour') h(hora)
    WHERE a.inicio<h.hora+INTERVAL '1 hour' AND a.fin>h.hora
), sumas AS (
    SELECT noche,franja,inicio,fin,hora,route_id,stop_id,sum(pasadas) AS pasadas_previstas,
           COALESCE(sum(pasadas) FILTER(WHERE dia_previo),0) AS pasadas_dia_previo
    FROM aportes GROUP BY noche,franja,inicio,fin,hora,route_id,stop_id
)
SELECT s.*,p.geom FROM sumas s JOIN paraderos_gtfs_bus p USING(stop_id);
CREATE UNIQUE INDEX mv_oferta_nocturna_pk ON mv_oferta_nocturna(noche,franja,hora,route_id,stop_id);
CREATE INDEX mv_oferta_nocturna_geom ON mv_oferta_nocturna USING gist(geom);
ANALYZE mv_oferta_nocturna;
