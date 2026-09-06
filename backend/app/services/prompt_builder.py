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



# Part A's data contract (four texts, matching MCQs over the text labels,
# short_answer word/phrase questions) mirrors the extraction contract proven
# in READING_EXTRACT_PROMPT (backend/app/routers/reading.py). Reproduced here
# rather than imported so the prompt builder doesn't couple to router code --
# see Phase 3B-2 audit.
#
# Phase 3B-6A: the first controlled generation used inline "Text A: ..."
# headers here, which PART_A_HEADER (backend/app/routers/reading.py) doesn't
# match -- that regex requires the header on its own line, nothing after it
# but optional punctuation. The schema/instructions below now demonstrate the
# actual parser-compatible standalone-header form, and the question-count
# guidance was tightened from "roughly 20" to the exact locked distribution
# _validate_reading_part_a (app/services/draft_generator.py) enforces.
_READING_PART_A_SCHEMA = """{
  "title": "short descriptive title for this passage",
  "part": "A",
  "difficulty": "beginner|intermediate|advanced",
  "body": "Text A\\n[Text A content]\\n\\nText B\\n[Text B content]\\n\\nText C\\n[Text C content]\\n\\nText D\\n[Text D content]",
  "questions": [
    {"content": "In which text can you find information about...?", "type": "mcq", "options": ["Text A", "Text B", "Text C", "Text D"], "correct_answer": "Text B"},
    {"content": "sentence-completion or short-answer question text", "type": "short_answer", "options": [], "correct_answer": "reference answer text"}
  ]
}"""

_READING_PART_A_INSTRUCTIONS = (
    "Create an original OET Reading Part A task -- a distinct multi-text task, NOT a single passage like Part B "
    "or C. Part A consists of FOUR separate short texts on a shared clinical topic, labelled Text A, Text B, "
    "Text C and Text D. Put all four in \"body\", concatenated in order. Each text's header MUST be on its own "
    "line by itself -- just \"Text A\" (or \"Text B\"/\"Text C\"/\"Text D\"), nothing else on that line, no colon, "
    "no content appended after it. The text's content starts on the NEXT line. Example body structure:\n\n"
    "Text A\n[Text A content]\n\nText B\n[Text B content]\n\nText C\n[Text C content]\n\nText D\n[Text D content]\n\n"
    "Do NOT put a colon or any content on the header line itself, and do NOT start the text on the same line as "
    "the header -- a header sharing its line with content is rejected. "
    "Each text should be original, authentic healthcare content (e.g. extracts from clinical guidelines, drug "
    "information, hospital policy, or care protocols) in the requested specialty/topic.\n\n"
    "Text heading wording: do NOT give a text a heading/title that echoes the wording of the matching question "
    "written about it -- e.g. if a question asks about \"acceptable blood glucose targets\", do not title that "
    "text \"Inpatient Glycaemic Targets\". A candidate must not be able to answer a matching question by keyword-"
    "matching the heading alone; the requested information must still be clearly present in the text's body, just "
    "not restated in its heading.\n\n"
    "Source/style diversity: vary the four texts' presentation style so they read like they came from different "
    "real healthcare sources rather than four copies of the same bullet-point protocol -- e.g. a guideline "
    "extract, hospital policy excerpt, medication/drug information sheet, patient-management protocol, a "
    "table-like reference, a clinical memo, or a checklist, as naturally fits the topic. Do not force every style "
    "every time and do not add decorative formatting purely for variety -- only use structure that would "
    "realistically occur in that kind of source. All four texts must still cohere around the same clinical "
    "topic.\n\n"
    "Generate EXACTLY 20 questions total, all answerable from the four texts, in this EXACT order and distribution:\n\n"
    "Q1-Q5: EXACTLY 5 matching MCQs (\"In which text can you find information about...?\" / \"Which text "
    "mentions...?\"). type=\"mcq\", options exactly [\"Text A\", \"Text B\", \"Text C\", \"Text D\"], "
    "correct_answer one of those four labels. Phrase each question as a paraphrase or description of information "
    "found in the text, not a copy of its heading.\n"
    "Q6-Q13: EXACTLY 8 sentence-completion short-answer questions (a sentence with a gap, answered with a word or "
    "short phrase from one of the texts). type=\"short_answer\", options=[] (empty array), correct_answer = the "
    "reference word or phrase as plain text. Before finalizing each one, check that QUESTION + CORRECT_ANSWER "
    "reads as one grammatically natural sentence when the answer is inserted into the blank -- reword the gap if "
    "it doesn't.\n"
    "Q14-Q20: EXACTLY 7 direct short-answer questions (a direct question answered with a word or short phrase "
    "from one of the texts). type=\"short_answer\", options=[] (empty array), correct_answer = the reference word "
    "or phrase as plain text.\n\n"
    "Unique answers (Q6-Q20): every short_answer question must have exactly one reasonably defensible "
    "correct_answer from the texts. If the text supports more than one valid answer (e.g. \"give the medication "
    "intramuscularly or subcutaneously\"), do NOT write a question whose blank only one of those would fill -- "
    "either ask for the full phrase covering all valid options (\"which two routes...?\", answer \"intramuscularly "
    "or subcutaneously\") or ask about a different, single-valued detail instead. Never let correct_answer be just "
    "one of several possible answers the text supports.\n\n"
    "Do NOT generate additional MCQs beyond Q1-Q5. Do NOT change this order. Do NOT merge or split these three "
    "groups. Final distribution must be exactly 5 mcq + 15 short_answer = 20 questions -- not 6, not 7, not "
    "approximately 20.\n\n"
    "Do not invent a different Part A format or question type -- use only \"mcq\" (matching) and \"short_answer\" "
    "as described above."
)

# Part B's data contract (Phase 4A): SIX independent short extracts, each its
# own passage with exactly one 3-option mcq question. Container shape ("part"
# + "passages": [...]) is deliberately NOT the flat title/body/questions shape
# every other module builder uses -- one Part B generation is six independent
# production rows (matching how PDF extraction already saves Part B: six
# separate reading_passages rows, see READING_EXTRACT_PROMPT in
# app/routers/reading.py), not one row like Part A's four-texts-in-one-body
# packing. _validate_reading_part_b (app/services/draft_generator.py) enforces
# this shape structurally. Publishing six rows from one draft is out of scope
# for this phase -- see draft_generator.py's Part B section for details.
_READING_PART_B_SCHEMA = """{
  "part": "B",
  "passages": [
    {
      "title": "short descriptive title for this extract",
      "body": "the short independent workplace-healthcare text extract",
      "questions": [
        {"content": "the single question about this extract", "type": "mcq", "options": ["option A text", "option B text", "option C text"], "correct_answer": "must match one option exactly"}
      ]
    }
  ]
}"""

_READING_PART_B_INSTRUCTIONS = (
    "Create an original OET Reading Part B task -- EXACTLY 6 independent short workplace-healthcare extracts, "
    "NOT one long passage like Part C or the default reading task, and NOT four texts sharing one topic like "
    "Part A. Return them as 6 separate entries in \"passages\", each with its own \"title\", \"body\", and "
    "\"questions\" array.\n\n"
    "Each extract is a short standalone workplace document, roughly 80-150 words. Vary the source style across "
    "the six extracts rather than repeating the same style -- appropriate styles include a hospital policy "
    "excerpt, clinical guideline extract, medication information sheet, workplace memo, instruction/procedure "
    "sheet, notice, checklist, or professional communication (e.g. an email or handover note). Do not force "
    "decorative formatting that wouldn't naturally occur in that kind of real document. Keep each extract fully "
    "independent -- do not make one extract necessary to understand or answer another.\n\n"
    "Each extract is followed by EXACTLY ONE question, in that extract's own \"questions\" array (a list of "
    "exactly 1 item). Every question has type=\"mcq\" with EXACTLY 3 options representing choices A, B and C, and "
    "correct_answer must exactly match one of those 3 option strings, character for character. No short_answer "
    "questions anywhere in Part B.\n\n"
    "Each question must test understanding, application, or inference of its own extract's content -- not a "
    "detail copied verbatim, and not answerable from outside knowledge. The correct option must not be obvious "
    "merely from a heading or label; a candidate must read the extract's body to distinguish the correct option "
    "from the other two. Exactly one option may be defensible as correct -- avoid wording that leaves two options "
    "both arguably right. Do not repeat the same question, extract topic, or answer content across the six "
    "extracts.\n\n"
    "Return exactly 6 passages, each with exactly 1 mcq question and exactly 3 options -- not 5, not 7, not a "
    "different question or option count."
)


# Part C's data contract (Phase 4C-3): exactly 2 independent long-form
# texts, each its own passage with exactly 8 mcq questions (4 options each).
# Shape mirrors Part B's container ("part" + a list of entries), not Part A's
# single-body packing -- one Part C generation is two independent production
# rows (reading_passages, passage_seq 0/1), reusing the multi-passage
# publishing architecture Part B already established. See
# _validate_reading_part_c (draft_generator.py) for the structural gate and
# draft_publisher.py's _reading_part_c_payloads for the publish mapping.
_READING_PART_C_SCHEMA = """{
  "part": "C",
  "texts": [
    {
      "title": "short descriptive title for this text",
      "body": "the first independent journalistic/feature-style healthcare text",
      "questions": [
        {"content": "question text", "type": "mcq", "options": ["option 1", "option 2", "option 3", "option 4"], "correct_answer": "must match one option exactly"}
      ]
    },
    {
      "title": "short descriptive title for this text",
      "body": "the second independent journalistic/feature-style healthcare text, on a different topic",
      "questions": [
        {"content": "question text", "type": "mcq", "options": ["option 1", "option 2", "option 3", "option 4"], "correct_answer": "must match one option exactly"}
      ]
    }
  ]
}"""

_READING_PART_C_INSTRUCTIONS = (
    "Create an original OET Reading Part C task -- EXACTLY 2 independent long-form texts, NOT one long passage "
    "shared between them, and NOT six short extracts like Part B. Return them as 2 separate entries in \"texts\", "
    "each with its own \"title\", \"body\", and \"questions\" array. The two texts must cover distinct topics and "
    "must not duplicate each other's subject matter -- do not write two angles on the same story.\n\n"
    "Write each text in an authentic journalistic/feature-style healthcare register -- e.g. a magazine feature, "
    "professional-body news article, or health-affairs commentary -- not a clinical guideline or textbook extract. "
    "Aim for approximately 800-1000 words per text as a general target; this is guidance for realistic length, not "
    "an exact figure to hit precisely. You may bold or otherwise mark a phrase in the text where it naturally helps "
    "a reader locate an answer, but do not force a fixed number of marked phrases -- use them only where useful, "
    "including not at all.\n\n"
    "Each text is followed by EXACTLY 8 questions, in that text's own \"questions\" array. Questions 1-7 MUST "
    "progress strictly forward through the text in chronological order -- question 1 targets the earliest "
    "paragraph its information appears in, and each subsequent question up to question 7 targets a paragraph at "
    "the same position or later than the one before it. Once a question targets a later paragraph, no later "
    "question among Q1-Q7 may go back to an earlier paragraph.\n\n"
    "Question 8 is different: it MUST be a whole-text question assessing the overall purpose, main theme, central "
    "argument, overall conclusion, or the author's overall message of the ENTIRE text -- not a detail from any "
    "single paragraph. Question 8 must NOT refer to a specific paragraph, the final paragraph, a specific "
    "sentence, a specific example, or a specific person or study named in the text. Do not phrase question 8 as "
    "\"In the final paragraph...\", \"According to paragraph 7...\", \"What does the author say about X in "
    "paragraph...\", or any other wording that points to a specific paragraph or location in the text. Question 8 "
    "must remain the last question in the array.\n\n"
    "Every question has type=\"mcq\" with EXACTLY 4 options, and correct_answer must "
    "exactly match one of those 4 option strings, character for character. Never write a question about one text "
    "that requires information from the other text -- each text's questions must be answerable from that text "
    "alone.\n\n"
    "Mix question types across each text's 8 questions -- retrieval of a specific detail, inference, the purpose "
    "of a statement or paragraph, the significance of a fact, and reference (what a word/phrase refers back to) -- "
    "rather than making all 8 direct detail lookups. Do not write pure vocabulary questions that only ask what a "
    "word means in isolation; every question must test understanding of the text's content. The correct option "
    "must not be guessable from a heading alone, and distractors must be plausible, paragraph-level near-misses "
    "(drawn from real content elsewhere in the same paragraph or text) rather than obviously wrong filler. Exactly "
    "one option may be defensible as correct per question -- avoid wording that leaves two options both arguably "
    "right.\n\n"
    "Return exactly 2 texts, each with exactly 8 mcq questions and exactly 4 options per question -- not 1, not 3, "
    "not a different question or option count. 2 texts x 8 questions = 16 questions total."
)


def build_reading_prompt(difficulty: str, specialty: str, topic: str, objectives: Optional[str] = None, instructions: Optional[str] = None, part: Optional[str] = None) -> Tuple[str, str]:
    if part == "A":
        user = (
            f"{_READING_PART_A_INSTRUCTIONS}\n"
            f"{_shared_context(difficulty, specialty, topic, objectives, instructions)}\n\n{_DIVERSITY_HINT}"
            f"\n\nReturn ONLY this JSON:\n{_READING_PART_A_SCHEMA}"
        )
        return _SYSTEM_HEADER, user

    if part == "B":
        user = (
            f"{_READING_PART_B_INSTRUCTIONS}\n"
            f"{_shared_context(difficulty, specialty, topic, objectives, instructions)}\n\n{_DIVERSITY_HINT}"
            f"\n\nReturn ONLY this JSON:\n{_READING_PART_B_SCHEMA}"
        )
        return _SYSTEM_HEADER, user

    if part == "C":
        user = (
            f"{_READING_PART_C_INSTRUCTIONS}\n"
            f"{_shared_context(difficulty, specialty, topic, objectives, instructions)}\n\n{_DIVERSITY_HINT}"
            f"\n\nReturn ONLY this JSON:\n{_READING_PART_C_SCHEMA}"
        )
        return _SYSTEM_HEADER, user

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


# Locked Listening Part A contract (Phase 3B): EXACTLY 2 independent extracts,
# each a nurse-patient/nurse-colleague consultation, each followed by 12
# short_answer gap-fill questions against a note-completion "body" template
# (headings + context bullets + numbered blanks matching the 12 questions).
# 2 extracts x 12 questions = 24 total. Container shape ("part" + "extracts":
# [...]) mirrors Reading Part B/C's per-slot list rather than the legacy flat
# title/transcript/questions shape above -- one Part A generation is 2
# independent production rows (listening_sections), not one. transcript is
# the canonical [{speaker, text}] shape used to generate/store the audio;
# accepted_answers is optional alternate-phrasing support, stored but not
# wired into grading this phase (see draft_generator.py's Part A validator).
_LISTENING_PART_A_SCHEMA = """{
  "part": "A",
  "prep_seconds": 30,
  "audio_mode": "dialogue",
  "extracts": [
    {
      "title": "short descriptive title for this extract",
      "transcript": [{"speaker": "Nurse", "text": "..."}, {"speaker": "Patient", "text": "..."}],
      "body": "note-completion template: headings, context bullets, and 12 numbered blanks, e.g. 'Reason for visit\\n- ...\\n\\nHistory\\n1. Patient reports (1) ______\\n2. ...'",
      "questions": [
        {"content": "gap-fill prompt for blank (1), phrased so the transcript answer completes it naturally", "type": "short_answer", "options": [], "correct_answer": "reference word or short phrase from the transcript", "accepted_answers": ["alternate acceptable phrasing"]}
      ]
    },
    {
      "title": "short descriptive title for the second extract",
      "transcript": [{"speaker": "Nurse", "text": "..."}, {"speaker": "Patient", "text": "..."}],
      "body": "note-completion template for the second extract, same shape as above",
      "questions": [
        {"content": "gap-fill prompt for blank (1) of the second extract", "type": "short_answer", "options": [], "correct_answer": "reference word or short phrase", "accepted_answers": []}
      ]
    }
  ]
}"""

_LISTENING_PART_A_INSTRUCTIONS = (
    "Create an original OET Listening Part A task -- EXACTLY 2 independent extracts, each a two-speaker dialogue "
    "(a nurse taking a patient's history, or a nurse consulting a colleague/patient about a clinical situation), "
    "NOT one shared conversation. Return them as 2 separate entries in \"extracts\", each with its own \"title\", "
    "\"transcript\", \"body\", and \"questions\".\n\n"
    "\"transcript\" is a list of speaker turns: [{\"speaker\": \"Nurse\", \"text\": \"...\"}, {\"speaker\": \"Patient\", "
    "\"text\": \"...\"}, ...]. Write natural spoken English -- realistic hesitations, interruptions, and clarification "
    "requests -- not scripted or robotic dialogue. The two extracts must cover distinct clinical situations.\n\n"
    "\"body\" is a note-completion template a candidate fills in while listening: section headings, short context "
    "bullets, and EXACTLY 12 numbered blanks, each answerable from that extract's transcript in the order the "
    "information is spoken. Every blank number must have a matching entry at the same position in \"questions\".\n\n"
    "Each extract has EXACTLY 12 short_answer questions, one per blank, in transcript order. type=\"short_answer\", "
    "options=[] (empty array), correct_answer = the reference word or short phrase from the transcript that fills "
    "that blank. \"accepted_answers\" is an optional array of other acceptable phrasings for the same blank -- use "
    "it only when the transcript genuinely supports more than one valid wording, otherwise leave it an empty array; "
    "never let correct_answer alone be just one of several answers the transcript actually supports without also "
    "listing the others in accepted_answers.\n\n"
    "Return exactly 2 extracts, each with exactly 12 short_answer questions -- not 10, not 15. "
    "2 extracts x 12 questions = 24 questions total. \"prep_seconds\" must be exactly 30 and \"audio_mode\" must be "
    "exactly \"dialogue\" -- copy those two fields into your output unchanged."
)


# Locked Listening Part B contract (Phase 3B): EXACTLY 6 independent short
# workplace extracts, each its own 1-mcq/3-option question -- same shape and
# spirit as Reading Part B (_READING_PART_B_SCHEMA above), over audio instead
# of text. 6 independent production rows (listening_sections) from one draft.
_LISTENING_PART_B_SCHEMA = """{
  "part": "B",
  "prep_seconds": 15,
  "audio_mode": "dialogue",
  "extracts": [
    {
      "title": "short descriptive title for this extract",
      "transcript": [{"speaker": "Nurse", "text": "..."}, {"speaker": "Colleague", "text": "..."}],
      "questions": [
        {"content": "the single question about this extract", "type": "mcq", "options": ["option A text", "option B text", "option C text"], "correct_answer": "must match one option exactly"}
      ]
    }
  ]
}"""

_LISTENING_PART_B_INSTRUCTIONS = (
    "Create an original OET Listening Part B task -- EXACTLY 6 independent short workplace-healthcare extracts "
    "(a handover, briefing, team meeting snippet, or short instruction from a colleague), NOT one long recording. "
    "Return them as 6 separate entries in \"extracts\", each with its own \"title\", \"transcript\", and "
    "\"questions\".\n\n"
    "\"transcript\" is a list of speaker turns: [{\"speaker\": \"...\", \"text\": \"...\"}, ...], natural spoken "
    "English for a short two-speaker (or single-speaker briefing) workplace exchange. Keep each extract fully "
    "independent -- do not make one extract necessary to understand another. Vary the workplace situation across "
    "the six extracts rather than repeating the same scenario.\n\n"
    "Each extract is followed by EXACTLY ONE question, in that extract's own \"questions\" array (a list of exactly "
    "1 item). Every question has type=\"mcq\" with EXACTLY 3 options, and correct_answer must exactly match one of "
    "those 3 option strings, character for character. Each question must test understanding, application, or "
    "inference of the extract's content -- not a detail answerable from outside knowledge. Exactly one option may "
    "be defensible as correct.\n\n"
    "Return exactly 6 extracts, each with exactly 1 mcq question and exactly 3 options. \"prep_seconds\" must be "
    "exactly 15 and \"audio_mode\" must be exactly \"dialogue\" -- copy those two fields into your output unchanged."
)


# Locked Listening Part C contract (Phase 3B): EXACTLY 2 independent
# long-form extracts (interview or presentation), each with 6 mcq questions
# over 3 options -- mirrors Reading Part C's per-slot list shape. Unlike
# Part A/B, audio_mode is chosen PER EXTRACT here (dialogue for an interview,
# monologue for a presentation), not a single top-level value.
_LISTENING_PART_C_SCHEMA = """{
  "part": "C",
  "prep_seconds": 90,
  "extracts": [
    {
      "title": "short descriptive title for this extract",
      "audio_mode": "dialogue",
      "transcript": [{"speaker": "Interviewer", "text": "..."}, {"speaker": "Guest", "text": "..."}],
      "questions": [
        {"content": "question text", "type": "mcq", "options": ["option 1", "option 2", "option 3"], "correct_answer": "must match one option exactly"}
      ]
    },
    {
      "title": "short descriptive title for the second extract",
      "audio_mode": "monologue",
      "transcript": [{"speaker": "Presenter", "text": "..."}],
      "questions": [
        {"content": "question text", "type": "mcq", "options": ["option 1", "option 2", "option 3"], "correct_answer": "must match one option exactly"}
      ]
    }
  ]
}"""

_LISTENING_PART_C_INSTRUCTIONS = (
    "Create an original OET Listening Part C task -- EXACTLY 2 independent long-form extracts, each either an "
    "interview (two speakers, audio_mode=\"dialogue\") or a presentation/talk (one speaker, audio_mode=\"monologue\") "
    "on a healthcare topic. Pick a mode per extract rather than defaulting both to the same one. Return them as 2 "
    "separate entries in \"extracts\", each with its own \"title\", \"audio_mode\", \"transcript\", and "
    "\"questions\". The two extracts must cover distinct topics.\n\n"
    "\"transcript\" is a list of speaker turns: [{\"speaker\": \"...\", \"text\": \"...\"}, ...] -- for a monologue "
    "every turn's speaker is the same presenter. Write natural spoken English -- hesitations, self-corrections, "
    "signposting phrases (\"so, moving on to...\") -- not a written article read aloud.\n\n"
    "Each extract has EXACTLY 6 mcq questions, in \"questions\", progressing forward through the extract in the "
    "order the information is spoken. Every question has type=\"mcq\" with EXACTLY 3 options, and correct_answer "
    "must exactly match one of those 3 option strings, character for character. Mix question types -- specific "
    "detail, inference, speaker's opinion/attitude, purpose of a remark -- rather than making all 6 direct detail "
    "lookups. The correct option must not be guessable without listening; distractors must be plausible near-misses "
    "drawn from real content elsewhere in the extract.\n\n"
    "Return exactly 2 extracts, each with exactly 6 mcq questions and exactly 3 options per question. "
    "\"prep_seconds\" must be exactly 90 -- copy that field into your output unchanged."
)


def build_listening_prompt(difficulty: str, specialty: str, topic: str, objectives: Optional[str] = None, instructions: Optional[str] = None, part: Optional[str] = None) -> Tuple[str, str]:
    if part == "A":
        user = (
            f"{_LISTENING_PART_A_INSTRUCTIONS}\n"
            f"{_shared_context(difficulty, specialty, topic, objectives, instructions)}\n\n{_DIVERSITY_HINT}"
            f"\n\nReturn ONLY this JSON:\n{_LISTENING_PART_A_SCHEMA}"
        )
        return _SYSTEM_HEADER, user

    if part == "B":
        user = (
            f"{_LISTENING_PART_B_INSTRUCTIONS}\n"
            f"{_shared_context(difficulty, specialty, topic, objectives, instructions)}\n\n{_DIVERSITY_HINT}"
            f"\n\nReturn ONLY this JSON:\n{_LISTENING_PART_B_SCHEMA}"
        )
        return _SYSTEM_HEADER, user

    if part == "C":
        user = (
            f"{_LISTENING_PART_C_INSTRUCTIONS}\n"
            f"{_shared_context(difficulty, specialty, topic, objectives, instructions)}\n\n{_DIVERSITY_HINT}"
            f"\n\nReturn ONLY this JSON:\n{_LISTENING_PART_C_SCHEMA}"
        )
        return _SYSTEM_HEADER, user

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


# Controlled vocabulary for letter_type -- the four types actually evidenced
# by the reference OET Nursing Writing samples (discharge, transfer, urgent
# referral, ongoing-care/continuity referral). Kept in sync with
# draft_generator._WRITING_LETTER_TYPES.
WRITING_LETTER_TYPES = ("referral", "discharge", "transfer", "ongoing_care")


def build_writing_prompt(difficulty: str, specialty: str, topic: str, objectives: Optional[str] = None, instructions: Optional[str] = None) -> Tuple[str, str]:
    schema = """{
  "title": "short scenario title, e.g. 'Discharge Letter - Pneumonia to Community Nurse'",
  "difficulty": "easy|medium|hard",
  "specialty": "medical specialty this case belongs to",
  "letter_type": "referral, discharge, transfer, or ongoing_care",
  "patient": {"name": "patient full name", "dob": "date of birth in dd/mm/yyyy format -- always provide this", "age": "OPTIONAL -- omit or leave blank; the system computes age from dob, do not calculate or invent a value", "gender": "patient gender, if relevant to the case", "address": "patient address, if given, else empty string"},
  "recipient": {"name": "recipient's full name", "role": "recipient's professional role, e.g. 'Head Nurse', 'Practice Nurse', 'Emergency Department Consultant on Duty'", "organization": "recipient's organization, e.g. a hospital, nursing home, or health centre", "address": "recipient's organization address"},
  "purpose": "one sentence stating why this letter is being written",
  "case_notes_structured": [
    {"section": "a case-note heading such as 'Patient Details', 'Medical History', 'Social Background', 'Presenting Complaint', 'Treatment Record', 'Medical Progress', 'Nursing Management', 'Current Concerns', or 'Plan' -- include only sections relevant to this case", "items": ["abbreviated, clinically dense note line, e.g. 'BP 130/80 (normal)'"]}
  ],
  "case_notes": "the SAME information as case_notes_structured, rendered as one text block with section labels and newlines between sections, exactly as OET case notes are printed",
  "task": "the writing task instruction in full: the recipient's name/role/organization/address and what letter to write, ending with 'The body of the letter should be approximately 180-200 words.'",
  "key_points": ["5 concise key points the letter must cover, used for scoring"],
  "distractor_notes": [
    {"text": "a case-note detail copied verbatim (or near-verbatim) from case_notes_structured/case_notes", "reason": "one sentence on why this specific detail is not needed for the requested letter"}
  ],
  "model_answer": "a complete example letter answering this task -- admin-only reference, never shown to learners"
}"""
    user = (
        f"Create an original OET Writing task. Randomly choose letter_type from exactly these four values -- "
        f"referral, discharge, transfer, ongoing_care -- rather than defaulting to the same one every time. "
        f"Write case_notes_structured (and the matching rendered case_notes) as real OET exams do: abbreviated, "
        f"clinically dense note fragments with realistic timestamps, not full prose. The task must instruct the "
        f"candidate to expand the notes into complete sentences, use letter format, and not use note form.\n\n"
        f"Always give patient.dob (date of birth, dd/mm/yyyy). Do NOT calculate or invent patient.age yourself -- "
        f"leave it blank, since the system derives age automatically from dob and the case's dates. State the "
        f"patient's DOB in the Patient Details section instead of a specific age, and do not mention a specific "
        f"age anywhere else (case_notes, task, or purpose) that could contradict the computed value.\n\n"
        f"Include rich clinical information in the case notes, including some genuinely less-relevant historical "
        f"detail where it would realistically appear in real notes (e.g. an earlier admission's imaging finding "
        f"that isn't needed for this specific letter). Do not manufacture obviously absurd or irrelevant "
        f"distractors, and do not label ordinary contextual information (social background, cognitive status, "
        f"safety concerns) as a distractor unless it is genuinely unneeded for this specific task -- most "
        f"contextual information should remain unflagged. In distractor_notes, list only case-note details that "
        f"are truly unnecessary for the specific letter requested: each entry's \"text\" must be copied verbatim "
        f"or near-verbatim from case_notes_structured/case_notes (never invented), and \"reason\" must explain why "
        f"that detail is not needed for this letter's purpose. Leave distractor_notes as an empty list if nothing "
        f"in the notes is genuinely unnecessary.\n\n"
        f"Never invent a phone number, email address, or other personal contact detail anywhere in the case "
        f"notes -- omit contact details entirely unless the task specifically requires the recipient's "
        f"professional/facility address, which belongs only in the 'recipient' object, not in the case notes.\n\n"
        f"Also write model_answer: a complete, admin-only reference letter answering this exact task, based ONLY "
        f"on case_notes/case_notes_structured, task, recipient, and key_points -- never invent a fact that isn't "
        f"in the case notes. Use correct letter format (salutation and closing appropriate to the recipient), "
        f"address the named recipient, state the purpose near the opening, prioritize covering every key point, "
        f"and omit the distractor_notes details entirely. Write in complete sentences -- never note form or "
        f"case-note shorthand. Target approximately 180-200 words for the letter body, in professional clinical "
        f"register. This is a reference for content reviewers, not a rigid answer key -- there is no need for "
        f"exact wording or exact sentence order.\n"
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


# Blog has no difficulty/specialty/part concept of its own (unlike every
# other module) -- the two params are accepted only so build_prompt()'s
# generic dispatch below can call every builder with the same signature;
# the frontend sends placeholder values for them and neither reaches the
# prompt text.
def build_blog_prompt(difficulty: str, specialty: str, topic: str, objectives: Optional[str] = None, instructions: Optional[str] = None) -> Tuple[str, str]:
    schema = """{
  "title": "a compelling, SEO-friendly blog post title",
  "excerpt": "a one-to-two sentence summary of the post, at most 200 characters -- used as the listing/meta description, not a copy of the opening paragraph",
  "body": "the full blog post body in Markdown -- use ## headings, short paragraphs, and bullet points where they aid readability"
}"""
    user = (
        f"Write an original blog article for nurses preparing for the OET (Occupational English Test). Write in "
        f"a practical, encouraging, beginner-friendly tone -- like a knowledgeable mentor, not an academic paper. "
        f"Aim for a substantial, complete article (roughly 800-1200 words in \"body\") that stands on its own, "
        f"not a teaser or outline.\n\n"
        f"Topic: {topic}\n"
    )
    if instructions:
        user += f"Additional instructions: {instructions}\n"
    user += (
        "\nDo not include a \"slug\" field -- the slug is assigned separately by the editor. "
        "Do not add meta-commentary or an \"AI-generated\" disclaimer inside the title, excerpt, or body -- "
        "write as if a human author wrote it. Do not wrap the JSON in a code fence.\n"
    )
    user += f"\nReturn ONLY this JSON:\n{schema}"
    return _SYSTEM_HEADER, user


BUILDERS: Dict[str, Callable[..., Tuple[str, str]]] = {
    "speaking": build_speaking_prompt,
    "reading": build_reading_prompt,
    "listening": build_listening_prompt,
    "writing": build_writing_prompt,
    "vocab": build_vocab_prompt,
    "grammar": build_grammar_prompt,
    "blog": build_blog_prompt,
}


def build_prompt(module: str, difficulty: str, specialty: str, topic: str, objectives: Optional[str] = None, instructions: Optional[str] = None, part: Optional[str] = None) -> Tuple[str, str]:
    builder = BUILDERS.get(module)
    if builder is None:
        raise ValueError(f"Unknown module: {module}")
    # Only build_reading_prompt/build_listening_prompt accept `part` -- every
    # other module builder's signature is unchanged, so `part` must not reach them.
    if module in ("reading", "listening"):
        return builder(difficulty, specialty, topic, objectives, instructions, part=part)
    return builder(difficulty, specialty, topic, objectives, instructions)
