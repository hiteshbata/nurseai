-- Reverts 20260808010000_learner_brain_product_column.sql.
-- Only safe if no row has product <> 'OET' yet (true until a second
-- product actually starts writing skill observations).
DROP INDEX IF EXISTS public.user_skill_stats_user_product_idx;

ALTER TABLE public.user_skill_stats
    DROP CONSTRAINT IF EXISTS user_skill_stats_user_id_product_skill_tag_key;

ALTER TABLE public.user_skill_stats
    ADD CONSTRAINT user_skill_stats_user_id_skill_tag_key
    UNIQUE (user_id, skill_tag);

ALTER TABLE public.user_skill_stats
    DROP COLUMN IF EXISTS product;
