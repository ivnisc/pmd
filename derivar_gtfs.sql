-- se construyen trazados completos antes de seleccionar o recortar la caja
-- densificar el borde geográfico evita unir solo las esquinas reproyectadas
BEGIN;

CREATE TABLE __ESQUEMA__.recorridos_completos AS
WITH lineas AS (
    SELECT shape_id, count(*) AS n_puntos,
           ST_Transform(ST_SetSRID(ST_MakeLine(
               ST_MakePoint(shape_pt_lon,shape_pt_lat) ORDER BY shape_pt_sequence
           ),4326),5361)::geometry(LineString,5361) AS geom
    FROM __ESQUEMA__.gtfs_shapes GROUP BY shape_id
)
SELECT *, ST_Length(geom) AS largo_m FROM lineas;
ALTER TABLE __ESQUEMA__.recorridos_completos ADD PRIMARY KEY (shape_id);
CREATE INDEX idx_recorridos_completos_geom ON __ESQUEMA__.recorridos_completos USING gist (geom);
ALTER TABLE __ESQUEMA__.gtfs_trips ADD FOREIGN KEY (shape_id)
    REFERENCES __ESQUEMA__.recorridos_completos(shape_id);
CREATE INDEX idx_gtfs_trips_route ON __ESQUEMA__.gtfs_trips (route_id);
CREATE INDEX idx_gtfs_trips_shape ON __ESQUEMA__.gtfs_trips (shape_id);
CREATE INDEX idx_gtfs_stop_times_stop ON __ESQUEMA__.gtfs_stop_times (stop_id);

CREATE TABLE __ESQUEMA__.rutas_shapes AS
SELECT DISTINCT route_id,shape_id FROM __ESQUEMA__.gtfs_trips WHERE shape_id IS NOT NULL;
ALTER TABLE __ESQUEMA__.rutas_shapes ADD PRIMARY KEY (route_id,shape_id);
CREATE INDEX idx_rutas_shapes_shape ON __ESQUEMA__.rutas_shapes (shape_id);

CREATE TABLE __ESQUEMA__.ruta_paraderos AS
SELECT DISTINCT t.route_id,s.stop_id
FROM __ESQUEMA__.gtfs_trips t JOIN __ESQUEMA__.gtfs_stop_times s USING (trip_id);
ALTER TABLE __ESQUEMA__.ruta_paraderos ADD PRIMARY KEY (route_id,stop_id);
CREATE INDEX idx_ruta_paraderos_stop ON __ESQUEMA__.ruta_paraderos (stop_id);

CREATE TABLE __ESQUEMA__.paraderos_gtfs AS
SELECT stop_id,stop_code,stop_name,COALESCE(location_type,0) AS location_type,
       ST_Transform(ST_SetSRID(ST_MakePoint(stop_lon,stop_lat),4326),5361)::geometry(Point,5361) AS geom
FROM __ESQUEMA__.gtfs_stops
WHERE COALESCE(location_type,0)=0
  AND ST_Covers(ST_MakeEnvelope(__BBOX__,4326),ST_SetSRID(ST_MakePoint(stop_lon,stop_lat),4326));
ALTER TABLE __ESQUEMA__.paraderos_gtfs ADD PRIMARY KEY (stop_id);
CREATE INDEX idx_paraderos_gtfs_geom ON __ESQUEMA__.paraderos_gtfs USING gist (geom);

CREATE TABLE __ESQUEMA__.paraderos_gtfs_bus AS
SELECT p.* FROM __ESQUEMA__.paraderos_gtfs p
WHERE EXISTS (
    SELECT FROM __ESQUEMA__.ruta_paraderos rp
    JOIN __ESQUEMA__.gtfs_routes r USING (route_id)
    WHERE rp.stop_id=p.stop_id AND r.route_type=3
);
ALTER TABLE __ESQUEMA__.paraderos_gtfs_bus ADD PRIMARY KEY (stop_id);
CREATE INDEX idx_paraderos_gtfs_bus_geom ON __ESQUEMA__.paraderos_gtfs_bus USING gist (geom);

CREATE TABLE __ESQUEMA__.recorridos AS
WITH candidatos AS (
    SELECT shape_id, ST_Multi(ST_CollectionExtract(ST_Intersection(
        geom,ST_Transform(ST_Segmentize(ST_MakeEnvelope(__BBOX__,4326),0.001),5361)
    ),2))::geometry(MultiLineString,5361) AS geom
    FROM __ESQUEMA__.recorridos_completos c
    WHERE ST_Intersects(geom,ST_Transform(ST_Segmentize(ST_MakeEnvelope(__BBOX__,4326),0.001),5361))
      AND EXISTS (SELECT FROM __ESQUEMA__.rutas_shapes r WHERE r.shape_id=c.shape_id)
)
SELECT *,ST_Length(geom) AS largo_m FROM candidatos WHERE NOT ST_IsEmpty(geom);
ALTER TABLE __ESQUEMA__.recorridos ADD PRIMARY KEY (shape_id);
CREATE INDEX idx_recorridos_geom ON __ESQUEMA__.recorridos USING gist (geom);

ANALYZE __ESQUEMA__.gtfs_stops;
ANALYZE __ESQUEMA__.gtfs_shapes;
ANALYZE __ESQUEMA__.gtfs_routes;
ANALYZE __ESQUEMA__.gtfs_trips;
ANALYZE __ESQUEMA__.gtfs_stop_times;
ANALYZE __ESQUEMA__.gtfs_calendar;
ANALYZE __ESQUEMA__.gtfs_calendar_dates;
ANALYZE __ESQUEMA__.gtfs_frequencies;
ANALYZE __ESQUEMA__.recorridos_completos;
ANALYZE __ESQUEMA__.rutas_shapes;
ANALYZE __ESQUEMA__.ruta_paraderos;
ANALYZE __ESQUEMA__.paraderos_gtfs;
ANALYZE __ESQUEMA__.paraderos_gtfs_bus;
ANALYZE __ESQUEMA__.recorridos;

WITH geometrias AS (
    SELECT 'paraderos_gtfs' AS tabla,geom FROM __ESQUEMA__.paraderos_gtfs
    UNION ALL SELECT 'paraderos_gtfs_bus',geom FROM __ESQUEMA__.paraderos_gtfs_bus
    UNION ALL SELECT 'recorridos_completos',geom FROM __ESQUEMA__.recorridos_completos
    UNION ALL SELECT 'recorridos',geom FROM __ESQUEMA__.recorridos
), frecuencias AS (
    SELECT *,split_part(start_time,':',1)::int*3600+split_part(start_time,':',2)::int*60
                 +split_part(start_time,':',3)::int AS inicio_s,
             split_part(end_time,':',1)::int*3600+split_part(end_time,':',2)::int*60
                 +split_part(end_time,':',3)::int AS fin_s
    FROM __ESQUEMA__.gtfs_frequencies
), ventanas AS (
    SELECT *,lag(fin_s) OVER(PARTITION BY trip_id ORDER BY inicio_s) AS fin_anterior
    FROM frecuencias
), resumen AS (
    SELECT tabla,count(*) AS filas,
           count(*) FILTER (WHERE geom IS NULL) AS nulos,
           count(*) FILTER (WHERE ST_IsEmpty(geom)) AS vacios,
           count(*) FILTER (WHERE NOT (ST_IsValidDetail(geom)).valid) AS invalidos,
           count(*) FILTER (WHERE NOT ST_IsSimple(geom)) AS no_simples,
           array_agg(DISTINCT ST_SRID(geom)) AS srids,
           array_agg(DISTINCT ST_GeometryType(geom)) AS tipos
    FROM geometrias GROUP BY tabla
)
SELECT jsonb_build_object(
    'esquema_inspeccionado','__ESQUEMA__',
    'filas_fuente',jsonb_build_object(
        'stops',(SELECT count(*) FROM __ESQUEMA__.gtfs_stops),
        'shapes',(SELECT count(*) FROM __ESQUEMA__.gtfs_shapes),
        'routes',(SELECT count(*) FROM __ESQUEMA__.gtfs_routes),
        'trips',(SELECT count(*) FROM __ESQUEMA__.gtfs_trips),
        'stop_times',(SELECT count(*) FROM __ESQUEMA__.gtfs_stop_times),
        'calendar',(SELECT count(*) FROM __ESQUEMA__.gtfs_calendar),
        'calendar_dates',(SELECT count(*) FROM __ESQUEMA__.gtfs_calendar_dates),
        'frequencies',(SELECT count(*) FROM __ESQUEMA__.gtfs_frequencies)
    ),
    'control_temporal',jsonb_build_object(
        'ventanas_invalidas',(SELECT count(*) FROM frecuencias WHERE fin_s<=inicio_s),
        'ventanas_solapadas',(SELECT count(*) FROM ventanas WHERE inicio_s<fin_anterior),
        'exact_times_no_cero',(SELECT count(*) FROM frecuencias WHERE COALESCE(exact_times,0)<>0),
        'bus_sin_frecuencias',(SELECT count(*) FROM __ESQUEMA__.gtfs_trips t
            JOIN __ESQUEMA__.gtfs_routes r USING(route_id) WHERE r.route_type=3
            AND NOT EXISTS(SELECT FROM frecuencias f WHERE f.trip_id=t.trip_id))
    ),
    'capas',(SELECT jsonb_agg(to_jsonb(r) ORDER BY tabla) FROM resumen r),
    'rutas_por_tipo',(SELECT jsonb_object_agg(route_type,n)
        FROM (SELECT route_type,count(*) n FROM __ESQUEMA__.gtfs_routes GROUP BY route_type) x),
    'stops_por_location_type',(SELECT jsonb_object_agg(location_type,n) FROM (
        SELECT COALESCE(location_type,0) AS location_type,count(*) n
        FROM __ESQUEMA__.gtfs_stops GROUP BY 1) x),
    'stops_sin_coordenadas',(SELECT count(*) FROM __ESQUEMA__.gtfs_stops WHERE stop_lat IS NULL OR stop_lon IS NULL),
    'relaciones',jsonb_build_object(
        'rutas_shapes',(SELECT count(*) FROM __ESQUEMA__.rutas_shapes),
        'ruta_paraderos',(SELECT count(*) FROM __ESQUEMA__.ruta_paraderos),
        'rutas_con_varios_shapes',(SELECT count(*) FROM (
            SELECT route_id FROM __ESQUEMA__.rutas_shapes GROUP BY route_id HAVING count(*)>1) x),
        'rutas_en_caja',(SELECT count(DISTINCT route_id) FROM __ESQUEMA__.rutas_shapes JOIN __ESQUEMA__.recorridos USING(shape_id))
    ),
    'control_trazados',jsonb_build_object(
        'menos_de_dos_puntos',(SELECT count(*) FROM __ESQUEMA__.recorridos_completos WHERE n_puntos<2),
        'vertices_perdidos',(SELECT count(*) FROM __ESQUEMA__.recorridos_completos WHERE ST_NPoints(geom)<>n_puntos),
        'shapes_no_usados',(SELECT count(*) FROM __ESQUEMA__.recorridos_completos s WHERE NOT EXISTS(
            SELECT FROM __ESQUEMA__.rutas_shapes r WHERE r.shape_id=s.shape_id)),
        'shapes_no_usados_que_intersectan_caja',(SELECT count(*) FROM __ESQUEMA__.recorridos_completos s
            WHERE ST_Intersects(geom,ST_Transform(ST_Segmentize(ST_MakeEnvelope(__BBOX__,4326),0.001),5361))
              AND NOT EXISTS (SELECT FROM __ESQUEMA__.rutas_shapes r WHERE r.shape_id=s.shape_id))
    ),
    'paraderos_sin_viajes',(SELECT count(*) FROM __ESQUEMA__.paraderos_gtfs p WHERE NOT EXISTS(
        SELECT FROM __ESQUEMA__.ruta_paraderos r WHERE r.stop_id=p.stop_id)),
    'stop_times_en_location_type_no_cero',(SELECT count(*) FROM __ESQUEMA__.gtfs_stop_times t
        JOIN __ESQUEMA__.gtfs_stops s USING(stop_id) WHERE COALESCE(s.location_type,0)<>0),
    'horarios_desde_24h',(SELECT count(*) FROM __ESQUEMA__.gtfs_stop_times WHERE
        NULLIF(split_part(arrival_time,':',1),'')::integer>=24
        OR NULLIF(split_part(departure_time,':',1),'')::integer>=24),
    'indices',(
        SELECT jsonb_agg(jsonb_build_object('tabla',t.relname,'indice',i.relname,
            'metodo',a.amname,'primario',x.indisprimary,'definicion',pg_get_indexdef(i.oid))
            ORDER BY t.relname,i.relname)
        FROM pg_index x JOIN pg_class t ON t.oid=x.indrelid JOIN pg_class i ON i.oid=x.indexrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace JOIN pg_am a ON a.oid=i.relam
        WHERE n.nspname='__ESQUEMA__' AND (t.relname LIKE 'gtfs_%'
            OR t.relname IN ('paraderos_gtfs','paraderos_gtfs_bus','recorridos_completos','recorridos','rutas_shapes','ruta_paraderos'))
    )
);

COMMIT;
