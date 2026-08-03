# Secret Rotation Checklist — SpeakOET

**Trigger:** real keys from `backend/.env` got printed into a Claude chat transcript 2026-08-02. Values in that file are already blanked locally — this tracks rotating each key at its provider and updating Render/Vercel so prod stays in sync.

Related: [DEVOPS_AUDIT_CHECKLIST.md](DEVOPS_AUDIT_CHECKLIST.md) item #1 (rotate & relocate all secrets).

---

| # | Key | Provider action | Render updated | Vercel updated |
|---|-----|------------------|-----------------|------------------|
| 1 | `SUPABASE_SERVICE_ROLE_KEY` | Supabase dashboard → API settings → reset service role key | [ ] | n/a |
| 2 | `SUPABASE_ANON_KEY` | Supabase dashboard → API settings → reset anon key | [ ] | [ ] (if `NEXT_PUBLIC_SUPABASE_ANON_KEY` set) |
| 3 | `SUPABASE_JWT_SECRET` | Supabase dashboard → API settings → reset JWT secret (⚠ invalidates all live sessions) | [ ] | n/a |
| 4 | `OPENROUTER_API_KEY` | openrouter.ai → Keys → revoke + create new | [ ] | n/a |
| 5 | `OPENAI_API_KEY` | platform.openai.com → API keys → revoke + create new | [ ] | n/a |
| 6 | `DEEPGRAM_API_KEY` | console.deepgram.com → API keys → regenerate | [ ] | n/a |
| 7 | `AZURE_SPEECH_KEY` | Azure Portal → Speech resource → Keys → regenerate | [ ] | n/a |
| 8 | `RAZORPAY_KEY_ID` + `RAZORPAY_KEY_SECRET` | Razorpay dashboard → Settings → API Keys → regenerate | [ ] | [ ] (if public key id used client-side) |
| 9 | `RAZORPAY_WEBHOOK_SECRET` | Razorpay dashboard → Webhooks → regenerate secret, re-point webhook | [ ] | n/a |
| 10 | `DATABASE_URL` (DB password) | Supabase dashboard → Database → reset password | [ ] | n/a |
| 11 | `GOOGLE_TTS_API_KEY` | Google Cloud Console → Credentials → regenerate/restrict key | [ ] | n/a |

**Not rotated (not secrets):** `SUPABASE_URL`, `RAZORPAY_PLAN_ID_*`, `AZURE_SPEECH_REGION`, `AI_PROVIDER`, `ALLOWED_ORIGINS`.

## After each rotation
1. Update value in Render dashboard (backend service env vars) → redeploy.
2. Update value in Vercel dashboard if also used frontend-side.
3. Paste new value into local `backend/.env` for dev.
4. Check the row above.

## When all rows checked
- [ ] Confirm backend boots clean on Render with new values (`/health` returns 200).
- [ ] Confirm frontend auth/payment flows still work live.
- [ ] Delete this file or move to done.
