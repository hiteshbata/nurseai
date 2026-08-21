"""E2.4.1: the canonical Skill Registry / Taxonomy seed.

This is metadata only -- a catalog of every distinct skill/criterion/part/
technique concept currently tracked anywhere in the app, given a stable
dotted `code`. It does NOT replace the legacy colon-tag strings
(`reading:A`, `speaking:fluency`, `technique:scanning`, ...) that
skill_graph.py / user_skill_stats / skill_observations / techniques /
listening_mistake_events already read and write -- those are untouched.

`legacy_tag` below is Python-side only (not a DB column on `skills`): it's
the join key skill_registry_reconciliation.py uses to compare what's
actually being written against what the registry knows about. The `skills`
table itself only ever gets (code, name, module, kind, description).

Source of truth per entry, so this list is regenerated from code, not
guessed:
  - reading:A/B/C, listening:A/B/C -- part-level tags routers write directly
    (see app/routers/reading.py, app/routers/listening.py)
  - reading:skill:* -- app/services/reading_skills.py SKILL_LABELS
  - speaking:* (3-mode) and speaking:* (9-mode) -- the two scoring rubrics
    in app/services/ai_scoring.py (score_speaking prompt branches)
  - writing:* -- app/services/ai_scoring.py WRITING_CRITERIA_MAX
  - technique:* -- app/services/seed_techniques.py TECHNIQUES (module +
    skill_tag per row; technique_progress.technique_skill_tag prefixes it)

Kept as four data-only lists (not one flat list) so each source stays easy
to diff against its origin file when that file changes.
"""
from typing import Dict, List, Optional, TypedDict


class SkillSeed(TypedDict):
    legacy_tag: str
    code: str
    name: str
    module: str
    kind: str
    description: Optional[str]


VALID_MODULES = {"reading", "listening", "writing", "speaking"}
VALID_KINDS = {"part", "comprehension_skill", "criterion", "technique"}

# ── reading & listening part tags ───────────────────────────────────────
_PARTS: List[SkillSeed] = [
    {"legacy_tag": f"{module}:{letter}", "code": f"{module}.part.{letter.lower()}",
     "name": f"{module.title()} Part {letter}", "module": module, "kind": "part",
     "description": None}
    for module in ("reading", "listening")
    for letter in ("A", "B", "C")
]

# ── reading comprehension skills (reading_skills.SKILL_LABELS) ─────────
_READING_SKILL_LABELS = {
    "scanning": "Scanning (finding which text has the info)",
    "detail": "Detail (specific stated facts)",
    "inference": "Inference (reading between the lines)",
    "main-idea": "Main idea / purpose",
    "vocabulary": "Vocabulary & word meaning",
    "writer-view": "Writer's view & attitude",
}
_READING_SKILLS: List[SkillSeed] = [
    {"legacy_tag": f"reading:skill:{tag}", "code": f"reading.skill.{tag.replace('-', '_')}",
     "name": tag.replace("-", " ").replace("_", " ").title(), "module": "reading",
     "kind": "comprehension_skill", "description": label}
    for tag, label in _READING_SKILL_LABELS.items()
]

# ── speaking criteria: 3-mode and 9-mode are distinct rubrics, never merged ─
_SPEAKING_3MODE = {
    "clinical_communication": "Did the nurse gather information effectively, explain clearly, and respond to patient cues?",
    "linguistic_delivery": "Was speech clear, fluent, and at an appropriate level for the patient?",
    "relationship_building": "Did the nurse show empathy, respect, and build rapport with the patient?",
}
_SPEAKING_9MODE = {
    "empathy": "Acknowledges the patient's emotional state, validates concerns, uses supportive language alongside clinical information.",
    "patient_perspective": "Did nurse actively listen and respond to patient cues, concerns and questions throughout?",
    "providing_structure": "Did conversation follow OET sequence: introduce, enquire, explain, advise?",
    "information_gathering": "Did nurse use open questions first then closed, and check understanding?",
    "information_giving": "Was advice clear, concise, jargon-free, given as suggestions not orders?",
    "intelligibility": "Was speech clear? Correct word stress, intonation, rhythm?",
    "fluency": "Smooth pace? Natural pauses? Minimal filler words?",
    "appropriateness_of_language": "Suitable register for patient? Medical terms explained in plain language?",
    "grammar": "Range of grammar structures used accurately? Varied vocabulary and idioms?",
}
_SPEAKING_CRITERIA: List[SkillSeed] = [
    {"legacy_tag": f"speaking:{tag}", "code": f"speaking.criterion.{tag}",
     "name": tag.replace("_", " ").title(), "module": "speaking", "kind": "criterion",
     "description": label}
    for tag, label in {**_SPEAKING_3MODE, **_SPEAKING_9MODE}.items()
]

# ── writing criteria (ai_scoring.WRITING_CRITERIA_MAX) ─────────────────
_WRITING_CRITERIA_TAGS = ["purpose", "content", "conciseness", "genre_style", "organization", "language"]
_WRITING_CRITERIA: List[SkillSeed] = [
    {"legacy_tag": f"writing:{tag}", "code": f"writing.criterion.{tag}",
     "name": tag.replace("_", " ").title(), "module": "writing", "kind": "criterion",
     "description": None}
    for tag in _WRITING_CRITERIA_TAGS
]

# ── technique tags (seed_techniques.TECHNIQUES; module+skill_tag per row) ─
# (module, skill_tag, name, description) -- mirrors seed_techniques.py exactly.
_TECHNIQUES = [
    ("reading", "skimming", "Skimming", "Read fast for the gist -- headings, topic sentences, first/last lines -- to grasp what a text is about before you need any detail."),
    ("reading", "scanning", "Scanning", "Move your eyes over a text hunting for one specific word, number, or phrase -- not understanding, just finding."),
    ("reading", "elimination", "Elimination", "Systematically cross out options the text contradicts or doesn't support, narrowing 4 choices down before picking."),
    ("reading", "textual_verification", "Textual Verification", "For any answer you pick, find and confirm the specific line of text that supports it -- proof, not a guess."),
    ("listening", "pre_listening", "Pre-listening Preparation", "Read the questions and notes template before the audio plays so you already know what information you're hunting for."),
    ("listening", "keyword_prediction", "Keyword Prediction", "From the question wording, guess the vocabulary the speaker will actually use, since the audio rarely repeats the question word-for-word."),
    ("listening", "signpost_tracking", "Signpost Tracking", "Catch phrases like 'however', 'the main issue is', or 'moving on to' that flag structure shifts and important information."),
    ("listening", "paraphrase_synonym_recognition", "Paraphrase & Synonym Recognition", "Match the meaning, not the exact wording, between what's asked and what's said."),
    ("writing", "audience_purpose_identification", "Audience & Purpose Identification", "Establish the reader (GP, specialist, discharge coordinator...) and the goal (referral, discharge summary, update) to shape tone and content correctly."),
    ("writing", "case_note_selection", "Case-Note Selection", "Not every case note belongs in the letter -- select only what serves the referral's purpose."),
    ("writing", "sentence_transformation_synthesis", "Sentence Transformation & Synthesis", "Combine and reword shorthand notes into fluent, professional prose suitable for a clinical letter."),
    ("speaking", "setting_context", "Setting Context", "Introduce yourself, confirm the patient's identity, and state the purpose of the conversation before diving into questions."),
    ("speaking", "empathy_validation", "Empathy & Validation", "Name and validate what the patient is feeling -- fear, frustration, confusion -- rather than only addressing the clinical facts."),
    ("speaking", "chunking_signposting", "Chunking & Signposting", "Deliver information in short pieces with verbal signposts ('firstly...', 'the next thing is...') instead of one long unbroken explanation."),
]
_TECHNIQUE_SKILLS: List[SkillSeed] = [
    {"legacy_tag": f"technique:{tag}", "code": f"technique.{tag}", "name": name,
     "module": module, "kind": "technique", "description": description}
    for module, tag, name, description in _TECHNIQUES
]

SEED_SKILLS: List[SkillSeed] = _PARTS + _READING_SKILLS + _SPEAKING_CRITERIA + _WRITING_CRITERIA + _TECHNIQUE_SKILLS

# legacy colon-tag -> canonical dotted code, for skill_registry_reconciliation.py.
LEGACY_TAG_TO_CODE: Dict[str, str] = {s["legacy_tag"]: s["code"] for s in SEED_SKILLS}


if __name__ == "__main__":
    # ponytail: one runnable check -- the seed list is the whole feature.
    assert len(SEED_SKILLS) == 44, f"expected 44 seed rows, got {len(SEED_SKILLS)}"
    codes = [s["code"] for s in SEED_SKILLS]
    assert len(codes) == len(set(codes)), "duplicate code in SEED_SKILLS"
    tags = [s["legacy_tag"] for s in SEED_SKILLS]
    assert len(tags) == len(set(tags)), "duplicate legacy_tag in SEED_SKILLS"
    assert {s["module"] for s in SEED_SKILLS} <= VALID_MODULES
    assert {s["kind"] for s in SEED_SKILLS} <= VALID_KINDS
    print(f"OK -- {len(SEED_SKILLS)} seed rows")
