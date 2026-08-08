-- Reverts 20260808020000_skill_observations_log.sql.
-- Safe any time -- nothing else in the codebase reads or writes this
-- table yet, so dropping it cannot break a running service.
DROP TABLE IF EXISTS public.skill_observations;
