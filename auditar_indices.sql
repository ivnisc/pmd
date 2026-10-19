-- contadores acumulados; cero lecturas no demuestra inutilidad general
SELECT s.schemaname AS esquema,s.relname AS tabla,s.indexrelname AS indice,
       a.amname AS metodo,i.indisprimary AS primario,i.indisunique AS unico,
       s.idx_scan,s.idx_tup_read,s.idx_tup_fetch,
       pg_relation_size(s.indexrelid) AS bytes,pg_get_indexdef(s.indexrelid) AS definicion
FROM pg_stat_user_indexes s
JOIN pg_index i ON i.indexrelid=s.indexrelid
JOIN pg_class c ON c.oid=s.indexrelid
JOIN pg_am a ON a.oid=c.relam
WHERE s.schemaname='public' AND s.relname<>'spatial_ref_sys'
ORDER BY s.relname,s.indexrelname;
