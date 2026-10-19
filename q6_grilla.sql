-- resultado de la vista creada por preparar_grilla.sql
WITH ordenados AS (
    SELECT *,row_number() OVER (ORDER BY edificios DESC,rutas ASC,i,j) AS orden
    FROM mv_grilla
)
SELECT i,j,round(area_m2::numeric,3) AS area_m2,edificios,rutas,
       rutas=0 AS sin_rutas,orden,edificios>0 AND orden<=10 AS top10
FROM ordenados ORDER BY orden;
