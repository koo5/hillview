-- fill_pano_meta.sql
--
-- Fills title-derived keywords and curated descriptions for our panoramas.
-- "Panorama" = a very wide stitched image: width > 10000 px (everything else in
-- the library is <= ~9973 px). Only captioned panos (title IS NOT NULL) are
-- touched — an untitled pano has nothing to derive a caption from.
--
-- MUST be run AFTER migration 018 (adds photos.title / photos.keywords).
-- Re-runnable: the curated table below is authoritative for the panos it lists —
-- edit a row and re-run to apply the change. Descriptions/keywords for panos NOT
-- in the table (e.g. set later by the upload pipeline) are left untouched.
--
-- Run:  psql "$DATABASE_URL" -f scripts/fill_pano_meta.sql
--   or: docker exec -i hillview_postgres psql -U hillview -d hillview < scripts/fill_pano_meta.sql

\set ON_ERROR_STOP on

-- 1) Guard: the title/keywords columns must exist (i.e. migration 018 has run).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'photos' AND column_name = 'title') THEN
        RAISE EXCEPTION 'photos.title is missing — run migration 018 (add title/keywords) first';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'photos' AND column_name = 'keywords') THEN
        RAISE EXCEPTION 'photos.keywords is missing — run migration 018 (add title/keywords) first';
    END IF;
END $$;

BEGIN;

-- 2) Curated text, keyed by the exact title. EDIT FREELY.
--    description: a hand-written Czech caption (reviewed first pass — check the
--                declension on the obscure place names).
--    extra_keywords: these ARE the photo's keywords verbatim. Only put terms that
--                aren't already findable via the title or description — alternate
--                names, nearby places, unannotated features (Vltava, etc.). Don't
--                repeat the title's location ("Vyšehrad") or the word "panorama";
--                a keyword that duplicates the title earns nothing. NULL = none.
--    A NULL description leaves that pano's description empty for you to fill later.
CREATE TEMP TABLE pano_curated (title text PRIMARY KEY, description text, extra_keywords text[]) ON COMMIT DROP;
INSERT INTO pano_curated (title, description, extra_keywords) VALUES
    ('Arcibiskupský altán -> Zbraslav',   'Panorama z Arcibiskupského altánu s výhledem na Zbraslav.', ARRAY['Vltava']),
    ('Bohdalec -> východ',                'Panorama z Bohdalce směrem na východ.', NULL),
    ('Bořanovice -> Čakovice',            'Panorama z Bořanovic s výhledem na Čakovice.', NULL),
    ('Chramostek -> sever',               'Panorama z Chramostku směrem na sever.', ARRAY['Vltava']),
    ('Grébovka',                          'Panorama Prahy z Havlíčkových sadů (Grébovky).', ARRAY['Havlíčkovy sady','Gröbovka','Vinohrady']),
    ('Grébovka -> východ',                'Panorama z Havlíčkových sadů (Grébovky) směrem na východ.', ARRAY['Havlíčkovy sady','Gröbovka','Vinohrady']),
    ('Havránka',                          'Panorama Prahy z Havránky.', NULL),
    ('Hvězdárna Ďáblice -> sever',        'Panorama od ďáblické hvězdárny směrem na sever.', ARRAY['Ďáblice']),
    ('Hvězdárna Ďáblice -> východ',       'Panorama od ďáblické hvězdárny směrem na východ.', ARRAY['Ďáblice']),
    ('Klokočské skály',                   'Panorama z Klokočských skal v Českém ráji.', ARRAY['Český ráj']),
    ('Kozí hřbety -> Praha',              'Panorama z Kozích hřbetů s výhledem na Prahu.', NULL),
    ('Kozí hřbety -> severozápad',        'Panorama z Kozích hřbetů směrem na severozápad.', NULL),
    ('Mělník -> jihozápad',               'Panorama z Mělníka směrem na jihozápad.', ARRAY['Vltava','Labe']),
    ('Park Sacré Coeur',                  'Panorama Prahy z parku Sacré Coeur na Smíchově.', ARRAY['Mrázovka','Smíchov']),
    ('Perucká -> jihozápad',              'Panorama z Perucké ulice směrem na jihozápad.', NULL),
    ('Průmyslová 566 -> východ',          'Panorama z Průmyslové směrem na východ.', NULL),
    ('Riegrovy sady -> Hrad',             'Panorama z Riegrových sadů s výhledem na Pražský hrad.', ARRAY['Vinohrady']),
    ('Riegrovy sady -> Petřín',           'Panorama z Riegrových sadů s výhledem na Petřín.', ARRAY['Vinohrady']),
    ('Vrbno -> sever',                    'Panorama od Vrbna směrem na sever.', NULL),
    ('Vrch Třešňovka -> sever 1',         'Panorama z vrchu Třešňovka směrem na sever.', ARRAY['Bohnice','Ládví','Prosek']),
    ('Vrch Třešňovka -> sever 2',         'Panorama z vrchu Třešňovka směrem na sever.', ARRAY['Bohnice','Ládví','Prosek']),
    ('Vrch Třešňovka -> sever 3',         'Panorama z vrchu Třešňovka směrem na sever.', ARRAY['Bohnice','Ládví','Prosek']),
    ('Výhledna Bořanovice -> jih',        'Panorama z výhledny Bořanovice směrem na jih.', ARRAY['Praha']),
    ('Výhledna Bořanovice -> sever',      'Panorama z výhledny Bořanovice směrem na sever.', NULL),
    ('Výhledna Bořanovice -> východ',     'Panorama z výhledny Bořanovice směrem na východ.', NULL),
    ('Vyhlídka Prosecké skály - východ',  'Panorama z Proseku směrem na východ.', ARRAY['Prosek']),
    ('Vyhlídka Prosecké skály - západ',   'Panorama z Proseku směrem na západ.', ARRAY['Prosek','Praha']),
    ('Vyšehrad -> jihovýchod',            'Panorama z Vyšehradu směrem na jihovýchod.', NULL),
    ('Vyšehrad -> jihozápad',             'Panorama z Vyšehradu směrem na jihozápad.', ARRAY['Vltava']),
    ('Vyšehrad -> Nuselský most',         'Panorama z Vyšehradu s výhledem na Nuselský most.', NULL),
    ('Vyšehrad -> sever',                 'Panorama z Vyšehradu směrem na sever.', NULL),
    ('Vyšehrad -> severozápad',           'Panorama z Vyšehradu směrem na severozápad.', NULL),
    ('Vyšehrad -> Strahov',               'Panorama z Vyšehradu s výhledem na Strahov.', NULL);

-- 3) Apply to captioned panoramas.
--    description: a curated value wins (so table edits re-apply); where the table
--                 has none, the existing value is kept.
--    keywords:    set to the curated extras verbatim (deduped/sorted) for a pano in
--                 the table — nothing is auto-added, since the title's location and
--                 the word "panorama" are already in the title/description. A curated
--                 pano with no extras ends up with NULL keywords (honest: nothing to
--                 add). An existing set on an un-curated pano (e.g. from the pipeline)
--                 is left alone.
WITH base AS (
    SELECT id, title
    FROM photos
    WHERE width > 10000
      AND deleted = false
      AND title IS NOT NULL AND title <> ''
)
UPDATE photos p
SET
    description = COALESCE(c.description, NULLIF(p.description, '')),
    keywords = CASE
        WHEN c.title IS NOT NULL THEN (
            SELECT array_agg(DISTINCT k ORDER BY k)
            FROM unnest(COALESCE(c.extra_keywords, '{}'::text[])) AS k
            WHERE k IS NOT NULL AND btrim(k) <> ''
        )
        ELSE p.keywords
    END
FROM base b
LEFT JOIN pano_curated c ON c.title = b.title
WHERE p.id = b.id;

-- 4) Report.
SELECT
    count(*)                                                        AS captioned_panos,
    count(*) FILTER (WHERE description IS NOT NULL AND description <> '') AS with_description,
    count(*) FILTER (WHERE keywords IS NOT NULL AND cardinality(keywords) > 0) AS with_keywords
FROM photos
WHERE width > 10000 AND deleted = false AND title IS NOT NULL AND title <> '';

COMMIT;
