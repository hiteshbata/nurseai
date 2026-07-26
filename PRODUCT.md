# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Indian nurses preparing for the OET (Occupational English Test) to register as nurses in Australia, UK, or New Zealand. ESL speakers, studying around shift work, on a fixed exam timeline, mostly on phone or laptop over Indian mobile/home internet.

## Product Purpose

SpeakOET is an AI coach that lets nurses practice every OET sub-test and get real, rubric-based feedback, so they can prepare for and pass OET without a human tutor or classroom course.

## Positioning

Full-syllabus depth: covers all four OET sub-tests (Speaking, Writing, Reading, Listening) with real rubric-based scoring, not just a Speaking-practice app or a static question bank. Live AI patient roleplay is the flagship mechanism — real-time voice conversation with an AI patient, scored on the public 9-criteria OET Speaking rubric (Empathy, Patient's Perspective, Providing Structure, Information Gathering, Information Giving, Intelligibility, Fluency, Appropriateness of Language, Grammar & Expression).

## Operating Context

- Practice is standalone/unproctored; the real OET is timed and scored by human examiners, remote or at a test center.
- Speaking: 100+ clinically-written scenarios across beginner/intermediate/advanced difficulty.
- Writing: AI-evaluated written responses (Pro plan).
- Reading, Listening, a study Hub, and a Vocab module are in active development (as of 2026-07-24) — the published README's "not yet built" note on Reading/Listening is stale.
- Subscription tiers: Free / Basic / Pro / Elite via Razorpay, one-off and auto-renewing.
- Progress dashboard: band-score trend, per-criterion breakdown, streaks, milestone badges, session history, AI-generated weekly coach summary.

## Capabilities and Constraints

- AI scoring provider is configurable per deployment (Gemini / OpenRouter / OpenAI); realtime voice via OpenAI Realtime or Gemini Live.
- Backend enforces authorization itself using the service-role key; Supabase RLS is defense-in-depth, not the primary boundary.
- Admin panel covers RBAC, audit log, AI cost/margin dashboard, reminders, and lead tracking.
- Open/undecided: final scope and ship date for Reading, Listening, Vocab, and the full timed Mock Test.

## Brand Commitments

- Name: SpeakOET. Domain: speakoet.com.
- No formally confirmed voice/tone or visual identity beyond the current live site — treat as open rather than inferred.

## Evidence on Hand

No real testimonials, user results, or case studies exist yet — pre-launch/early stage. Design must not fabricate social proof (fake reviews, invented user counts, made-up press). Use founder story, product mechanism, or live demo in its place.

## Product Principles

1. Full-syllabus depth over single-skill depth — every module must be credible against the real OET rubric, not a placeholder.
2. Practice must feel exam-real (live roleplay, real rubric) so confidence transfers to the actual test.
3. Affordable, fully self-serve alternative to human tutors and classroom courses — no sales-assisted onboarding required.
4. Ship honest claims only — never state a module, result, or proof point that isn't real yet (see Evidence on Hand).

## Accessibility & Inclusion

No specific accessibility requirement confirmed beyond standard web practice (WCAG-level not yet set).
