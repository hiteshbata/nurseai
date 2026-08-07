-- previous_band stores a letter grade ('A','B','C+','C','D','E'), not a
-- number -- FLOAT was wrong from creation (20260628000200_schema_v3.sql),
-- breaking every onboarding submit where has_taken_oet=true.
ALTER TABLE user_profiles ALTER COLUMN previous_band TYPE TEXT USING previous_band::text;
