"""Per-module prompt templates for the AI Draft Generator (RC3.2).

One function per module builds (system_prompt, user_prompt) from the same
generation params. Shared OET framing lives in _SYSTEM_HEADER and
_shared_context so no module repeats it; only the output JSON schema and
module-specific guidance differ per function.
"""
from typing import Callable, Dict, Optional, Tuple

_SYSTEM_HEADER = (
    "You are an OET (Occupational English Test) content specialist writing "
    "material for nursing candidates. Generate clinically realistic, "
    "exam-accurate content. Return ONLY valid JSON matching the schema "
    "given -- no markdown, no commentary, no text outside the JSON."
)

# Reused by every module so the instruction lives once, not six times. When
# the requested topic/specialty is broad, models default to the same few
# safe tropes (post-op pain, discharge letters) -- naming the breadth of
# real clinical practice nudges toward a specific, varied pick instead.
_DIVERSITY_HINT = (
    "Pick a specific, varied clinical scenario within the given topic/specialty "
    "rather than defaulting to the most obvious or common one -- e.g. infection "
    "control, diabetes, COPD, stroke, heart failure, renal disease, palliative "
    "care, mental health, elderly care, wound management, medication safety, "
    "falls, sepsis, vaccination, child health, maternity, or emergency care are "
    "all equally valid starting points."
)


def _shared_context(difficulty: str, specialty: str, topic: str, objectives: Optional[str], instructions: Optional[str]) -> str:
    lines = [
        f"Difficulty: {difficulty}",
        f"Medical specialty: {specialty}",
        f"Topic: {topic}",
    ]
    if objectives:
        lines.append(f"Learning objectives: {objectives}")
    if instructions:
        lines.append(f"Additional instructions: {instructions}")
    return "\n".join(lines)


def build_speaking_prompt(difficulty: str, specialty: str, topic: str, objectives: Optional[str] = None, instructions: Optional[str] = None) -> Tuple[str, str]:
    schema = """{
  "title": "short descriptive title for this scenario",
  "setting": "the ward/clinic/location and context paragraph",
  "difficulty": "beginner|intermediate|advanced",
  "specialty": "the medical specialty",
  "nurse_card": {"role": "You are the nurse in charge of this patient", "tasks": ["task 1", "task 2", "task 3", "task 4", "task 5"]},
  "interlocutor_card": {"persona": "how the patient should behave", "emotional_triggers": ["trigger 1"], "questions_to_ask": ["question 1"], "information_to_withhold": ["info 1"]}
}"""
    user = (
        f"Create an original OET Speaking role-play card (nurse/patient interaction). Vary the specialty across "
        f"generations (medical, surgical, emergency, community, oncology, mental health, paediatrics, aged care, "
        f"rehabilitation, ICU, cardiology, respiratory, renal, maternity, etc.) rather than defaulting to "
        f"post-operative care. Give the patient a distinct personality and emotional state (e.g. anxious, "
        f"frustrated, embarrassed, confused, angry, withdrawn, overly confident, forgetful, emotional) -- vary it "
        f"each time rather than repeating the same pattern. The persona should include a realistic communication "
        f"barrier, genuine information the patient is holding back, and a clear consultation goal specific to this "
        f"scenario.\n{_shared_context(difficulty, specialty, topic, objectives, instructions)}\n\n{_DIVERSITY_HINT}"
        f"\n\nReturn ONLY this JSON:\n{schema}"
    )
    return _SYSTEM_HEADER, user


def build_reading_prompt(difficulty: str, specialty: str, topic: str, objectives: Optional[str] = None, instructions: Optional[str] = None) -> Tuple[str, str]:
    schema = """{
  "title": "short descriptive title for this passage",
  "part": "A, B, or C",
  "difficulty": "beginner|intermediate|advanced",
  "body": "the reading passage text",
  "questions": [
    {"content": "question text", "type": "mcq", "options": ["option 1", "option 2", "option 3", "option 4"], "correct_answer": "must match one option exactly"}
  ]
}"""
    user = (
        f"Create an original OET Reading passage with comprehension questions. Write it in an authentic healthcare "
        f"style -- e.g. a professional nursing journal article, hospital clinical guideline, evidence summary, "
        f"clinical practice article, or quality-improvement report -- not a generic textbook extract. Target "
        f"roughly 700-900 words. Mix the question types: include inference, the author's opinion, main idea, a "
        f"specific detail, and vocabulary-in-context -- avoid making every answer a direct copy of one sentence; "
        f"some should require connecting information across the passage.\n"
        f"{_shared_context(difficulty, specialty, topic, objectives, instructions)}\n\n{_DIVERSITY_HINT}"
        f"\n\nReturn ONLY this JSON:\n{schema}"
    )
    return _SYSTEM_HEADER, user


def build_listening_prompt(difficulty: str, specialty: str, topic: str, objectives: Optional[str] = None, instructions: Optional[str] = None) -> Tuple[str, str]:
    schema = """{
  "title": "short descriptive title for this section",
  "part": "A, B, or C",
  "difficulty": "beginner|intermediate|advanced",
  "transcript": [{"speaker": "Nurse", "text": "..."}, {"speaker": "Patient", "text": "..."}],
  "questions": [
    {"content": "question text", "type": "mcq", "options": ["option 1", "option 2", "option 3", "option 4"], "correct_answer": "must match one option exactly"}
  ]
}"""
    user = (
        f"Pick ONE of Part A, B, or C at random for this generation -- do not default to the same part every time; "
        f"each is equally likely. Part A: a nurse taking a patient's history in consultation (two-speaker "
        f"dialogue). Part B: a short workplace extract such as a handover, briefing, or team meeting. Part C: an "
        f"interview or presentation on a healthcare topic. Shape the transcript to match whichever part you pick. "
        f"Write natural spoken English -- include realistic hesitations, interruptions, and clarification "
        f"requests -- not scripted or robotic dialogue.\n"
        f"{_shared_context(difficulty, specialty, topic, objectives, instructions)}\n\n{_DIVERSITY_HINT}"
        f"\n\nReturn ONLY this JSON:\n{schema}"
    )
    return _SYSTEM_HEADER, user


def build_writing_prompt(difficulty: str, specialty: str, topic: str, objectives: Optional[str] = None, instructions: Optional[str] = None) -> Tuple[str, str]:
    schema = """{
  "title": "short scenario title, e.g. 'Discharge Letter - Pneumonia to Community Nurse'",
  "difficulty": "easy|medium|hard",
  "case_notes": "the full case notes, preserving section labels (Patient details, Past medical history, Social background, Medical progress, Nursing management, Discharge plan) with newlines between sections",
  "task": "the writing task instruction in full: the recipient and what letter to write, ending with word-count guidance (approximately 180-200 words)",
  "key_points": ["5 concise key points the letter must cover, used for scoring"]
}"""
    user = (
        f"Create an original OET Writing task. Randomly choose the letter type -- referral, discharge, transfer, "
        f"update, community nursing handover, specialist referral, rehabilitation, or outpatient follow-up -- "
        f"rather than defaulting to a referral/discharge letter every time. Write the case notes as real OET exams "
        f"do: abbreviated, clinically dense, with realistic timestamps and section labels, not full prose.\n"
        f"{_shared_context(difficulty, specialty, topic, objectives, instructions)}\n\n{_DIVERSITY_HINT}"
        f"\n\nReturn ONLY this JSON:\n{schema}"
    )
    return _SYSTEM_HEADER, user


def build_vocab_prompt(difficulty: str, specialty: str, topic: str, objectives: Optional[str] = None, instructions: Optional[str] = None) -> Tuple[str, str]:
    schema = """{
  "topic": "short label for this vocabulary set",
  "difficulty": "beginner|intermediate|advanced",
  "items": [
    {"term": "medical term", "definition": "plain-English definition", "example_sentence": "the term used in a clinical sentence", "pronunciation": "simple phonetic guide", "collocations": ["common word pairing 1", "common word pairing 2"], "related_terms": ["related term 1"], "synonym": "a common synonym, if one exists", "clinical_context": "when/how a nurse would actually use this term in practice"}
  ]
}"""
    user = (
        f"Create a set of 5-6 OET-relevant clinical vocabulary terms. Favor words nurses actually use in everyday "
        f"clinical communication (handover, patient education, documentation) over rare academic vocabulary. Keep "
        f"every field concise -- a few words each, not full sentences (example_sentence excepted).\n"
        f"{_shared_context(difficulty, specialty, topic, objectives, instructions)}\n\n{_DIVERSITY_HINT}"
        f"\n\nReturn ONLY this JSON:\n{schema}"
    )
    return _SYSTEM_HEADER, user


def build_grammar_prompt(difficulty: str, specialty: str, topic: str, objectives: Optional[str] = None, instructions: Optional[str] = None) -> Tuple[str, str]:
    schema = """{
  "topic": "short label for this grammar point, e.g. 'Reported speech for handover'",
  "difficulty": "beginner|intermediate|advanced",
  "explanation": "plain-English explanation of the grammar point, with clinical-context examples",
  "practice_questions": [
    {"content": "question text", "type": "mcq", "options": ["option 1", "option 2", "option 3", "option 4"], "correct_answer": "must match one option exactly", "explanation": "why the correct answer is right and briefly why each wrong option is wrong, grounded in the clinical example"}
  ]
}"""
    user = (
        f"Create an OET-relevant grammar lesson for nursing candidates. Base it on a mistake nurses actually make "
        f"in real clinical communication (documentation, handover, or patient-facing speech) rather than generic "
        f"English grammar -- ground the explanation and every practice question in an authentic clinical example.\n"
        f"{_shared_context(difficulty, specialty, topic, objectives, instructions)}\n\n{_DIVERSITY_HINT}"
        f"\n\nReturn ONLY this JSON:\n{schema}"
    )
    return _SYSTEM_HEADER, user


BUILDERS: Dict[str, Callable[..., Tuple[str, str]]] = {
    "speaking": build_speaking_prompt,
    "reading": build_reading_prompt,
    "listening": build_listening_prompt,
    "writing": build_writing_prompt,
    "vocab": build_vocab_prompt,
    "grammar": build_grammar_prompt,
}


def build_prompt(module: str, difficulty: str, specialty: str, topic: str, objectives: Optional[str] = None, instructions: Optional[str] = None) -> Tuple[str, str]:
    builder = BUILDERS.get(module)
    if builder is None:
        raise ValueError(f"Unknown module: {module}")
    return builder(difficulty, specialty, topic, objectives, instructions)
