-- Add Indian-nurse-specific fields to user_profiles
ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS state TEXT;
ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS qualification TEXT;
ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS years_of_experience TEXT;
ALTER TABLE public.user_profiles ADD COLUMN IF NOT EXISTS nursing_specialty TEXT;
