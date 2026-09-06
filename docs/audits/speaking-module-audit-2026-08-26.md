# SpeakOET Speaking Module — Deep Technical & Product Audit

**Date:** 2026-08-26
**Scope:** `backend/app/routers/speaking.py`, `backend/app/routers/speaking_realtime.py`, `backend/app/services/{ai_scoring,pronunciation,tts_service,plan_gating,realtime/*,skill_graph,observation_service,coaching_messages}.py`, `frontend/app/practice/speaking/*`, `frontend/app/hooks/{useSpeakingSession,useRealtimeSpeakingSession,useSttStream,useAudioPlayback}.ts`
**Method:** Full read of the above files (no assumptions), traced end-to-end for both voice pipelines, cross-checked scenario seed data against the prompt builder, checked test coverage. No code was changed.

---

## 1. Executive Summary

SpeakOET's Speaking module is real, live, and more sophisticated than a typical "chat with an AI patient" feature. Concretely, it already has:

- **Two parallel voice pipelines**: a legacy turn-based pipeline (Deepgram streaming STT → LLM text turn → Google TTS) and a genuinely modern **realtime voice pipeline** (OpenAI Realtime API / Gemini Live over WebSocket, full-duplex audio, server-side barge-in), staged-rolled-out by user-id hash (`REALTIME_ROLLOUT_PCT`, `frontend/app/practice/speaking/shared.ts:114-122`), with automatic fallback to the legacy pipeline if the realtime provider dies mid-session.
- **OET-aligned 9-criterion scoring** (empathy, patient's perspective, providing structure, information gathering, information giving, intelligibility, fluency, appropriateness of language, grammar), weighted 60/40 clinical/linguistic exactly as OET does (`backend/app/services/ai_scoring.py:544-605`).
- **A deterministic jargon-detection safety net** on the legacy path (`detect_jargon`, `ai_scoring.py:341-358`) plus a persona-instructed equivalent for the realtime path — this is the one behavior the landing page explicitly sells, and it exists in both pipelines, with the tradeoffs documented in code comments.
- **Session quota, cost tracking, rate limiting, and a circuit breaker** wired through every AI call (`sessions.py`, `cost_tracking.py`, `cost_circuit_breaker`), so nothing here is a demo — it is billed and capped like production infrastructure.
- **A skill-graph feedback loop**: every scored session pushes 9 criterion scores into `user_skill_stats`, and the results page surfaces a weakest-skill recommendation with a "next best scenario" CTA (`_build_speaking_insights`, `speaking.py:695-757`).

**What is missing that matters most for realism and training value:**

1. **The AI patient has no persistent internal state.** Every turn is one stateless LLM call replaying the same static card plus the raw conversation history. There is no tracking of *what's already been revealed*, *how the patient's emotional state has evolved*, or *what the nurse has and hasn't done yet*. The card says "reveal X only if asked" but nothing enforces or even monitors this across turns — it's pure prompt-compliance, unverified. This is why the experience reads as "a chatbot playing a role" rather than "a simulated patient with continuity."
2. **Scoring is a single LLM judgment pass with no structural grounding.** The examiner prompt is well-written and criterion-aligned, but there is no deterministic evidence extraction (e.g., "did the nurse's turns include a question about medication history") backing any score — feedback is only as evidence-based as the model chooses to make it, with no code-level enforcement that every score cites a real quote.
3. **No Practice / Exam / Challenge mode split exists.** Every student gets the same single experience — no strict-timing exam simulation, no coached practice with hints, no deliberately difficult patient mode.
4. **Scenario content has schema drift.** The older, larger portion of the seed library (`seed_scenarios.py`) uses a leaner `interlocutor_card` shape (`persona`, `emotional_triggers`, `questions_patient_will_ask`, `information_to_withhold`) that does not populate the fields the prompt builder actually reads (`patient_name`, `age`, `condition`, `mood`, `background` — see `ai_scoring.py:388-393`). The newer admin-generation schema (`speaking.py:1109-1135`) fills all of these. Net effect: a large fraction of scenarios silently hand the model "Age: adult", "Condition: Not specified", "Mood: Cooperative" regardless of the actual scenario, which measurably weakens persona fidelity exactly where the content library is deepest.
5. **A defined "technique" library for speaking already exists in the skill registry** (`setting_context`, `empathy_validation`, `chunking_signposting` — `skill_registry.py:116-118`) but is never referenced by any grading or coaching code path (confirmed: zero matches in `technique_progress.py`, `technique_grading.py`, `coach.py`). This is a built-but-orphaned asset — the cheapest possible win is wiring it up before building anything new.

The realtime voice architecture is the standout strength here and should not be touched structurally. The examiner-realism gap is a prompt/state-management problem, not an infrastructure problem — it's addressable incrementally on top of what exists, which is exactly the recommendation this audit makes.

---

## 2. Current Speaking Architecture

### 2.1 Two pipelines, one component tree

```
frontend/app/practice/speaking/page.tsx      (state owner: phase, scenario, history, sessionId)
        │
        ├─ SelectPhase.tsx                    (scenario picker, filters, recommendations, resume-in-progress)
        │
        └─ SpeakingSession.tsx (dynamic-imported, code-split)
                │
                ├─ useSpeakingSession()        ── legacy pipeline
                │      ├─ useSttStream()        → WS /speaking/stt/stream  (Deepgram Nova, streaming)
                │      └─ useAudioPlayback()     → POST /speaking/tts      (Google Cloud TTS, MP3 blob)
                │
                └─ useRealtimeSpeakingSession()  ── realtime pipeline
                       └─ WS /speaking/realtime/stream (raw PCM16 both directions)
                              └─ backend picks OpenAI Realtime or Gemini Live via VOICE_PROVIDER
```

`inRealtimeRollout(userId)` (`shared.ts:116-122`) deterministically buckets a user into realtime vs. legacy by a hash of their id, so the same user always gets the same pipeline session-to-session, but the rollout percentage can be raised without a deploy. If the realtime provider fails mid-session (`onProviderUnavailable`), `SpeakingSession.tsx:172-191` flips `useLegacyFallback` and hot-swaps to the legacy hook using the same `sessionId` and `convHistory` — the quota charge already made is preserved and the user never sees a dead end.

### 2.2 One turn, legacy pipeline

1. Student taps orb → `useSttStream` opens `WS /speaking/stt/stream`, authenticates with the Supabase token, and proxies raw MediaRecorder audio to Deepgram Nova (`speaking.py:167-470`). Deepgram's own endpointing (1500ms) plus a client-side 1200-1500ms silence timer (`useSttStream.ts:227-243`) decides when an utterance is "final."
2. Final transcript → `POST /speaking/chat` (`speaking.py:806-896`): loads the scenario's `interlocutor_card`, calls `get_patient_response()` (one `_call_ai` LLM call, `purpose="patient_roleplay"`, temp 0.3, max 200 tokens), appends the reply to history.
3. `speakPatientReply()` fires `POST /speaking/tts` immediately (before history/session-id state updates) so audio starts playing at the earliest possible moment (`useSpeakingSession.ts:136-150`).
4. If `autoListen` is on, the mic reopens automatically once the audio element's `onended` fires (`useAudioPlayback.ts:31-35` → `useSpeakingSession.ts:148-150`) — not a fixed delay, an actual playback-end signal.
5. On "End Session": `POST /speaking/score` runs the 9-criterion examiner prompt once over the full transcript, saves a `submissions` row, and (in parallel) `POST /speaking/pronunciation` runs Azure phoneme scoring (Elite) or a regex-based Indian-accent pattern scan (everyone else) over the session-long recording.

### 2.3 One turn, realtime pipeline

The realtime router (`speaking_realtime.py`) is provider-agnostic by design: `RealtimeProviderAdapter` (`realtime/base.py`) is a 5-method interface with **zero business logic** — auth, quota, session timers, cost tracking, and fallback all live in the router, identical regardless of which provider is active. Two adapters exist today, `OpenAIRealtimeAdapter` and `GeminiLiveAdapter`, each translating one wire protocol into canonical events (`SessionReady`, `TranscriptDelta`, `TranscriptFinal`, `ResponseDone`, `Interrupted`, `ProviderError`).

Flow: client opens `WS /speaking/realtime/stream` → sends `{token, scenario_id, session_id}` → server validates, charges/reuses quota, builds the persona system prompt (`_build_realtime_system_prompt`, `speaking_realtime.py:143-207`), connects to the provider, and streams `session.ready` back with the **provider's actual required sample rates** (OpenAI 24kHz both ways, Gemini 16kHz in / 24kHz out) so the frontend's `AudioWorklet` captures at the right rate from the start — this is a real cross-provider abstraction, not a stub. Audio flows as raw binary WebSocket frames both ways; barge-in is server-side VAD (`input_audio_buffer.speech_started` on OpenAI, `serverContent.interrupted` on Gemini) → `Interrupted` event → frontend stops playback immediately and the backend cancels the in-flight response (explicit `response.cancel` for OpenAI; a no-op for Gemini, whose VAD already auto-cancels server-side — `gemini_adapter.py:140-148`).

Session hard-caps at 5 minutes (`REALTIME_SESSION_MAX_SECONDS=300`) with a warning at 4:30 (`REALTIME_SESSION_WARNING_SECONDS=270`) — this matches real OET role-play timing (~5 minutes per role-play) closely.

### 2.4 Scoring, skill graph, and mock test integration

`POST /speaking/score` (`speaking.py:899-1008`) is plan-aware: it picks `speaking_scoring_free` vs `speaking_scoring_premium` as the AI-registry purpose (so admins can point different tiers at different models without a deploy), always scores all 9 criteria (`get_scoring_criteria_count` — differentiation is by model quality, not criteria depth), and on success writes the raw criterion scores through `validate_and_normalize()` into `record_skill_observations()`, which feeds `user_skill_stats` (EMA-based) and drives the "weakest skill" line on the results page and the scenario recommender.

Speaking also serves as the last two role-plays of the Full Mock Test (`mock.py`) — same component tree, but `mockRoleplay` prop swaps the stepper for "Role play N of 2" labeling, hides per-roleplay scores until both are done, and reports completion back to the mock controller (`finishMockRoleplay`, `page.tsx:297-324`).

---

## 3. Current Features Inventory

**Exists and works (confirmed by code, not assumed):**
- Scenario picker with search/specialty/difficulty/completion filters, personalized "Recommended for you" row (unattempted-first, then weakest-scored — `_recommend_scenarios`, `speaking.py:609-686`), and resume-in-progress via localStorage.
- 3-minute reading/preparation phase (`PREP_SECONDS=180`) matching real OET prep timing, with a live countdown and "Start Early" escape hatch.
- Typed-response fallback for both pipelines when mic/STT fails (though realtime's typed path is stubbed — see §6).
- Deterministic jargon interrupt (legacy) that returns a random one of 4 in-character "I don't understand that word" lines *without even calling the LLM* when an unexplained medical term is detected (`detect_jargon`, `ai_scoring.py:341-358`) — cheap, fast, 100% reliable on the legacy path.
- Persona-instructed jargon rule + no-prompt-leak rule for the realtime path (model-compliance, not deterministic — explicitly flagged as a trade-off in the code comment, `speaking_realtime.py:156-166`).
- Prompt-leak detection + one retry on the legacy path (`_PROMPT_LEAK_KEYWORDS`, `ai_scoring.py:441-455`) with a safe canned fallback if the retry still leaks.
- Prompt-injection defense on the scoring path: transcript sanitization (HTML-tag stripping, NFKC normalization against homoglyph tricks, injection-keyword scan) plus a heuristic "suspicious" flag when injection keywords co-occur with all-high scores (`_sanitize_transcript`, `ai_scoring.py:32-50`, `680-700`).
- Plan-gated voice/model tiers: free-trial-first-session gets premium voice + premium scoring once; Pro/Elite always do; Basic/Free otherwise get WaveNet TTS + the free-tier scoring model.
- Full cost instrumentation: every LLM/TTS/STT/realtime call logs to `ai_usage_events` with per-call cost estimate or metered actuals (`_persist_realtime_metrics` prefers OpenAI's real token usage over the wall-clock estimate when available — `speaking_realtime.py:283-291`).
- Rate limiting per endpoint (`tts`, `score`, `transcribe`, `pronunciation`, both stream websockets) via a sliding-window limiter, plus a global cost circuit breaker checked before every AI-costing action.
- Session-quota integrity: a session is charged exactly once; a failed first-turn AI call refunds the charge (`release_session_charge`); a second scoring attempt on an already-scored session gets a 409, but a *failed* scoring attempt (provider outage) can be retried without re-charging.
- Post-session pronunciation: Azure phoneme-level (Elite) or a regex-based Indian-English mispronunciation pattern list (everyone else) — see §6 for depth concerns.
- Skill-graph weakness tracking + "Retry — Focus on {weakest criterion}" CTA + cross-session insights card comparing today's session to rolling history.
- Full transcript persistence for admin review (`session_transcripts` table, realtime path only — see §12).
- Reconnect-with-backoff on the realtime socket (5 attempts, exponential, mic/AudioContext left running across attempts) — a genuinely good resilience detail most teams skip.

**Partially implemented:**
- **Speaking "techniques"** (`setting_context`, `empathy_validation`, `chunking_signposting`) are registered in the skill graph's content model but never surfaced in any UI or referenced by any grading path — defined, never used.
- **Typed input on the realtime pipeline** exists as an input box but just shows an error telling the user to speak instead (`useRealtimeSpeakingSession.ts:556-565`) — it's a UI affordance with no backend behind it for that pipeline.
- **Attempt comparison** (`compare_attempts`) exists and is wired to the UI, but is a single LLM call over two 500-char transcript excerpts with no structural diffing — genuinely useful copy, thin analysis underneath.
- **Pronunciation feedback** for non-Elite users is a hardcoded 26-word regex list of Indian-English patterns (`INDIAN_ACCENT_PATTERNS`, `pronunciation.py:32-82`) — real, but shallow and static.

**Missing entirely:**
- Practice / Exam / Challenge mode distinction.
- Any state machine tracking what the patient has/hasn't revealed across turns, beyond "the LLM read the same card again."
- Any deterministic behavioral scoring signal (e.g., did the nurse ask an open question before a closed one, did they summarize) feeding the LLM judge as structured evidence rather than leaving 100% of judgment to one prompt.
- Replay/highlight-weak-moments UI on the transcript.
- Adaptive difficulty across sessions.
- Any indication to the student, in real time, of *why* the patient reacted a certain way (a "coach mode" overlay).

---

## 4. Real OET Comparison

Real OET Speaking has: role-play card → 3 min prep → ~5 min role-play with a trained interlocutor who follows a card but adapts in real time to what the candidate says → examiner scores live off a rubric.

| Real OET element | SpeakOET today | Verdict |
|---|---|---|
| Role-play card preparation | 3-min timed prep screen showing setting/role/tasks, "Start Early" option | **Matches** |
| ~5 min role-play duration | Realtime path hard-caps at 5:00 with a 4:30 warning; legacy path has no session-length cap (only a 10-min STT-stream reconnect cap) | **Matches on realtime; unbounded on legacy** |
| Interlocutor follows a card | Both pipelines pass the card into the system prompt every turn | **Matches structurally** |
| Interlocutor adapts to what's actually said | Model re-reads the same static card + raw history each turn; nothing tracks "have I already used this trigger," "have I already answered this," "has the nurse been dismissive twice now" | **Gap — no state, so adaptation is entirely improvised per-turn, not a designed arc** |
| Natural turn-taking, interruption | Realtime path: real server-side VAD barge-in. Legacy path: rigid mic-closes-while-AI-speaks turn structure | **Matches on realtime; chatbot-like on legacy (currently the default for 80% of users)** |
| Difficult/resistant/confused patients | `mood` field exists in the schema and newer scenarios set it; many older seeded scenarios never set `mood` so it silently defaults to "Cooperative" regardless of intended difficulty | **Partially implemented — content-dependent, not guaranteed** |
| Misunderstandings, hesitation | Legacy prompt explicitly instructs "occasionally misunderstand" (`ai_scoring.py:413`); no equivalent instruction found in the realtime prompt | **Present on legacy, missing on realtime** |
| Clarification requests, resistance | Present as prompt instructions only, unverified/unmeasured — no telemetry on whether the model actually does this | **Unverified compliance, not a guarantee** |
| Structured rapport → gather → explain → advise → close | `providing_structure` is a scored criterion, but nothing enforces the *patient's* responses to actually follow that arc — a nurse who skips straight to advice gets scored down, but the patient doesn't push back on the missing structure | **Scored after the fact, not trained into the interaction itself** |

**Bottom line:** the mechanics (timing, card structure, criteria) map onto real OET closely. The felt difference — "this is a chatbot, not a patient" — comes from the complete absence of turn-to-turn state: nothing in this system remembers that it already revealed the indigestion pain, already asked "am I dying?", or already got interrupted rudely twice. Every turn, the model is handed the same static card and told to improvise again. This is Gap #1 in §10.

---

## 5. OET Criteria Audit

`ai_scoring.py:544-559` implements the exact 9 OET Speaking sub-test criteria with descriptors that map closely to OET's official band language ("appropriate register," "checked patient understood," "range of grammar structures"). Assessment per criterion:

| Criterion | Current implementation | Gap | Risk to student | Recommendation |
|---|---|---|---|---|
| **Empathy** | LLM scores 0-6 against a written rubric with example phrasing ("I understand this is worrying") | Purely LLM judgment; no structural signal (e.g., count of emotion-acknowledging phrases near a patient's emotional-trigger turn) feeds the judge | A borderline case gets no more evidence-grounding than the model chooses to provide | Feed the judge a lightweight structural hint: which turns immediately followed a patient emotional-trigger line, so feedback can say "you didn't acknowledge X right after the patient said Y" |
| **Patient's perspective** | Same LLM-judgment pattern | Same | Same | Same |
| **Providing structure** | Scored against "introduce → enquire → explain → advise" sequence, with an explicit penalty ("deduct 0.5") if no roleplay card was provided | Deterministic penalty is good, but the sequence-check itself is left to the LLM's read of the transcript | Reasonable, actually one of the stronger criteria as implemented | Low priority — already has a deterministic anchor point |
| **Information gathering** | "open questions first then closed... summarise and check understanding" | No code counts actual question types (open vs. closed) or detects a summarizing utterance | Feedback can be vague ("could gather more information") without pointing at a specific missed opening | A cheap regex/heuristic pass (question mark + 5W1H opener vs. yes/no opener) as a structured hint, not a hard score, would sharpen this measurably |
| **Information giving** | "clear, concise, jargon-free... given as suggestions not orders... checked patient understood" | `detect_jargon` (legacy) already flags unexplained medical terms in real time — that same signal isn't passed forward into scoring as evidence | Two students who both trigger 3 jargon interrupts could get different-looking feedback text purely by luck of model phrasing | Attach the actual jargon-interrupt log (which terms, how many times, whether explained on retry) as scoring input — this is data the system already has and currently throws away after the turn |
| **Intelligibility** | LLM judges "clear... correct word stress/intonation" **from a text transcript** | The scorer never receives audio — it cannot actually assess stress, intonation, or rhythm, only spelling/word choice in the STT transcript | This criterion's score is largely fabricated from text; a nurse with perfect written English but poor spoken intelligibility would be over-scored, and vice versa for STT transcription errors mis-attributed to the speaker | This is the single most important scoring gap — see §7/§8. Either (a) feed Azure's pronunciation accuracy/fluency scores (already computed for Elite, §6) into this criterion as real signal, or (b) rename/reframe what's being measured for non-Elite users so the score isn't implicitly claiming audio-based judgment it never performed |
| **Fluency** | "smooth pace... minimal filler words" — same text-only limitation as Intelligibility | STT transcripts often strip filler words/pauses entirely (Deepgram's `smart_format=true`), so the raw signal this criterion needs may not even survive into the transcript | Same fabrication risk as above, arguably worse since filler-word detection depends on STT verbatim fidelity that's actively being smoothed away | Disable `smart_format` (or capture a parallel verbatim transcript) specifically for the scoring input, and pass actual turn-timing gaps (which the system already has via message timestamps) as a structural proxy for pacing |
| **Appropriateness of language** | "suitable register... medical terms explained in plain language" | Same text-only constraint, but this one is genuinely text-assessable (register/word choice) — no real gap here | — | Low priority |
| **Grammar** | "range of grammar structures... accurately... varied vocabulary" | Text-assessable, no real gap | — | Low priority |

**Overall:** 5 of 9 criteria (empathy, patient's perspective, information gathering, information giving, providing structure) are reasonably assessable from a text transcript and the current single-LLM-pass approach is defensible for them, if thin on evidence-grounding. The other 2 — **intelligibility and fluency** — are being scored from a channel (text transcript) that cannot actually carry the signal the criterion claims to measure. This is the most examiner-defensibility-relevant finding in this audit.

---

## 6. AI Patient Behaviour Audit

**Personality:** The `mood` field (cooperative/anxious/confused/angry/resistant, per the admin-generation schema, `speaking.py:1128`) is the only explicit personality lever, and it only reaches the model when a scenario actually sets it — confirmed absent from every `interlocutor_card` in `seed_scenarios.py`'s legacy shape (§1, finding 4), so those scenarios (a large fraction of the library) default every patient to "Cooperative" regardless of intent. **This alone likely explains a meaningful share of "feels flat" feedback** if it's been raised before — check whether user complaints skew toward the older scenario set.

**Patient knowledge / information withholding:** `information_to_withhold` is passed as a prompt instruction ("only reveal if asked directly") on both pipelines. There is **no verification mechanism** — nothing checks whether the model actually withheld the information or volunteered it anyway. This is the single clearest example of "AI vs. real OET" gap: a real trained interlocutor mechanically will not volunteer withheld information; this system asks an LLM to remember not to, every single turn, with no code checking compliance. Spot-checking this against live sessions (cheap: grep session_transcripts for withheld-info strings appearing before the nurse's matching question) would quantify how often it actually leaks.

**Emotional state changes based on nurse behavior:** The prompt says to react to `emotional_triggers` and to show emotion the nurse "must acknowledge," but there is no mechanism differentiating "nurse showed empathy → patient calms" from "nurse ignored concern → patient escalates" beyond what the LLM improvises fresh each turn from the raw history. Real conversational branching (a state machine: `anxious → (empathy shown) → reassured` vs. `anxious → (jargon/dismissiveness) → more anxious/defensive`) does not exist.

**Role-play realism — specific findings:**
- "Stays within scenario facts" — enforced only by instruction, not validated. A hallucinated fact (e.g., inventing a new symptom not in the card) would not be caught by anything in this codebase.
- "Avoids long monologues" — enforced by `max_tokens=200` on the legacy path (a hard cap, effective) and by an instruction only ("2-4 sentences") on the realtime path (softer, since realtime doesn't token-cap the same way).
- "Occasionally misunderstands" — explicit instruction on legacy prompt (`ai_scoring.py:413`), **absent** from the realtime system prompt (`speaking_realtime.py:173-207`) — a persona-fidelity regression introduced by the newer pipeline that the older one didn't have.
- "Never breaks character / no prompt leak" — legacy path has a genuine safety net (detect leak → retry → canned fallback, `ai_scoring.py:441-455`); realtime path has instruction only, with the code comment itself acknowledging there's no complete-response scan possible for streamed audio (`speaking_realtime.py:160-166`) — an inherent, documented limitation of realtime architectures generally, not a bug, but worth knowing the two pipelines have meaningfully different guarantee levels here.

---

## 7. Voice/Realtime Audit

This is the strongest part of the system as built. Specific technical merits:
- Provider-agnostic adapter interface with zero business logic in the adapters (`realtime/base.py`) — genuinely clean separation, easy to add a third provider.
- Correct handling of provider-specific quirks: OpenAI's `response_cancel_not_active` race is explicitly absorbed as benign rather than torn down as an error (`openai_adapter.py:152-160`); Gemini's lack of a client-cancel message is documented as a deliberate no-op, not a missing feature (`gemini_adapter.py:140-148`).
- Real audio-config negotiation: sample rates are provider-specific and communicated to the frontend via `session.ready` rather than hardcoded — this is why swapping `VOICE_PROVIDER` doesn't require a frontend deploy.
- Reconnect-with-backoff (5 attempts, exponential, mic/AudioContext untouched across attempts) is a genuinely above-average resilience pattern.
- Gapless audio scheduling via explicit `nextPlaybackTimeRef` bookkeeping (`useRealtimeSpeakingSession.ts:200-213`) rather than "play chunks as they arrive," which avoids audible stutter between TTS chunks.

**Weaknesses / unverified claims (flagged in the code itself, worth taking seriously):**
- `capabilities.py`'s `unverified` tuple explicitly flags that Gemini's transcript-delta behavior (incremental vs. cumulative) has never been confirmed against a live session — if wrong, patient/nurse transcripts on Gemini would show visible duplication or garbling. **This should be manually verified before raising Gemini's rollout share.**
- The realtime jargon rule and no-leak rule are both explicitly acknowledged in code comments as "model-compliance, not a guarantee," with a direct recommendation to spot-check before scaling rollout — this has apparently not yet been done (per the memory record noting `VOICE_PROVIDER` config drift and no Gemini key configured, Gemini specifically has never run in production).
- Typed input is a dead end on the realtime pipeline (§3) — a student whose mic fails mid-realtime-session has no working fallback within that session; they'd need `onProviderUnavailable` to fire (which only happens on a *provider* failure, not a *microphone* failure) to get to the legacy pipeline's working typed-input path.
- No latency instrumentation surfaced anywhere — `time_to_ready_ms` is captured and persisted (`_persist_realtime_metrics`) but there's no dashboard or alerting referenced anywhere in the codebase for it; it's write-only telemetry today.
- Legacy pipeline's turn-taking (mic closes while AI "speaks," reopens only after playback ends) is the default experience for 80% of users (`REALTIME_ROLLOUT_PCT=20`) and structurally cannot interrupt or be interrupted — this is the most chatbot-like part of the whole experience and it's what most students are actually getting today.

**Does it feel like speaking to a real person?** On the realtime path: closer than most competitors, genuinely. On the legacy path (still the majority default): no — rigid turn-taking with no barge-in is the biggest single UX gap between what most students experience and what OET actually requires (interrupting, being interrupted, natural overlap).

---

## 8. Scoring Audit

**Pipeline:** transcript-only, single LLM call (`purpose=speaking_scoring_free` or `_premium`), one retry on JSON-parse failure, deterministic post-processing (clamp scores 0-6, compute weighted overall band in Python, not by the model — good practice, prevents the model from fabricating an inconsistent overall score).

**What the scorer receives:** full text transcript (nurse + patient turns), the scenario's task list, and nothing else. **What it does not receive:** audio, timing/pause data, interruption counts, the jargon-interrupt log, or any structured behavioral signal.

**Defensibility check, criterion by criterion:** covered in §5. Net: **Intelligibility and Fluency are not currently defensible** — they are named as if audio-based but are actually inferred from a possibly-smoothed STT transcript. This is the top scoring-integrity issue found.

**Failure handling:** genuinely well-built — `provider_failure` distinguishes an outage from a bad response so a real 503 is returned instead of a fake 0/6 (`speaking.py:957-965`); a session is only claimed-for-scoring on success, so a failed scoring attempt can be retried without double-charging or double-scoring (`claim_session_for_scoring`); a prompt-injection heuristic exists on the scoring path specifically (`suspicious` flag) even though the equivalent risk on `get_patient_response` (jailbreaking the *patient*, not the *scorer*) has no analogous detection.

**Score inflation / instability risk:** not measured anywhere in the codebase — there is no eval harness, no golden-transcript regression test, and no admin view (found) that tracks score distribution drift over time or across model changes. Given that `Admin > AI Models` can swap the underlying model per purpose without a deploy, a silent quality regression from a model change would currently be invisible until a student or support ticket surfaces it.

---

## 9. Feedback Audit

**What's already good:** per-criterion feedback is explicitly instructed to "reference the specific words or moment from the transcript" (`ai_scoring.py:596-600`), scaled up to 2-3 sentences with "explain why it matters + name one specific thing that would raise the score" for Pro/Elite (`enhanced_feedback`). `top_strength`/`top_improvement`/`examiner_summary` give a clear headline. The insights card adds a second, independent layer: today's strongest skill + the learner's cross-session weakest skill (from real history once `WEAKNESS_MIN_ATTEMPTS=2` is met) + a concrete next-scenario recommendation.

**What's missing for the "bad feedback → better feedback" bar this audit was asked to check against:**
- No enforcement that the "specific words or moment" instruction is actually honored — it's a prompt request, not a validated output field. A lazy or degraded model response could produce generic "improve your fluency"-style feedback and nothing in the pipeline would catch or flag it.
- No mistake-replay UI: the transcript is shown in full, but nothing highlights *which turns* the feedback is talking about. A student reading "you used medical jargon at 2:14" (if the model even gives a timestamp, which it currently has no way to since it never receives timing) has no way to jump to that moment.
- No aggregation of the deterministic jargon-interrupt data into feedback — this is free, already-computed evidence being thrown away (same gap as §5's Information Giving criterion).
- Comparison feature (`compare_attempts`) is real but thin — 500-char transcript excerpts, no structural diff, so "what improved and why" is another single LLM guess rather than a grounded before/after.

---

## 10. Biggest Gaps

### P0 — Critical (directly caps realism or training value)
1. **No conversational/patient state across turns.** The model re-reads the same static card every turn with no tracking of what's been revealed, what's been asked, or how the emotional arc has moved. This is the root cause of "feels like a chatbot." *(§4, §6)*
2. **Intelligibility and Fluency are scored from text alone but presented as if audio-assessed.** These are 2 of 9 criteria (22% of the score) resting on a channel that structurally cannot carry the signal. *(§5, §8)*
3. **Scenario schema drift silently flattens patient personality** for a large fraction of the content library (missing `mood`/`age`/`condition`/`background` on older seeded scenarios → all default to generic/cooperative). *(§1, §6)*
4. **Legacy pipeline (80% of traffic today) has no barge-in / natural turn-taking** — rigid mic-closes-while-AI-speaks structure is the single biggest gap between what most students actually experience and what a real OET conversation requires. *(§7)*

### P1 — High (materially improves learning)
5. **No Practice / Exam / Challenge mode split** — one-size experience regardless of whether a student wants coaching, strict simulation, or deliberately difficult practice. *(§11)*
6. **Deterministic signals already computed (jargon interrupts, turn timing, withheld-info compliance) are discarded instead of feeding scoring/feedback as structured evidence.** Cheap to fix, currently just thrown away. *(§5, §9)*
7. **The already-built "technique" library (setting_context, empathy_validation, chunking_signposting) is completely unwired** — a coaching layer that already exists in the data model but touches nothing. *(§1, §3)*
8. **Realtime pipeline's persona prompt lost the "occasionally misunderstand" instruction** present in the legacy prompt — a regression, not a design choice, worth reconciling as the rollout percentage rises. *(§6)*
9. **No eval harness or score-distribution monitoring** — a silent model swap via Admin > AI Models could regress scoring quality invisibly. *(§8)*

### P2 — Medium (useful, not urgent)
10. Typed-input dead end on the realtime pipeline when mic fails mid-session.
11. Gemini's transcript-delta behavior is explicitly unverified against a live session — should be confirmed before its rollout share increases.
12. Pronunciation feedback for non-Elite users is a static 26-pattern regex list — real but shallow; could be extended without needing Azure.
13. No mistake-replay / highlighted-weak-moment UI on the transcript.
14. Attempt comparison (`compare_attempts`) is a thin single-LLM-call diff over 500-char excerpts.

### P3 — Nice to have
15. Latency telemetry (`time_to_ready_ms`) is captured but has no dashboard/alerting consumer.
16. No adaptive difficulty across sessions (scenario recommender ranks by weakest-score, but doesn't adjust *within* a scenario).
17. No downloadable/shareable score history trend view beyond the single cross-attempt comparison.

---

## 11. Recommended Features

Filtered to what materially changes the training value given what already exists — not a wishlist.

- **Turn-tagged scenario state** (see §13) — the single highest-leverage feature. A small per-session JSON blob (not a new subsystem) tracking which `information_to_withhold` items have been revealed and which `emotional_triggers` have fired, injected back into the prompt each turn ("You have already told the nurse about X — do not repeat it as new information unless asked again"). This directly fixes P0 gaps #1 and, partially, the withholding-compliance gap in §6.
- **Structured evidence pre-pass for scoring** — a cheap deterministic extraction step (question-type tally, jargon-interrupt log, turn-timing gaps) computed in Python and handed to the scoring prompt as labeled input, not asked of the LLM to infer from raw text. Turns 3 of the 9 criteria (information gathering, information giving, fluency) from "trust the model" into "the model reasons over real evidence."
- **Wire the existing technique library into the results page** — when a scored session's weakest criterion maps to `empathy_validation` or `chunking_signposting`, surface the matching technique's description as a concrete "how to improve" tip. This is a join against data that already exists (`skill_registry.py:116-118`), not a new feature build.
- **Reconcile the realtime persona prompt with the legacy one** (misunderstanding instruction) — a one-line prompt fix, not a project.
- **Practice / Exam / Challenge mode** (see §12 for how this maps onto existing code) — the single biggest *product* differentiator on this list, and buildable as a thin layer over the existing session/scoring pipeline rather than a new one.
- **Mistake replay on the results transcript** — once turns carry timing (already captured for realtime sessions in `session_transcripts`), highlighting the specific turn a piece of feedback refers to is a frontend-only change given the backend data already exists for realtime sessions.
- **A lightweight speaking eval set** — 10-20 golden transcripts with known expected score ranges, run automatically whenever the underlying AI model for `speaking_scoring_*` changes in Admin > AI Models. Directly closes P1 gap #9.

Deliberately **not** recommended right now: full branching dialogue trees, a from-scratch state-machine engine, or replacing either voice pipeline. The realtime architecture is good; the gap is in what state/evidence is fed into the existing prompts, not the transport layer.

---

## 12. Separating Training Mode and Exam Simulation Mode

This makes sense, and it maps cleanly onto what already exists rather than requiring new infrastructure:

- **Exam Mode** = today's behavior almost exactly. Strict timing (already exists — 3 min prep, 5 min realtime cap), no coaching, score only at the end. The only change needed: make sure the legacy pipeline's session length is also capped (§10, gap noted) so "exam mode" timing is consistent regardless of which voice pipeline a student lands on.
- **Practice Mode** = the same session/scoring pipeline, but with two additions: (a) a visible "hint" affordance that surfaces the matching technique from the skill registry (§11) mid-conversation, not just after scoring, and (b) allow the student to end early and re-listen/retry a single turn rather than the whole conversation. Both are additive UI/state changes on top of the existing `convHistory` array — no new backend concept required beyond flagging the session as `mode=practice` when charging quota (or not charging quota at all for practice — a product decision, not a technical one).
- **Challenge Mode** = the same patient-persona prompt, but with a scenario-level flag that deliberately increases `mood` intensity and forces more `emotional_triggers`/misunderstandings into the instructions. This is a prompt-content change (new scenario variants or a "difficulty modifier" appended to the existing system prompt builder), not new plumbing — `_build_realtime_system_prompt` and `get_patient_response`'s system prompt are both single string-builders that already take the card as input; a `difficulty_modifier` parameter is a small, additive change to both.

None of these three modes require touching the realtime transport, the scoring pipeline's shape, or the database schema in a disruptive way — they're best modeled as a `mode` field on the session/scenario selection, consumed by the existing prompt builders and by a couple of `if mode == 'practice'` UI branches. This keeps the recommendation consistent with §15 (incremental upgrades over a working system).

---

## 13. Technical Architecture Recommendations

- **Scenario/patient state**: add a small per-session mutable state object (e.g., `{revealed: [...], triggers_fired: [...], jargon_interrupts: [...]}`), updated after each turn and passed into the next turn's system prompt as a labeled "CONVERSATION STATE SO FAR" block. This is the mechanism behind §11's top recommendation. Cheapest implementation: store it in the same place `convHistory` already lives (frontend state, sent up each turn) rather than a new backend table — it only needs to survive one session, not persist.
- **Scoring evidence pipeline**: a pure-Python pre-pass function (no AI call) that takes the transcript + the already-existing jargon-interrupt log + turn timestamps, and produces a small structured JSON block appended to the scoring prompt. This is a few dozen lines next to `score_speaking`, not a new service.
- **Scenario content backfill**: a one-time migration pass over `seed_scenarios.py`-originated rows to populate `patient_name`/`age`/`condition`/`mood`/`background` from the existing `persona`/`setting` text (can be AI-assisted, one-shot, reviewed before going live) so every scenario — old and new — actually exercises the full persona template the prompt builder already supports.
- **Eval harness**: a small `pytest`-style fixture set of golden transcripts + expected score bands, run as a manual/CI check whenever a `speaking_scoring_*` purpose's model changes in `ai_model_purposes`. Given the test suite already has `test_speaking_chat_ai_failure.py`, `test_speaking_insights.py`, `test_speaking_realtime_router.py`, and `test_speaking_session_quota.py`, this fits the existing test-file convention rather than needing new tooling.
- **Gemini verification**: before raising rollout share on Gemini specifically, run one live manual session and confirm the incremental-vs-cumulative transcript question flagged in `capabilities.py`'s `unverified` tuple — a half-day task that de-risks a real correctness bug (visibly duplicated/garbled transcripts) before it reaches more users.
- **Cost/latency dashboard**: `time_to_ready_ms`, `interrupted_count`, `cache_hit_rate` are all already computed and persisted per session (`realtime_session_metrics` table) — wiring these into whatever admin view already surfaces `ai_usage_events` (per the AI usage cost tracking work already done) is a query-and-render task, not new instrumentation.
- **Do not** rewrite the adapter interface, the WebSocket transport, or the quota/session-charging model — all three are well-factored and correctly separated already.

---

## 14. Exact Files/Components to Modify

| Change | File(s) | Why |
|---|---|---|
| Persistent conversation state | `backend/app/services/ai_scoring.py` (`get_patient_response`, system prompt builder), `backend/app/routers/speaking_realtime.py` (`_build_realtime_system_prompt`) | Both are pure string-builders today; adding a `conversation_state` param is additive |
| Structural scoring evidence | `backend/app/services/ai_scoring.py` (`score_speaking`) | Where the scoring prompt is assembled; jargon log already exists via `detect_jargon` call sites in `speaking.py` |
| Scenario schema backfill | `backend/app/services/seed_scenarios.py` (source data), a new one-off migration/script (not a recurring service) | Root cause of the mood/age/condition defaulting gap |
| Realtime "occasionally misunderstand" parity | `backend/app/services/realtime import in speaking_realtime.py:143-207` (`_build_realtime_system_prompt`) | One-line prompt addition to match `ai_scoring.py:413` |
| Wire technique library into results | `frontend/app/practice/speaking/SpeakingSession.tsx` (results phase, near `feedback.insights` block, ~line 1122), `backend/app/routers/speaking.py` (`_build_speaking_insights`) | Join weakest criterion → matching technique row from `skill_registry.py` |
| Mode split (Practice/Exam/Challenge) | `frontend/app/practice/speaking/page.tsx` (add `mode` to session state + localStorage shape), `SelectPhase.tsx` (mode picker UI), `backend/app/routers/speaking.py` + `speaking_realtime.py` (accept/pass `mode` through to prompt builders) | Additive field through the existing flow, not a new pipeline |
| Legacy pipeline session cap parity | `backend/app/routers/speaking.py` (`/stt/stream`, currently only `STT_STREAM_MAX_SECONDS=600` — no equivalent to realtime's 300s conversation cap) | Exam-mode timing consistency across both pipelines |
| Eval harness | New `backend/tests/test_speaking_scoring_eval.py` alongside the existing `test_speaking_*` files | Matches existing test-file convention |
| Mistake replay | `frontend/app/practice/speaking/SpeakingSession.tsx` (transcript block, ~line 922) + realtime path's already-captured `session_transcripts` timing | Backend data exists for realtime sessions already |

---

## 15. Risks and Trade-offs

- **Conversation-state injection increases prompt length and per-turn cost slightly** (an extra block in every system prompt) — small (a few hundred tokens), and directly justified by the realism gain; not worth engineering around further given the existing cost-tracking infrastructure will simply reflect the small increase transparently.
- **Reconciling intelligibility/fluency scoring** (feeding Azure pronunciation data into the score, or reframing what non-Elite users see) is a **scoring-methodology change**, not a code change — it needs a product decision (does Elite's audio-based signal replace the free-tier's text-only guess, or do we relabel the free-tier criteria to be honest about what they measure?) before implementation. Flagging this explicitly as a decision point, not a build task.
- **Scenario schema backfill touches live content** — treat as a one-time reviewed migration with a rollback path (keep the original seed data), not a live AI-rewrite-in-place job.
- **Raising realtime rollout percentage before verifying Gemini's transcript behavior** risks visibly broken transcripts reaching more users — sequence the verification before the rollout increase, not after.
- **Mode split adds a new dimension to an already-tested quota/session-charging system** — the safest sequencing is Exam Mode first (== today's behavior, i.e., no quota-logic change at all), then Practice Mode (needs a decision on whether it consumes quota), then Challenge Mode (a content/prompt change only, no quota implications) — each phase in isolation instead of shipping all three at once.

---

## 16. Final Recommendation

Do not rebuild. The realtime voice architecture, the quota/cost/circuit-breaker infrastructure, and the OET-aligned scoring rubric are all genuinely solid engineering and should be the foundation everything else builds on. The actual gap between SpeakOET today and a training tool that "feels like a real OET interlocutor" is concentrated in a small number of specific, additive changes:

1. Give the patient persona memory across turns (state, not a new pipeline).
2. Stop discarding the deterministic signals the system already computes (jargon interrupts, timing) before they reach scoring/feedback.
3. Fix the content schema drift so every scenario — not just the newest ones — actually exercises the full persona template.
4. Be honest about what intelligibility/fluency scoring can and cannot claim from a text-only channel, and use the Azure signal that already exists for Elite users to make it real where it can be.
5. Ship the mode split as a thin flag through the existing pipeline, exam mode first since it requires zero behavioral change.

None of this requires new infrastructure. It requires making better use of data and structure the system has already built and is currently throwing away.

---

# Top 10 Changes I Should Make First

Ranked by realism/training-value gained per unit of engineering effort — not by raw importance, and not by ease alone.

1. **Add turn-to-turn conversation state to the patient prompt** (revealed info, fired triggers) — `ai_scoring.py` / `speaking_realtime.py` prompt builders. Highest realism gain for a genuinely small, additive code change.
2. **Feed the jargon-interrupt log into scoring as evidence** for the Information Giving criterion — data already computed, currently discarded. Near-zero engineering cost.
3. **Fix the realtime persona prompt's missing "occasionally misunderstand" instruction** — a one-line parity fix with the legacy prompt.
4. **Backfill scenario schema** (`mood`/`age`/`condition`/`background`) across the older seed-data scenarios — fixes silent personality-flattening across a large chunk of the content library.
5. **Wire the existing technique library into the results page's weakest-skill card** — joins data that already exists; no new subsystem.
6. **Ship Exam Mode as an explicit, named mode** (== current behavior, formalized) and cap the legacy pipeline's session length to match — makes today's default experience honestly labeled and timing-consistent across both pipelines.
7. **Add a structural question-type/pacing pre-pass feeding Information Gathering and Fluency scoring** — turns two of the weaker-grounded criteria into evidence-based judgments.
8. **Verify Gemini's transcript-delta behavior against a live session** before raising its rollout share — cheap, de-risks a real correctness bug.
9. **Build a small golden-transcript eval harness** for the speaking scoring prompts, run whenever the underlying model changes in Admin > AI Models — protects against silent scoring regressions.
10. **Design and ship Practice Mode** (hints from the technique library mid-conversation, retry-a-single-turn) as the first mode beyond Exam — the biggest genuinely new product surface on this list, sequenced last because it's the only one that needs a quota-behavior decision first.
