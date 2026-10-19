-- más edificios; a igual conteo, menos rutas; los ceros siguen siendo elegibles
SELECT i,j,edificios,rutas,
       round(ST_X(ST_Transform(ST_PointOnSurface(geom),4326))::numeric,6) AS longitud,
       round(ST_Y(ST_Transform(ST_PointOnSurface(geom),4326))::numeric,6) AS latitud
FROM mv_grilla
WHERE edificios>0
ORDER BY edificios DESC,rutas ASC,i,j
LIMIT 10;
