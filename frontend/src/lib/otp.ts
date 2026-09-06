// Single source of truth for the email OTP code length. Must match the
// Supabase Dashboard's Auth > Email OTP length setting (confirmed 8 digits
// in both QA and production as of 2026-09-06) -- shared by OtpInput and
// every page that renders it (/auth/verify, /auth/invite-code) so they
// can't drift from each other or from the Dashboard.
export const OTP_LENGTH = 8
