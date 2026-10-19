-- comunas completas y subdivisión de 128 vértices, como en los labs 03 y 05
BEGIN;

CREATE UNIQUE INDEX comunas_cl_cut_com_idx ON __ESQUEMA__.comunas_cl (cut_com);
ANALYZE __ESQUEMA__.comunas_cl;

CREATE TABLE __ESQUEMA__.comunas_estudio AS
SELECT gid, cut_reg, cut_prov, cut_com, comuna, ST_Area(geom) AS area_m2, geom
FROM __ESQUEMA__.comunas_cl
WHERE ST_Intersects(geom, ST_Transform(ST_Segmentize(ST_MakeEnvelope(__BBOX__,4326),0.001),5361));
ALTER TABLE __ESQUEMA__.comunas_estudio ADD PRIMARY KEY (cut_com);
CREATE INDEX idx_comunas_estudio_geom ON __ESQUEMA__.comunas_estudio USING gist (geom);

CREATE TABLE __ESQUEMA__.comunas_sub AS
SELECT c.gid, c.cut_com, c.comuna, s.parte, s.geom
FROM __ESQUEMA__.comunas_estudio c
CROSS JOIN LATERAL ST_Subdivide(c.geom,128) WITH ORDINALITY AS s(geom,parte);
ALTER TABLE __ESQUEMA__.comunas_sub ADD PRIMARY KEY (cut_com,parte);
CREATE INDEX idx_comunas_sub_geom ON __ESQUEMA__.comunas_sub USING gist (geom);
ANALYZE __ESQUEMA__.comunas_estudio;
ANALYZE __ESQUEMA__.comunas_sub;

WITH geometrias AS (
    SELECT 'comunas_cl' AS tabla, geom FROM __ESQUEMA__.comunas_cl
    UNION ALL SELECT 'comunas_estudio', geom FROM __ESQUEMA__.comunas_estudio
    UNION ALL SELECT 'comunas_sub', geom FROM __ESQUEMA__.comunas_sub
), resumen AS (
    SELECT tabla, count(*) AS filas,
           count(*) FILTER (WHERE geom IS NULL) AS nulos,
           count(*) FILTER (WHERE ST_IsEmpty(geom)) AS vacios,
           count(*) FILTER (WHERE NOT (ST_IsValidDetail(geom)).valid) AS invalidos,
           array_agg(DISTINCT ST_SRID(geom)) AS srids,
           array_agg(DISTINCT ST_GeometryType(geom)) AS tipos,
           max(ST_NPoints(geom)) AS max_vertices
    FROM geometrias GROUP BY tabla
), areas AS (
    SELECT c.cut_com, c.comuna, c.area_m2 AS area_comuna_m2,
           sum(ST_Area(s.geom)) AS area_fragmentos_m2,
           abs(c.area_m2 - sum(ST_Area(s.geom))) AS diferencia_area_m2,
           count(*) AS fragmentos
    FROM __ESQUEMA__.comunas_estudio c
    JOIN __ESQUEMA__.comunas_sub s USING (cut_com)
    GROUP BY c.cut_com,c.comuna,c.area_m2
)
SELECT jsonb_build_object(
    'esquema_inspeccionado', '__ESQUEMA__',
    'capas', (SELECT jsonb_agg(to_jsonb(r) ORDER BY tabla) FROM resumen r),
    'region_05', (SELECT count(*) FROM __ESQUEMA__.comunas_cl WHERE cut_reg = '05'),
    'region_13', (SELECT count(*) FROM __ESQUEMA__.comunas_cl WHERE cut_reg = '13'),
    'nunoa_utf8_correcto', EXISTS (
        SELECT FROM __ESQUEMA__.comunas_cl WHERE cut_com = '13120' AND comuna = 'Ñuñoa'
    ),
    'comunas_seleccionadas', (SELECT jsonb_agg(to_jsonb(a) ORDER BY cut_com) FROM areas a),
    'indices', (
        SELECT jsonb_agg(jsonb_build_object(
            'tabla',t.relname,'indice',i.relname,'metodo',a.amname,
            'primario',x.indisprimary,'definicion',pg_get_indexdef(i.oid)
        ) ORDER BY t.relname,i.relname)
        FROM pg_index x JOIN pg_class t ON t.oid=x.indrelid
        JOIN pg_class i ON i.oid=x.indexrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace
        JOIN pg_am a ON a.oid=i.relam
        WHERE n.nspname='__ESQUEMA__'
          AND t.relname IN ('comunas_cl','comunas_estudio','comunas_sub')
    )
);

COMMIT;
