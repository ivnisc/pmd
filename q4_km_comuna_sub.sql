-- reunir fragmentos por shape y comuna evita duplicar líneas sobre sus bordes
WITH tramos AS (
    SELECT c.cut_com,r.shape_id,
           ST_Length(ST_UnaryUnion(ST_Collect(ST_Intersection(r.geom,c.geom))))
               AS largo_m
    FROM comunas_sub c JOIN recorridos r ON ST_Intersects(c.geom,r.geom)
    GROUP BY c.cut_com,r.shape_id
)
SELECT c.cut_com,c.comuna,
       count(t.shape_id) FILTER (WHERE t.largo_m>0) AS shapes,
       COALESCE(sum(t.largo_m),0)/1000 AS km_recorridos
FROM comunas_estudio c LEFT JOIN tramos t USING (cut_com)
GROUP BY c.cut_com,c.comuna
ORDER BY c.cut_com;
