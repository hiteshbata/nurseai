# SpeakOET OET Speaking Evidence Specification

**Date:** 2026-08-28
**Scope:** Architecture/specification only. No code, schema, prompt, or scoring changes were made while producing this document. No model calls (Gemini/Sonnet/Opus/OpenRouter/embeddings) were made.
**Predecessor:** Speaking Module Audit (`docs/audits/speaking-module-audit-2026-08-26.md`) and the Step 17 Examiner Architecture Design (not present as a file in this repository or in this session's available context — its content was **not** consulted or relied on for this document; everything below is derived directly from the official PDF and a fresh read of the current codebase).

---

## 1. Source

The controlling source for every criterion, band, indicator, and scoring scale in this document is the uploaded PDF **"Speaking sub-test: Assessment criteria and level descriptors"** (2 pages, OET official document), read in full:

- Page 1 — **Linguistic Criteria**: a 4-column × 7-row table (Bands 6 down to 0) covering Intelligibility, Fluency, Appropriateness of Language, Resources of Grammar and Expression.
- Page 2 — **Clinical Communication Criteria**: five lettered indicator families (A–E, 19 indicators total: A1–A4, B1–B3, C1–C3, D1–D5, E1–E5) plus a single 4-point scoring scale (3/2/1/0).

No terminology has been substituted, no indicator has been renamed, and no category has been added or removed. Where the PDF is silent on something the task asked for (see §17), that silence is stated explicitly rather than filled in.

---

## 2. Complete Official Framework (9 Criteria)

| # | Family | Criterion | Score range | Source |
|---|---|---|---|---|
| 1 | Linguistic | Intelligibility | 0–6 | PDF p.1 |
| 2 | Linguistic | Fluency | 0–6 | PDF p.1 |
| 3 | Linguistic | Appropriateness of Language | 0–6 | PDF p.1 |
| 4 | Linguistic | Resources of Grammar and Expression | 0–6 | PDF p.1 |
| 5 | Clinical | Relationship Building | 0–3 | PDF p.2 |
| 6 | Clinical | Understanding & Incorporating the Patient's Perspective | 0–3 | PDF p.2 |
| 7 | Clinical | Providing Structure | 0–3 | PDF p.2 |
| 8 | Clinical | Information Gathering | 0–3 | PDF p.2 |
| 9 | Clinical | Information Giving | 0–3 | PDF p.2 |

**Important clarification the PDF itself makes structurally, not something inferred by this document:** the clinical page lists 19 lettered items (A1–E5) under the heading "Indicators," then gives **one** scoring scale (3–0) at the bottom of the page, not one scale per indicator. That layout is the PDF's own evidence that a criterion (A, B, C, D, or E) is the scored unit, and A1…E5 are the observable behaviours a rater uses as evidence *for* that one score — exactly the criterion/indicator distinction the task brief describes in Step 3. This document does not turn the 19 indicators into 19 separate scores.

---

## 3. Complete Clinical Indicator Tree (A1–E5)

```text
A. Relationship Building
  A1  initiating the interaction appropriately (greeting, introductions, nature of interview)
  A2  demonstrating an attentive and respectful attitude
  A3  adopting a non-judgmental approach
  A4  showing empathy for feelings/predicament/emotional state

B. Understanding & Incorporating the Patient's Perspective
  B1  eliciting and exploring the patient's ideas/concerns/expectations
  B2  picking up the patient's cues
  B3  relating explanations to elicited ideas/concerns/expectations

C. Providing Structure
  C1  sequencing the interview purposefully and logically
  C2  signposting changes in topic
  C3  using organising techniques in explanations

D. Information Gathering
  D1  facilitating the patient's narrative with active listening techniques, minimising interruption
  D2  using initially open questions, appropriately moving to closed questions
  D3  NOT using compound questions/leading questions
  D4  clarifying statements which are vague or need amplification
  D5  summarising information to encourage correction/invite further information

E. Information Giving
  E1  establishing initially what the patient already knows
  E2  pausing periodically when giving information, using the response to guide next steps
  E3  encouraging the patient to contribute reactions/feelings
  E4  checking whether the patient has understood information
  E5  discovering what further information the patient needs
```

All 19 indicators are carried through every table below. None omitted.

---

## 4. Linguistic Level Mapping (0–6)

Faithful summary, not verbatim reproduction. Each row states what a human examiner is listening for, and what a rater looks at to tell that band apart from its neighbour.

### Intelligibility

| Band | Meaning | What separates it from the band below |
|---|---|---|
| 6 | Pronunciation easily understood; stress/intonation/rhythm used effectively; L1 accent has no effect. | Band 5 still has occasional pronunciation/prosody slips or a noticeable accent — 6 has none. |
| 5 | Easily understood; a few pronunciation/prosody errors or a noticeable accent don't impede communication; minimal listener strain. | Band 4 causes strain "at times" — 5 causes none worth mentioning. |
| 4 | Easily understood *most* of the time; errors/accent cause strain at times. | Band 3 is described as genuinely "difficult to understand" — 4 is not. |
| 3 | Some acceptable features of spoken English; errors/accent cause *serious* strain; difficult to understand. | Band 2 is "often unintelligible" — a step beyond "difficult." |
| 2 | Often unintelligible; frequent errors cause severe strain. | Band 1 is "almost entirely" unintelligible — 2 still produces some intelligible stretches. |
| 1 | Almost entirely unintelligible. | Band 0 is total absence of a response. |
| 0 | No response provided. | — |

### Fluency

| Band | Meaning | What separates it from the band below |
|---|---|---|
| 6 | Completely fluent at normal speed; any hesitation is natural, not word-searching. | 5 still has occasional repetition/self-correction — 6 has essentially none. |
| 5 | Fluent at normal speed; occasional repetition/self-correction; hesitation is generally appropriate. | 4 has an "uneven flow" — 5's flow is steady. |
| 4 | Uneven flow, some repetition especially in longer turns; some word-searching that doesn't cause serious strain; delivery may be staccato/too fast/slow. | 3 is "very uneven" with *frequent* pauses/repetition — a difference of degree and frequency. |
| 3 | Very uneven; frequent pauses/repetition indicating word-searching; excessive fillers; difficulty sustaining longer utterances; serious listener strain. | 2 is "extremely uneven" with long pauses that make speech hard to *follow*, not just strained. |
| 2 | Extremely uneven; long pauses, numerous repetition/self-correction make speech difficult to follow. | 1 is "impossible to follow." |
| 1 | Impossible to follow — isolated words/phrases and self-corrections separated by long pauses. | 0 is no response. |
| 0 | No response provided. | — |

### Appropriateness of Language

| Band | Meaning | What separates it from the band below |
|---|---|---|
| 6 | Entirely appropriate register/tone/lexis; no difficulty explaining technical matters in lay terms. | 5 still has occasional non-intrusive lapses — 6 has none. |
| 5 | Mostly appropriate; occasional lapses that are not intrusive. | 4's lapses are "noticeable" and reflect resource limits, not just occasional slips. |
| 4 | Generally appropriate but somewhat restricted/lacking complexity; noticeable lapses reflecting limited resources. | 3's lapses are "frequent and intrusive" — a jump in both rate and impact. |
| 3 | Some evidence of appropriate register, but frequent, intrusive lapses reflecting inadequate resources. | 2 is "mostly inappropriate" — the balance flips from mostly-right to mostly-wrong. |
| 2 | Mostly inappropriate register/tone/lexis for the context. | 1 is "entirely inappropriate." |
| 1 | Entirely inappropriate register/tone/lexis. | 0 is no response. |
| 0 | No response provided. | — |

### Resources of Grammar and Expression

| Band | Meaning | What separates it from the band below |
|---|---|---|
| 6 | Rich and flexible; wide accurate/flexible range; confident idiomatic use. | 5's errors, while rare, are still present — 6 is essentially error-free and idiomatic. |
| 5 | Wide range, generally accurate and flexible; occasional non-intrusive errors. | 4's inaccuracies are "sometimes intrusive," especially in complex sentences — a real, if partial, comprehension cost. |
| 4 | Sufficient resources to maintain the interaction; inaccuracies (especially in complex sentences) sometimes intrusive; meaning generally clear. | 3 is "limited... except very simple sentences" with "persistent" intrusive inaccuracies — a step down in both range and reliability. |
| 3 | Limited vocabulary/grammatical control except in very simple sentences; persistent intrusive inaccuracies. | 2 is "very limited... even in simple sentences" — 3 can at least handle simple sentences reliably. |
| 2 | Very limited resources even in simple sentences; numerous word-choice errors. | 1 is "limited in all respects" — a further, undifferentiated collapse. |
| 1 | Limited in all respects. | 0 is no response. |
| 0 | No response provided. | — |

---

## 5. Clinical Level Mapping (0–3)

The PDF gives one scale, applied per criterion (A–E), not per indicator:

| Score | Label | Meaning |
|---|---|---|
| 3 | Adept use | The candidate demonstrates the behaviours under this criterion's indicators skilfully and consistently. |
| 2 | Competent use | The behaviours are demonstrated adequately, without notable skill or notable failure. |
| 1 | Partially effective use | The behaviours are attempted but inconsistently or incompletely realised. |
| 0 | Ineffective use | The behaviours under this criterion are essentially absent or actively undermined. |

**Explicitly unavailable in the source PDF (do not fabricate):** the PDF does not provide worded level descriptors for what distinguishes "Adept" from "Competent" from "Partially effective" from "Ineffective" *per indicator or per criterion* the way it does for the four linguistic criteria's 0–6 bands. It gives the indicator list (what to look for) and the 4-point scale (how good is what you saw) as two separate blocks, with no descriptor text bridging them. §16 addresses this gap directly rather than inventing bridging text.

---

## 6. Criterion → Evidence Matrix (Linguistic)

For every linguistic criterion: official requirement → observable behaviour → possible evidence channel → current SpeakOET evidence.

| Criterion | Observable candidate behaviour | Possible audio/language evidence | Current SpeakOET evidence | Evidence quality |
|---|---|---|---|---|
| **Intelligibility** | Pronunciation, stress, intonation, rhythm are clear enough not to strain the listener. | Phoneme-level accuracy, word-level pronunciation scores, prosody. | Elite tier only: Azure `assess_pronunciation_azure()` (`pronunciation.py`) returns `overall_score` (accuracy) and per-word `accuracy_score` + `error_type`, computed once over the full session recording, **after** scoring, and **not passed into** `score_speaking()`. Free/Basic/Pro (non-Elite): no audio at all — the LLM examiner in `ai_scoring.py` scores "intelligibility" purely by reading the STT transcript (word choice, spelling), which cannot carry pronunciation/stress/intonation information. | **PARTIAL** (Elite: real signal exists but is disconnected from the score) / **INSUFFICIENT** (everyone else: no audio-based evidence at all) |
| **Fluency** | Speech flow, pause pattern, repetition, self-correction, hesitation, filler use, ability to sustain longer turns. | Pause/gap timing, filler-word count, self-correction detection, Azure fluency/completeness scores. | Elite tier: Azure returns `fluency_score` and `completeness_score` (`pronunciation.py`) — same disconnection-from-scoring issue as Intelligibility. Realtime pipeline has `duration_seconds`, `time_to_ready_ms`, `interrupted_count` per session (`speaking_realtime.py`) — session-level timing exists but nothing per-utterance (no pause-length or filler data). Deepgram's `smart_format=true` on the legacy STT path actively strips filler words/disfluencies before the transcript is scored, destroying the one text-adjacent proxy this criterion could have had. | **PARTIAL** (Elite) / **INSUFFICIENT** (everyone else — the transcript itself has been smoothed against the exact signal this criterion needs) |
| **Appropriateness of Language** | Register/tone/lexis match the clinical, patient-facing context; technical content explained in lay terms. | Register classification, jargon presence, evidence the speaker adapted wording after a clarification request. | `detect_jargon()` (`patient_state.py`, re-exported by `ai_scoring.py`) deterministically flags unexplained medical terms per nurse turn; `speaking_evidence.py` aggregates this into `jargon_evidence` (term, turn index, patient reaction, whether later clarified). The LLM examiner separately judges register/tone from the transcript. Jargon evidence is **not currently passed into** the scoring prompt (confirmed absent from `score_speaking()`'s inputs). | **STRONG** (text-assessable; deterministic jargon signal exists and is real, if unwired) |
| **Resources of Grammar and Expression** | Grammatical range/accuracy, vocabulary range/accuracy, flexibility, complexity, idiomatic control. | Grammar-error detection, lexical diversity metrics, structural complexity measures. | No dedicated grammar-evidence pass exists for Speaking. The LLM examiner judges "grammar" purely from reading the transcript as part of the same single scoring call that produces all 9 criteria. There is no equivalent, for Speaking, of a separate grammar-checker service. | **STRONG** (text-assessable in principle) / **LIMITED** (no structural evidence pass backs the LLM's judgment — pure single-pass inference, same caveat as every other LLM-only criterion) |

---

## 7. Indicator → Evidence Matrix (Clinical, A1–E5)

Every indicator, mapped: official meaning → observable behaviour → current SpeakOET evidence → status.

### A. Relationship Building

| Indicator | Official meaning | Observable behaviour | Current SpeakOET evidence | Status |
|---|---|---|---|---|
| A1 | Initiating the interaction appropriately (greeting, introductions, nature of interview). | Opening turn contains a greeting, self-introduction, and/or statement of interview purpose. | **None.** No detector, phrase list, or state field looks at the *first* nurse turn specifically for this. `detect_nurse_events()` runs the same generic phrase checks on every turn with no "is this the opening turn" awareness. | **missing** |
| A2 | Demonstrating an attentive and respectful attitude. | Absence of dismissive/interrupting behaviour; turn-taking that lets the patient finish. | Indirect, negative-only signal: `_DISMISSIVE_PHRASES` (`patient_state.py`) flags dismissive language ("don't worry," "calm down") and lowers the `trust` score. There is no positive detector for "attentive" behaviour itself (e.g., asking a follow-up that shows the nurse listened). | **missing** (only the negative case is covered) |
| A3 | Adopting a non-judgmental approach. | Absence of judgmental language or tone when the patient discloses something sensitive (e.g., non-adherence, lifestyle factors). | **None.** No phrase list or classifier targets judgmental vs. neutral framing. | **missing** |
| A4 | Showing empathy for feelings/predicament/emotional state. | Acknowledging phrases immediately following a patient's emotional disclosure or a fired `emotional_trigger`. | `_EMPATHY_PHRASES` (`patient_state.py`) deterministically detects empathy phrasing ("I understand you," "that must be," "I hear you") per nurse turn; feeds `detect_nurse_events()` → contributes +1 to the `trust` score in `_derive_behavioural_state()`; surfaced in `speaking_evidence.py` as `candidate_events` (`event="empathy_acknowledgement"`) and can advance a concern's `concern_status` to "acknowledged." No semantic (LLM-verified) empathy detector exists — only the fixed phrase list. | **partial** (real deterministic L2 evidence exists; semantic paraphrase coverage is a documented gap) |

### B. Understanding & Incorporating the Patient's Perspective

| Indicator | Official meaning | Observable behaviour | Current SpeakOET evidence | Status |
|---|---|---|---|---|
| B1 | Eliciting and exploring the patient's ideas/concerns/expectations. | Open questions inviting the patient to state or elaborate a concern. | `_CONCERN_EXPLORATION_PHRASES` (deterministic, `patient_state.py`) plus `semantic_evidence.classify_nurse_concern_event()` (LLM, called only when the deterministic list finds nothing and a concern is still outstanding) — both feed `concern_status` transitions to "explored" and are captured in `speaking_evidence.py`'s `candidate_events`. | **strong** (deterministic + semantic layers both real) |
| B2 | Picking up the patient's cues. | A nurse turn that responds specifically to something the patient just revealed (an emotional trigger firing, or a concern being raised) rather than ignoring it. | Partial: `PatientState.fired_emotional_triggers` and `concerns_raised` record *that* the patient gave a cue, and `concern_status` advancing on the *next* nurse turn is evidence the cue was picked up. But there is no explicit "cue → response latency/relevance" detector — advancing status is inferred from the FIFO-target heuristic in `_derive_behavioural_state()`, not a direct "did the nurse address *this specific* cue" check. | **partial** |
| B3 | Relating explanations to elicited ideas/concerns/expectations. | An information-giving turn that explicitly references a concern raised earlier, not just information in the abstract. | `concern_addressing` (semantic-only event, `semantic_evidence.classify_nurse_concern_event()`) advances `concern_status` to "addressed," with `target_concern` naming which concern; `speaking_evidence.py` records this with turn index and evidence text. No deterministic (phrase-list) equivalent exists — this indicator currently depends entirely on the semantic layer being called (it is only invoked when the deterministic pass found nothing). | **partial** (real but semantic-only, and semantic calls are selectively triggered, not exhaustive) |

### C. Providing Structure

| Indicator | Official meaning | Observable behaviour | Current SpeakOET evidence | Status |
|---|---|---|---|---|
| C1 | Sequencing the interview purposefully and logically. | Turns follow a recognisable order (e.g., introduce → enquire → explain → advise) rather than jumping around. | The LLM examiner is instructed to judge this from the transcript (`ai_scoring.py`: "Did conversation follow OET sequence... in logical order?"), with one deterministic anchor: a fixed 0.5-point penalty if no roleplay card was provided. There is no structural/stage-tagging evidence — no code labels a turn as "introduce" vs. "enquire" vs. "explain" vs. "advise." | **limited** (LLM judgment only, one deterministic penalty point, no stage detection) |
| C2 | Signposting changes in topic. | Explicit verbal markers when moving between topics ("Now I'd like to ask about...", "Moving on to..."). | **None.** No detector exists. Confirmed absent by direct inspection — no signposting phrase list, no topic-segmentation logic anywhere in `patient_state.py`, `speaking_evidence.py`, or `ai_scoring.py`. | **missing** |
| C3 | Using organising techniques in explanations. | Numbered/sequenced explanations ("First... then... finally..."), previews ("I'm going to explain three things"), or explicit summaries closing an explanation. | **None.** No detector exists. | **missing** |

### D. Information Gathering

| Indicator | Official meaning | Observable behaviour | Current SpeakOET evidence | Status |
|---|---|---|---|---|
| D1 | Facilitating the patient's narrative with active listening, minimising interruption. | Patient turns are allowed to run their length; the nurse does not talk over the patient. | Weak proxy only: the realtime pipeline's `interrupted_count` (`speaking_realtime.py`) records when the AI patient's speech was cut off by barge-in, but this metric was built for VAD/latency purposes, is not attributed to "was this a legitimate active-listening interruption or a rude one," and does not exist at all on the legacy (non-realtime) pipeline, which is turn-locked by construction (mic closes while the AI speaks, so interruption in the D1 sense cannot even physically occur there). | **missing** (realtime has an adjacent raw signal never interpreted this way; legacy has none by design) |
| D2 | Using initially open questions, appropriately moving to closed questions. | Question-type classification (open vs. closed) across the conversation, checked for an open→closed pattern. | **None.** No question-type classifier exists anywhere in the codebase (confirmed — this exact gap is independently flagged in the 2026-08-26 audit, §5, as a proposed-but-unbuilt heuristic). | **missing** |
| D3 | NOT using compound questions/leading questions. | Detecting a single utterance that asks two things at once, or that presupposes an answer. | **None.** No detector exists. | **missing** |
| D4 | Clarifying statements which are vague or need amplification. | A nurse follow-up that asks the patient to expand on an ambiguous prior statement. | **None** directly. `_UNDERSTANDING_CHECK_PHRASES` exists but checks whether the *patient* understood the *nurse's* explanation — the opposite direction from D4 (nurse seeking clarification of something the *patient* said). No phrase list or classifier targets D4's direction. | **missing** |
| D5 | Summarising information to encourage correction/invite further information. | A nurse turn that recaps what's been gathered so far and invites correction ("So to summarise, you've had this pain for three days — is that right?"). | **None.** No summary-detection exists anywhere in the codebase. | **missing** |

### E. Information Giving

| Indicator | Official meaning | Observable behaviour | Current SpeakOET evidence | Status |
|---|---|---|---|---|
| E1 | Establishing initially what the patient already knows. | An opening question before explaining ("What have you already been told about...?"). | **None.** No detector exists. | **missing** |
| E2 | Pausing periodically when giving information, using the response to guide next steps. | Natural pauses during explanation turns, followed by adapting content based on the patient's reply. | **None** as a labelled behavioural event. Turn-level timing exists at the session level in the realtime pipeline (`duration_seconds`, per-turn timestamps implicit in `session_transcripts` ordering) but nothing extracts "did the nurse pause and check in" as an event. | **missing** |
| E3 | Encouraging the patient to contribute reactions/feelings. | Explicit invitations for the patient to react ("How does that sound to you?", "What do you think about that?"). | Partial overlap only: `_CONCERN_EXPLORATION_PHRASES` ("what concerns you," "tell me more about") is built for B1, not E3, but a subset of real utterances could trigger both; there is no E3-specific phrase list or classifier. | **missing** (no dedicated detector; only accidental overlap with a differently-targeted list) |
| E4 | Checking whether the patient has understood information. | Explicit understanding-check questions ("Does that make sense?", "Do you have any questions?"). | `_UNDERSTANDING_CHECK_PHRASES` (deterministic, `patient_state.py`) directly detects this; feeds `detect_nurse_events()` → can advance `concern_status` from "explored" to "addressed"; captured in `speaking_evidence.py`'s `candidate_events` (`event="understanding_checked"`). | **strong** (deterministic evidence exists and is wired into the state machine) |
| E5 | Discovering what further information the patient needs. | A closing-style question inviting the patient to raise anything not yet covered ("Is there anything else you'd like to ask?"). | **None.** No detector exists. | **missing** |

---

## 8. Evidence Hierarchy (L1–L4)

Reusing the project's established levels, applied per criterion/indicator:

- **L1 — Direct transcript/audio evidence:** the raw text or audio signal itself (a transcript line, an Azure phoneme score).
- **L2 — Deterministic evidence:** rule-based extraction over L1 (phrase-list matches in `patient_state.py`, `detect_jargon()`, timing counters).
- **L3 — Semantic evidence:** LLM-verified interpretation of L1, used conservatively and only where L2 is known to be insufficient (`semantic_evidence.py`'s `verify_hidden_reveal`, `classify_nurse_concern_event`, `classify_patient_resolution`).
- **L4 — Patient outcome:** state that resulted from the interaction (`PatientState.trust`, `concern_status`, `current_emotion` in `patient_state.py`), which is *evidence of effect*, not of the candidate's behaviour directly.

| Criterion / Indicator | Appropriate levels today | Notes |
|---|---|---|
| Intelligibility | L1 (Elite only, unwired) | Non-Elite: no legitimate L1 exists; the current LLM judgment is not really any of L1–L4, it is an L1-shaped claim resting on L1-absent data (see §10). |
| Fluency | L1 (Elite only, unwired), thin L2 (session timing) | Same caveat as Intelligibility for non-Elite. |
| Appropriateness of Language | L1 (transcript), L2 (jargon) | Text-legitimate. |
| Resources of Grammar and Expression | L1 (transcript) | Text-legitimate; no L2 exists. |
| A1–A3 | none currently produced | — |
| A4 | L2 | Deterministic phrase match. |
| B1 | L2 + L3 | Both layers real and combined. |
| B2 | L4 (partial) | Inferred from state advancing, not a direct behavioural detector. |
| B3 | L3 | Semantic-only. |
| C1 | L1 (LLM judgment) + one L2 penalty point | — |
| C2, C3 | none currently produced | — |
| D1 | L2 (raw, uninterpreted) | `interrupted_count` exists but is not evidence *for* D1 as currently computed. |
| D2–D5 | none currently produced | — |
| E1, E2, E3, E5 | none currently produced | — |
| E4 | L2 | Deterministic phrase match. |

---

## 9. Evidence-Quality Model

Per the task's mandatory distinction: this rates **evidence availability**, never candidate performance.

| Rating | Meaning |
|---|---|
| **STRONG** | Direct, reliable evidence exists and is (or could trivially be) wired to the criterion. |
| **PARTIAL** | Real evidence exists but is incomplete, tier-gated, disconnected from scoring, or covers only part of the indicator's scope. |
| **LIMITED** | Only indirect or single-source (typically LLM-only, unverified) evidence exists. |
| **INSUFFICIENT** | No evidence channel exists that can legitimately support this criterion as currently scored. |

Applied to the 9 criteria and 19 indicators:

| Item | Evidence quality |
|---|---|
| Intelligibility | INSUFFICIENT (non-Elite) / PARTIAL (Elite, unwired) |
| Fluency | INSUFFICIENT (non-Elite) / PARTIAL (Elite, unwired) |
| Appropriateness of Language | STRONG |
| Resources of Grammar and Expression | LIMITED |
| A1, A2, A3 | INSUFFICIENT |
| A4 | PARTIAL |
| B1 | STRONG |
| B2 | PARTIAL |
| B3 | PARTIAL |
| C1 | LIMITED |
| C2, C3 | INSUFFICIENT |
| D1 | INSUFFICIENT (raw signal exists, uninterpreted) |
| D2, D3, D4, D5 | INSUFFICIENT |
| E1, E2, E3, E5 | INSUFFICIENT |
| E4 | STRONG |

---

## 10. Missing vs. Negative Evidence

Per Step 19, these are never the same thing, and this document keeps them apart everywhere above:

| Missing evidence (the system cannot see) | Negative/performance evidence (the system saw something and it was bad) |
|---|---|
| No audio channel exists for a non-Elite Intelligibility/Fluency score. | An Elite candidate's Azure `accuracy_score` came back low. |
| No detector exists for C2 (signposting). | A candidate signposted poorly (not detectable either way today). |
| No detector exists for D5 (summarising). | A candidate summarised inaccurately. |
| A1 has no opening-turn detector. | A candidate's greeting was rude (currently indistinguishable from "no greeting at all," since neither is detected). |

Every "missing" row in §6, §7, §9 is a `status = missing` / `INSUFFICIENT` statement about the *system*, not a `status = poor` statement about any candidate. Where the LLM examiner currently produces a score anyway (e.g., Intelligibility for non-Elite users), that is flagged explicitly as a **channel mismatch** — the score exists, but it should not be read as evidence-grounded performance data, only as an unverifiable LLM guess dressed in the criterion's name.

---

## 11. Audio Requirements

| Criterion | Transcript sufficient? | Audio required for a defensible score? |
|---|---|---|
| Intelligibility | **NO** | **YES.** Pronunciation, stress, intonation, rhythm are acoustic properties; a transcript (even a perfect one) cannot carry them. |
| Fluency | **PARTIAL** | **YES** for pause/hesitation/rhythm; a transcript can carry *some* signal (filler words, repetition, self-correction) only if the STT does not smooth them away — which the current legacy path's `smart_format=true` does. |
| Appropriateness of Language | **YES** | No — register, tone, and lexis are legitimately assessable from text. |
| Resources of Grammar and Expression | **YES** | No — grammatical range/accuracy/vocabulary are legitimately assessable from text. |
| All 5 clinical criteria (A–E) | **YES**, with one caveat | No — clinical communication behaviours (what was said, in what order, whether a concern was addressed) are fundamentally content-based, not acoustic. The one caveat: A2 ("attentive... attitude") and D1 (interruption/active listening) have a *paralinguistic* component (tone of voice, actually waiting vs. talking over) that a transcript alone cannot fully capture, though the *content* half of both indicators is transcript-assessable. |

This is stated explicitly per Step 12's instruction: do not infer intelligibility from transcript grammar, and do not treat Fluency as transcript-only just because some proxies happen to survive into text.

---

## 12. Current SpeakOET Capabilities (Summary)

Everything below was confirmed by reading the actual source files, not assumed:

- **`patient_state.py`** — deterministic behavioural-event detection (`detect_nurse_events`: empathy, concern-exploration, understanding-check, dismissive, jargon) and a pure state machine (`derive_patient_state`) producing `trust`, `current_emotion`, `concern_status` per concern, `fired_emotional_triggers`, `revealed_information`/`hidden_information`.
- **`semantic_evidence.py`** — three narrowly-scoped, conservative LLM classifiers: `verify_hidden_reveal` (Finding 1 fix), `classify_nurse_concern_event` (concern exploration/addressing), `classify_patient_resolution` (patient-side resolution signal). Every classifier fails safe (a None/failure result is always treated as the conservative default, never silently promoted).
- **`session_semantic_state.py`** — persists `SemanticHints` per session so semantic verification survives realtime reconnects and is inspectable later without re-running LLM calls.
- **`speaking_evidence.py`** — reconstructs a full per-turn evidence timeline (`candidate_events`, `patient_events`, `concern_outcomes`, `state_transitions`, `jargon_evidence`, `interaction_metrics`, `hidden_info_outcomes`) by re-deriving `PatientState` at every conversation prefix and diffing. Both a deterministic-only builder and a semantics-enriched builder exist.
- **`evidence_reconciliation.py`** — merges deterministic and semantic evidence into one provenance-tagged (`deterministic_rule` / `semantic_model` / `hybrid`) view, plus an integrity checker that flags internally impossible combinations. Read-only, no new LLM calls.
- **`admin_speaking_evidence.py`** — read-only admin inspector surfacing the above for real sessions (both pipelines), for manual QA before anything is wired into scoring.
- **`ai_scoring.py`** — the actual 9-criterion OET scorer: one LLM call, transcript-only input, deterministic post-processing (score clamping, weighted `overall_band = clinical×0.6 + linguistic×0.4` computed in Python). **None of the evidence layers above currently feed into this scoring call.**
- **`pronunciation.py`** — Azure phoneme-level assessment (Elite tier only): `overall_score`, `fluency_score`, `completeness_score`, per-word `accuracy_score`/`error_type`. Computed once, post-session, over the full recording; not currently connected to `score_speaking()`.
- **`speaking_realtime.py`** — session-level metrics (`duration_seconds`, `time_to_ready_ms`, `interrupted_count`) persisted per realtime session; no per-utterance timing exists.

**Net position:** SpeakOET has built a genuinely sophisticated, provenance-aware evidence layer for the *clinical* side (especially A4, B1, B3, E4, plus the hidden-information/concern state machine), but almost none of D (Information Gathering) or C (Providing Structure), and only A4 of Relationship Building. The *linguistic* side has one tier (Elite) with real audio evidence that is architecturally present but not wired to scoring, and three tiers with no audio evidence at all.

---

## 13. Evidence Gaps (Complete Table)

| Criterion/Indicator | Evidence needed | Available now | Missing | Audio required | Future detector |
|---|---|---|---|---|---|
| Intelligibility | Pronunciation/stress/intonation/rhythm signal | Azure scores (Elite only, unwired) | Non-Elite: everything. Elite: wiring into scoring. | Yes | Consultation-wide pronunciation/audio assessment feeding the score directly |
| Fluency | Pause/hesitation/filler/rhythm signal | Azure scores (Elite only, unwired); session-level timing | Per-utterance pause data; unsmoothed transcript; wiring into scoring | Yes (mostly) | Audio timing analysis + verbatim (non-smart-format) transcript capture |
| Appropriateness of Language | Register/tone/lexis + jargon | LLM judgment + `detect_jargon` (unwired to scoring) | Wiring jargon log into the scoring prompt | No | Feed existing jargon log into scoring input |
| Resources of Grammar and Expression | Grammatical/lexical range & accuracy | LLM judgment only | A structured grammar-evidence pass | No | Dedicated grammar-evidence extractor (see §14) |
| A1 | Opening-turn greeting/introduction/purpose statement | None | Everything | No | Opening-turn detector |
| A2 | Attentive/respectful attitude | Negative-only (`_DISMISSIVE_PHRASES`) | A positive attentiveness signal | Partial (tone) | Attentiveness heuristic (follow-up-question rate, non-interruption) |
| A3 | Non-judgmental approach | None | Everything | No | Judgmental-language classifier |
| A4 | Empathy | `_EMPATHY_PHRASES` (L2) | Semantic (paraphrase) coverage | No | Empathy semantic classifier |
| B1 | Eliciting/exploring concerns | Deterministic + semantic | — (well covered) | No | — |
| B2 | Picking up cues | Inferred from state advance (L4) | Direct cue→response detector | No | Cue-response latency/relevance detector |
| B3 | Relating explanations to concerns | Semantic-only | Deterministic backstop | No | Phrase-list backstop for common "as you mentioned..." framings |
| C1 | Logical sequencing | LLM judgment + 1 deterministic penalty | Stage-tagging | No | Interview-stage classifier (introduce/enquire/explain/advise) |
| C2 | Signposting | None | Everything | No | Signposting-phrase detector |
| C3 | Organising techniques in explanations | None | Everything | No | Explanation-structure detector (numbered lists, previews, summaries) |
| D1 | Active listening, minimal interruption | Raw `interrupted_count` (uninterpreted) | Attribution + legacy-pipeline coverage | Partial | Interruption-attribution classifier (realtime only) |
| D2 | Open-then-closed questions | None | Everything | No | Question-type classifier |
| D3 | No compound/leading questions | None | Everything | No | Compound/leading-question detector |
| D4 | Clarifying vague statements | None | Everything | No | Clarification-request detector (opposite direction of the existing understanding-check list) |
| D5 | Summarising to invite correction | None | Everything | No | Summary detector |
| E1 | Establishing prior knowledge | None | Everything | No | Opening-of-explanation detector |
| E2 | Pausing, using response to guide next steps | None | Everything | No | Pause + response-adaptation detector |
| E3 | Encouraging patient reactions/feelings | Accidental overlap with B1's list only | A dedicated detector | No | Reaction-invitation phrase/semantic detector |
| E4 | Checking understanding | `_UNDERSTANDING_CHECK_PHRASES` (L2) | Semantic coverage | No | Understanding-check semantic classifier (mirrors B1's pattern) |
| E5 | Discovering further info needs | None | Everything | No | Closing-invitation detector |

---

## 14. Future Detectors

Smallest plausible detector per gap — proposed, not implemented, no model calls made:

- **A1 (opening-turn detector):** deterministic phrase check restricted to the *first* nurse turn only (greeting words, self-introduction pattern, "I'd like to ask you some questions").
- **A2/A3 (attentiveness / non-judgmental):** a semantic classifier in the same conservative style as `classify_nurse_concern_event` — narrowly scoped, invoked selectively, fails safe.
- **A4 semantic backstop:** extend `_EMPATHY_PHRASES`' deterministic pass with an occasional semantic check (same selective-invocation pattern already used for B-family indicators), rather than a new subsystem.
- **B2 (cue-response):** a direct pairing of "trigger/concern fired at turn N" with "nurse turn N+1 addresses it," rather than inferring it from state advancing generically.
- **C1 (stage classifier):** a lightweight per-turn label (introduce/enquire/explain/advise/close) — deterministic keyword pass first, semantic fallback only where ambiguous.
- **C2 (signposting detector):** deterministic phrase list ("moving on to," "now I'd like to ask about," "next I want to explain").
- **C3 (explanation-structure detector):** deterministic pattern match for enumeration/preview/summary markers ("first... second...," "there are three things," "to sum up").
- **D1 (interruption attribution):** reclassify the existing `interrupted_count` signal by who spoke over whom and whether the patient's utterance had already reached a natural pause point — realtime-only, since legacy structurally cannot produce this signal.
- **D2 (question-type classifier):** deterministic heuristic (5W1H opener + no yes/no auxiliary at the start ⇒ open; yes/no auxiliary at the start ⇒ closed), same shape as the audit's own proposal.
- **D3 (compound/leading-question detector):** deterministic pattern match ("and... or...?" within one utterance; a question containing an embedded assumed answer).
- **D4 (clarification-of-patient detector):** mirror of the existing understanding-check list, pointed at the opposite direction ("what do you mean by," "can you tell me more specifically").
- **D5 (summary detector):** deterministic pattern match ("so to summarise," "just to check I've got this right," "let me make sure I understand").
- **E1 (prior-knowledge check):** deterministic phrase list ("what have you been told," "do you know anything about").
- **E2 (pause + adapt):** requires per-utterance timing data that does not currently exist even at the session level for the legacy pipeline; a real detector here is gated on that data existing first — flagged as a data-availability dependency, not just a missing classifier.
- **E3 (reaction-invitation detector):** deterministic phrase list distinct from B1's ("how does that sound," "what are your thoughts on that").
- **E4 semantic backstop:** same treatment as A4 — extend the existing deterministic list with a selective semantic fallback.
- **E5 (closing-invitation detector):** deterministic phrase list ("is there anything else," "any other questions before we finish").
- **Intelligibility/Fluency:** consultation-wide audio assessment — wire the already-computed Azure scores (Elite) into the scoring input as real evidence; for non-Elite, either extend audio capture (cost/infra decision, not a code detail this document should resolve) or relabel what is being measured, per the audit's own recommendation.
- **Resources of Grammar and Expression:** a dedicated grammar-evidence pass (structural, not the whole-criterion LLM call) — out of scope to design further here per Step 15 ("determine whether existing output is suitable... or a dedicated evidence pass is needed"); this document's answer is: a dedicated pass is needed, no equivalent currently exists for Speaking.

None of the above have been implemented, scaffolded, or stubbed. This is a list of what to build later, not code.

---

## 15. Proposed ExaminerInput

The smallest structure that carries every criterion's evidence without unnecessary raw data:

```text
ExaminerInput
├── scenario_context
│   ├── role_card_tasks: List[str]
│   ├── scenario_title: str
│   └── had_roleplay_card: bool          # for the existing 0.5-point structure penalty
├── transcript
│   └── turns: List[{role, content, turn_index}]
├── linguistic_evidence
│   ├── audio_available: bool
│   ├── pronunciation: Optional[{overall_score, fluency_score, completeness_score, problem_words}]  # Elite only, today
│   └── jargon_log: List[JargonEvidence]  # from speaking_evidence.py, already computed
├── clinical_evidence  (UnifiedEvidence, already built by evidence_reconciliation.py)
│   ├── candidate_events: List[UnifiedCandidateEvent]
│   ├── patient_events: List[UnifiedPatientEvent]
│   ├── concern_outcomes: List[UnifiedConcernOutcome]
│   ├── hidden_info_outcomes: List[UnifiedHiddenInfoOutcome]
│   ├── state_transitions: List[UnifiedStateTransition]
│   └── interaction_metrics: InteractionMetrics
└── evidence_gaps  # explicit, not silent — which of the 9 criteria/19 indicators had no supporting evidence this session, so the examiner (human or AI) knows what it's judging blind on
```

`UnifiedEvidence` already exists as a fully-built Pydantic model (`evidence_reconciliation.py`) — this is not a new type, it is the object this input structure already has on hand. `evidence_gaps` is the one net-new field this document proposes, because Step 18/19's mandatory missing-vs-negative distinction has to reach the examiner itself, not just this specification.

---

## 16. Future Examiner Output Contract Preview

```text
CriterionResult
├── criterion: str                 # one of the 9 official names
├── score: float                   # 0-6 (linguistic) or 0-3 (clinical)
├── justification: str             # cites specific evidence, not free invention
├── supporting_evidence: List[EvidenceRef]   # pointers into ExaminerInput, not copies
├── provenance: str                # "deterministic_rule" | "semantic_model" | "llm_judgment" | "hybrid"
└── evidence_quality: str          # STRONG | PARTIAL | LIMITED | INSUFFICIENT (per §9's model)
```

For the 5 clinical criteria, `supporting_evidence` retains indicator-level references (which of A1–E5 contributed) even though `score` is criterion-level — per Step 26's explicit instruction not to lose that resolution just because the final number is coarser.

---

## 17. Human Calibration Requirements

Requiring human judgment before any of this becomes an automated score:

- **Linguistic band boundaries** (§4): "occasional" vs. "some" vs. "frequent," "minimal strain" vs. "at times causes strain," are inherently graded human judgments the PDF describes in words, not thresholds. A human rater (or a panel) needs to calibrate what count/frequency of, e.g., jargon incidents or filler words maps to each band, for this system's specific evidence signals — the PDF gives no numeric anchors.
- **Clinical criterion judgement** (§5): explicitly flagged as unresolvable from the PDF alone (§5's "explicitly unavailable" note) — there is no descriptor text distinguishing Adept/Competent/Partially effective/Ineffective per indicator. This is the single largest human-calibration requirement in the whole framework and cannot be inferred from the source document.
- **Evidence interpretation:** whenever two evidence sources conflict (e.g., a deterministic empathy-phrase match on a turn a human reviewer feels was actually sarcastic), a human must decide which one wins, and whether the detector itself needs revision.
- **Case where evidence conflicts:** `evidence_reconciliation.py`'s `check_integrity()` already flags internally *impossible* combinations (e.g., "verified revealed but final status hidden") — but a *legitimate* disagreement (deterministic says "explored," semantic says "addressed") is not a violation, and resolving which one the human examiner should trust more needs calibration, not code.
- **OET's own internal examiner tolerance thresholds** (Step 27's explicit instruction): not fabricated here. This document does not claim to know how much inter-rater variance real OET examiners tolerate, and none of the future-detector designs above assume a specific number.

---

## 18. Golden Consultation Requirements

For calibrating and testing any of the above once built:

- A small set (the existing audit's own recommendation, §11 of the 2026-08-26 audit, suggested 10–20) of golden transcripts per scenario archetype (cooperative, anxious, confused, resistant patient moods), each with:
  - a human-assigned score per criterion (all 9),
  - a human-annotated list of which A1–E5 indicators were actually observed and where (turn index),
  - explicit notes on which criteria had **no legitimate evidence available** in that session (so the golden set itself models §10's missing-vs-negative distinction, not just scores).
- At least one golden transcript per linguistic band boundary (6/5, 5/4, 4/3, 3/2, 2/1, 1/0) — currently does not exist; the codebase's existing test files (`test_speaking_chat_ai_failure.py`, `test_speaking_insights.py`, etc.) test pipeline behaviour, not scoring calibration.
- Golden transcripts must include at least one Elite-tier session with real Azure pronunciation data, to calibrate the two criteria (Intelligibility, Fluency) that cannot be tested meaningfully on transcript-only data.

---

## 19. Recommended Implementation Phases

Adjusted from the task's suggested sequence to match what this specification actually found (the evidence layer for clinical criteria is already substantially built; the linguistic side and several clinical indicators are not):

1. **ExaminerInput assembler** — a pure function that packages `UnifiedEvidence` (already built) + transcript + scenario context + the Elite pronunciation payload (already computed, currently thrown away) into the `ExaminerInput` shape in §15. No new evidence, just assembly.
2. **Wire existing-but-disconnected evidence into scoring** — jargon log and Elite pronunciation scores are the cheapest wins: both already exist, are computed, and are currently discarded before reaching `score_speaking()`.
3. **Build the missing clinical detectors, cheapest first** — deterministic phrase-list detectors for A1, C2, D2, D3, D4, D5, E1, E3, E5 (all listed in §14 as phrase-list-shape, no LLM needed) before the semantic-only gaps (A2, A3, C1 stage-tagging, D1 attribution).
4. **Shadow examiner** — run the future examiner's evidence-gathering step against real sessions without it affecting any live score, verified against the admin evidence inspector that already exists (`admin_speaking_evidence.py`).
5. **Golden evaluation** — build the golden-consultation set (§18), scored by humans, before any automated score is trusted.
6. **Human calibration** — resolve §17's open questions (clinical band descriptors, evidence-conflict precedence) using the golden set.
7. **Examiner scoring validation** — compare the future examiner's output against the golden set's human scores; do not proceed until agreement is acceptable (an OET-specific tolerance threshold this document does not set, per §17).
8. **Controlled scoring integration** — replace or augment the current single-LLM-pass `score_speaking()` only after the above, and only incrementally (per the 2026-08-26 audit's own final recommendation: do not rebuild, extend what exists).

---

## 20. Critical Risks

- **Channel-mismatch risk (highest severity):** Intelligibility and Fluency are currently scored, presented, and stored as if they were audio-based judgments, for 3 of 4 pricing tiers where no audio evidence exists at all. Any automation built on top of the current scoring output would inherit and formalise this defensibility gap rather than fix it.
- **Silent scope creep risk:** it would be easy, in a future implementation step, to accidentally turn A1–E5 into 19 scored sub-criteria instead of evidence for 5 scores (the exact anti-pattern §3 of the task brief warns against). Every future detector must feed a criterion's evidence bundle, never a standalone score.
- **False-confidence risk from unwired evidence:** the clinical evidence layer (`speaking_evidence.py`, `evidence_reconciliation.py`) is genuinely sophisticated, which creates a risk of assuming it is already informing scores — it is not. `score_speaking()` today has zero dependency on any of it.
- **Legacy-pipeline structural gap:** D1 (minimising interruption) cannot be evidenced at all on the legacy voice pipeline because that pipeline's turn-taking is rigid by design (mic closes while the AI speaks) — no detector can fix a data-availability problem that is actually a transport-architecture property.
- **Human-calibration dependency risk:** §17 identifies that the clinical 0–3 scale has no source-provided descriptor text distinguishing its four levels per indicator. Any scoring automation for the 5 clinical criteria that skips human calibration is building on an assumption, not the PDF.
- **Cost risk of semantic evidence:** every semantic classifier in `semantic_evidence.py` is an LLM call; scaling the number of semantic-backed indicators (per §14's proposed backstops for A4, E4, etc.) multiplies per-session cost. The existing cost-tracking/circuit-breaker infrastructure (noted in the 2026-08-26 audit) would need to account for this before scaling semantic coverage.

---

## Final Confirmation

```text
All 9 official criteria included:              YES (§2)
All A1–E5 indicators included (19 total):       YES (§3, §7)
All linguistic 0–6 levels considered:           YES (§4)
Clinical 0–3 scoring considered:                YES (§5)
No criterion omitted:                            confirmed
No indicator omitted:                            confirmed
```

```text
No scoring code modified:        confirmed — read-only investigation of ai_scoring.py, pronunciation.py, patient_state.py, semantic_evidence.py, session_semantic_state.py, speaking_evidence.py, evidence_reconciliation.py, admin_speaking_evidence.py, speaking_realtime.py
No Learning Brain code modified: confirmed
No model calls made:             confirmed — no Gemini/Sonnet/Opus/OpenRouter/embedding calls were made while producing this document
No production changes:           confirmed
```
