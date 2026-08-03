"""Shared cached "why is this the answer" explanation generator -- Reading
and Listening both cache this on questions.explanation, keyed by question id,
generated once ever per question."""
import json

from app.services.ai_scoring import _call_ai, GEMINI_SCORING_FREE_MODEL


async def generate_mcq_explanation(question: dict, subject: str, context_noun: str) -> str:
    """question: a row with content, options (JSON string or list), correct_answer.
    subject: "Reading" or "Listening". context_noun: "passage" or "audio track"."""
    raw_options = question.get("options")
    options = json.loads(raw_options) if isinstance(raw_options, str) and raw_options else (raw_options or [])
    options_block = "\n".join(f"- {o}" for o in options) if options else "(no options — short-answer question)"

    prompt = f"""You are an OET {subject} tutor. A nursing student got this question wrong and wants to understand why.

Question: {question['content']}
Options:
{options_block}
Correct answer: {question['correct_answer']}

Explain in 2-3 short sentences why the correct answer is right, referencing the {context_noun}'s logic (you don't have the {context_noun} itself, just the question). If there are wrong options, briefly note what makes them tempting-but-wrong. Plain, encouraging tone.

Return ONLY this JSON, no other text:
{{"explanation": "your 2-3 sentence explanation"}}"""

    result = await _call_ai(
        [{"role": "user", "content": prompt}],
        max_tokens=300,
        json_mode=True,
        model=GEMINI_SCORING_FREE_MODEL,
    )
    if result.get("provider_failure"):
        return ""
    return (result.get("explanation") or "").strip()


async def generate_reading_explanation_with_evidence(question: dict, passage_body: str) -> dict:
    """Reading-only variant that also has the passage, so it can (a) ground the
    explanation in the actual text and (b) return the single verbatim sentence
    the answer comes from, for the "show me where" highlight. Returns
    {"explanation": str, "evidence": str} -- evidence "" if nothing clean matched.

    Kept separate from generate_mcq_explanation because that one is shared with
    Listening (audio, no passage text to quote)."""
    raw_options = question.get("options")
    options = json.loads(raw_options) if isinstance(raw_options, str) and raw_options else (raw_options or [])
    options_block = "\n".join(f"- {o}" for o in options) if options else "(no options — short-answer question)"

    prompt = f"""You are an OET Reading tutor. A nursing student got this question wrong. You have the source passage below.

Passage:
\"\"\"
{passage_body[:6000]}
\"\"\"

Question: {question['content']}
Options:
{options_block}
Correct answer: {question['correct_answer']}

Do two things:
1. Explain in 2-3 short sentences why the correct answer is right, referencing the passage. If there are wrong options, briefly note what makes them tempting-but-wrong. Plain, encouraging tone.
2. Quote the SINGLE most relevant sentence from the passage that the answer comes from, copied VERBATIM (exact characters) so it can be found and highlighted in the text. If no single sentence fits, use "".

Return ONLY this JSON, no other text:
{{"explanation": "your 2-3 sentence explanation", "evidence": "the exact supporting sentence, or empty string"}}"""

    result = await _call_ai(
        [{"role": "user", "content": prompt}],
        max_tokens=500,
        json_mode=True,
        model=GEMINI_SCORING_FREE_MODEL,
    )
    if result.get("provider_failure"):
        return {"explanation": "", "evidence": ""}
    return {
        "explanation": (result.get("explanation") or "").strip(),
        "evidence": (result.get("evidence") or "").strip(),
    }
