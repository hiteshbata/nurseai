"""Comprehension-skill tagging for OET Reading questions, derived from the
question stem at grade time -- no per-question column, no AI backfill. The tag
feeds the shared skill graph as `reading:skill:<tag>` so the student's weak
question TYPES (not just weak parts) surface in the weakness summary.

Deliberately a transparent keyword heuristic, not an AI call: it runs in the hot
grading path for every question, must be free and deterministic, and a rough tag
is enough to nudge "you miss inference questions". Upgrade to AI/stored tags only
if the heuristic proves too coarse in practice."""
import re

# Skill tag -> the student-facing label the weakness summary shows.
SKILL_LABELS = {
    "scanning": "Scanning (finding which text has the info)",
    "detail": "Detail (specific stated facts)",
    "inference": "Inference (reading between the lines)",
    "main-idea": "Main idea / purpose",
    "vocabulary": "Vocabulary & word meaning",
    "writer-view": "Writer's view & attitude",
}

# Checked in order; first hit wins, so more specific patterns come first.
_PATTERNS = [
    ("writer-view", re.compile(r"writer'?s?\s+(view|opinion|attitude|feel|think|tone)|attitude of|point of view", re.I)),
    ("vocabulary", re.compile(r"\bthe word\b|\bthe phrase\b|\brefers? to\b|\bmeaning of\b|\bwhat does .{0,20}\bmean\b|\bin this context\b", re.I)),
    ("main-idea", re.compile(r"main (idea|point|purpose)|mainly (about|concerned)|primary purpose|overall|the purpose of (this|the) (text|paragraph|guideline|memo|email)|best title", re.I)),
    ("inference", re.compile(r"\bimpl(y|ies|ied)\b|\binfer\b|\bsuggest(s|ed|ing)?\b|\bindicat(e|es|ed)\b|we can conclude|it is clear that|point (is )?being made", re.I)),
]


def classify_reading_skill(content: str, qtype: str, part: str) -> str:
    """Map one question to a single comprehension skill tag.

    Part A "which text" matching questions are pure scanning; Part A short-answer
    is locating a specific detail. For Part B/C, fall back to stem keywords, then
    to 'detail' (the commonest OET reading skill) when nothing matches."""
    if part == "A":
        return "scanning" if qtype == "mcq" else "detail"
    text = content or ""
    for tag, pat in _PATTERNS:
        if pat.search(text):
            return tag
    return "detail"


if __name__ == "__main__":
    # ponytail: one runnable check -- the heuristic is the whole feature's accuracy.
    cases = [
        ("Which text mentions the dosage?", "mcq", "A", "scanning"),
        ("Complete: the ideal dressing is ___", "short_answer", "A", "detail"),
        ("What point is being made about multi-trauma patients?", "mcq", "C", "inference"),
        ("The word 'it' in line 4 refers to what?", "mcq", "C", "vocabulary"),
        ("What is the main purpose of this memo?", "mcq", "B", "main-idea"),
        ("What is the writer's attitude to the new policy?", "mcq", "C", "writer-view"),
        ("How often should the dressing be changed?", "mcq", "C", "detail"),  # no keyword -> detail
        ("This guideline suggests staff should prioritise which action?", "mcq", "C", "inference"),
    ]
    for content, qtype, part, expected in cases:
        got = classify_reading_skill(content, qtype, part)
        assert got == expected, f"{content!r} -> {got}, expected {expected}"
    assert set(SKILL_LABELS) >= {t for _, t in [(0, c[3]) for c in cases]}, "every tag needs a label"
    print("OK")
