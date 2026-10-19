-- detalle para rastrear longitudes y variantes hasta sus rutas declaradas
SELECT c.cut_com,c.comuna,r.shape_id,
       (SELECT array_agg(s.route_id ORDER BY s.route_id)
        FROM rutas_shapes s WHERE s.shape_id=r.shape_id) AS route_ids,
       (SELECT array_agg(DISTINCT g.route_short_name ORDER BY g.route_short_name)
        FROM rutas_shapes s JOIN gtfs_routes g USING(route_id)
        WHERE s.shape_id=r.shape_id) AS route_short_names,
       ST_Length(ST_Intersection(r.geom,c.geom)) AS largo_m
FROM comunas_estudio c JOIN recorridos r ON ST_Intersects(c.geom,r.geom)
WHERE ST_Length(ST_Intersection(r.geom,c.geom))>0
ORDER BY c.cut_com,r.shape_id;
