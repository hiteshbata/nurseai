-- Nullable contact field only. No phone auth/MFA in this migration --
-- schema just leaves room for it later.
ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS phone_e164 TEXT NULL;

ALTER TABLE public.user_profiles
  ADD CONSTRAINT user_profiles_phone_e164_format
  CHECK (phone_e164 IS NULL OR phone_e164 ~ '^\+[1-9]\d{7,14}$');
