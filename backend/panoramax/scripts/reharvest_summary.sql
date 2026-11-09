-- What the harvester itself recorded for the harvests reharvest.fish just ran
-- (:instance, started at or after :since), then what the catalog now holds for
-- that instance — to set beside what the instance serves (stats.py).
--
-- created/updated/deleted are collection_harvest's verdicts per collection;
-- deleted is a tombstone the catalog acted on. items_removed are deleted_items
-- rows the harvest wrote: photos gone from a collection it re-fetched.
SELECT CASE WHEN h.is_incremental THEN 'incremental' ELSE 'full' END AS harvest,
	h.start::timestamp(0) AS started,
	round(extract(epoch FROM h.finished_at - h.start)) AS seconds,
	left(coalesce(h.error, ''), 60) AS error,
	(SELECT count(*) FROM harvest_errors e WHERE e.harvest_id = h.id) AS errors,
	count(c.*) FILTER (WHERE c.status = 'created') AS created,
	count(c.*) FILTER (WHERE c.status = 'updated') AS updated,
	count(c.*) FILTER (WHERE c.status = 'deleted') AS deleted,
	(SELECT count(*) FROM deleted_items d WHERE d.harvest_id = h.id) AS items_removed
FROM harvests h
JOIN instances i ON i.id = h.instance_id
LEFT JOIN collection_harvest c ON c.harvest_id = h.id
WHERE i.name = :'instance' AND h.start >= :'since'
GROUP BY h.id
ORDER BY h.start;

SELECT left(e.error, 120) AS harvest_error, e.collection_id
FROM harvest_errors e
JOIN harvests h ON h.id = e.harvest_id
JOIN instances i ON i.id = h.instance_id
WHERE i.name = :'instance' AND h.start >= :'since'
LIMIT 10;

SELECT count(DISTINCT c.id) AS catalog_collections, count(it.id) AS catalog_items
FROM collections c
JOIN instances i ON i.id = c.instance_id
LEFT JOIN items it ON it.collection_id = c.id
WHERE i.name = :'instance';
