-- Learner Brain Foundation, part 1: tag every skill-graph row with which
-- exam product it belongs to. Today only OET exists, so skill_tag values
-- like "reading:B" or "speaking:fluency" implicitly mean OET -- nothing
-- marks that on the row. The moment a second product (NCLEX/IELTS) is
-- added, that becomes ambiguous and a year of historical rows can't be
-- told apart. Fixing it now, while there's one product and zero rows to
-- migrate incorrectly, is free; fixing it later means a backfill guess.
--
-- DEFAULT 'OET' means every existing row is valid immediately and
-- app/services/skill_graph.py needs no code change -- inserts that don't
-- name the column keep working exactly as before.
ALTER TABLE public.user_skill_stats
    ADD COLUMN IF NOT EXISTS product text NOT NULL DEFAULT 'OET';

-- Old uniqueness (user_id, skill_tag) would collide the day a second
-- product reuses a tag like "writing:coherence". Re-scope it to
-- (user_id, product, skill_tag) -- safe now because every existing row
-- shares the same product default, so no duplicates are introduced.
ALTER TABLE public.user_skill_stats
    DROP CONSTRAINT IF EXISTS user_skill_stats_user_id_skill_tag_key;

ALTER TABLE public.user_skill_stats
    ADD CONSTRAINT user_skill_stats_user_id_product_skill_tag_key
    UNIQUE (user_id, product, skill_tag);

-- Weakness-graph reads filter by user_id and a skill_tag prefix within one
-- product (get_weakness in skill_graph.py); once callers pass product too,
-- this index covers that lookup without a table scan.
CREATE INDEX IF NOT EXISTS user_skill_stats_user_product_idx
    ON public.user_skill_stats (user_id, product);
