"""Seed the Phase 1A MVP technique catalog into Supabase. Same idempotent
insert-if-title/slug-missing convention as seed_scenarios.py."""
from app.core.supabase import get_supabase

TECHNIQUES = [
    # ── READING ──
    {
        "module": "reading", "skill_tag": "skimming", "slug": "skimming",
        "name": "Skimming", "difficulty": "easy", "estimated_minutes": 4, "sort_order": 1,
        "learning_objective": "Identify a text's main purpose and topic without reading every word.",
        "description": "Read fast for the gist -- headings, topic sentences, first/last lines -- to grasp what a text is about before you need any detail.",
        "lesson_content": {
            "what": "Skimming is reading quickly to get the general idea of a text -- its topic, purpose, and overall structure -- without processing every sentence.",
            "why": "Part A of OET Reading is timed at roughly 1 word/second across 4 short texts. You cannot read every word and still finish -- skimming gets you oriented fast so you know where to look for detail.",
            "when": "Use it in the first 10-15 seconds with any new text: before answering 'which text' questions, and before switching to scanning for a specific fact.",
            "how": "Read the title/heading, the first and last sentence of each paragraph, and any bolded or capitalized words. Do not sound out every word -- let your eyes move fast and only slow down on words that signal the topic.",
            "common_mistakes": "Reading start-to-finish at normal speed (too slow); stopping to look up unfamiliar words (skimming tolerates not understanding everything); skimming so fast that the general topic doesn't register at all.",
            "example": "A text titled 'Managing Post-Operative Pain in Elderly Patients' -- skim the headings/first lines and you already know it's about pain management, elderly patients, post-surgery, before reading a single full paragraph.",
        },
    },
    {
        "module": "reading", "skill_tag": "scanning", "slug": "scanning",
        "name": "Scanning", "difficulty": "easy", "estimated_minutes": 4, "sort_order": 2,
        "learning_objective": "Locate a specific piece of information in a text quickly without reading for meaning.",
        "description": "Move your eyes over a text hunting for one specific word, number, or phrase -- not understanding, just finding.",
        "lesson_content": {
            "what": "Scanning is running your eyes over a text to find one specific piece of information -- a number, name, date, or exact phrase -- while ignoring everything else.",
            "why": "Many OET Reading Part B/C questions ask for one specific fact (a dosage, a contraindication, a named procedure). Reading the whole passage for these wastes time you don't have.",
            "when": "Use it once you know exactly what you're looking for -- after skimming has told you which text/section is relevant, or when a question names a specific term.",
            "how": "Take the exact word or a close synonym from the question and let your eyes sweep down the text looking only for that shape/word -- don't read surrounding text until you land on a match.",
            "common_mistakes": "Reading every word instead of hunting for the target (turns scanning into slow reading); scanning for the exact question wording when the text uses a paraphrase or synonym instead.",
            "example": "Question: 'What is the maximum recommended daily dose?' -- scan for the word 'dose' or a number pattern like 'mg' rather than reading the whole paragraph about the drug.",
        },
    },
    {
        "module": "reading", "skill_tag": "elimination", "slug": "elimination",
        "name": "Elimination", "difficulty": "medium", "estimated_minutes": 5, "sort_order": 3,
        "learning_objective": "Rule out clearly wrong multiple-choice options before selecting an answer.",
        "description": "Systematically cross out options the text contradicts or doesn't support, narrowing 4 choices down before picking.",
        "lesson_content": {
            "what": "Elimination is checking each multiple-choice option against the text and discarding the ones the text clearly contradicts or never mentions, instead of jumping straight to 'the one that sounds right'.",
            "why": "OET distractor options are deliberately written to sound plausible. Testing each option against the text, not against your general knowledge, is what actually separates the correct answer from a good distractor.",
            "when": "Use it on every multiple-choice question in Part B/C, especially when two options both sound reasonable.",
            "how": "For each option, find the exact sentence in the text it relates to. If the text says the opposite, or says nothing about it, cross it out. Stop as soon as one option is left standing, or verify the remaining ones against the text directly.",
            "common_mistakes": "Picking the first option that sounds plausible without checking the others; using outside medical knowledge instead of what the text actually says; not verifying the option that 'feels right' the same way you eliminated the others.",
            "example": "4 options about a drug's side effect -- 2 are never mentioned in the text (eliminate), 1 contradicts a sentence in the text (eliminate), 1 matches a sentence exactly (keep).",
        },
    },
    {
        "module": "reading", "skill_tag": "textual_verification", "slug": "textual-verification",
        "name": "Textual Verification", "difficulty": "medium", "estimated_minutes": 5, "sort_order": 4,
        "learning_objective": "Point to the exact sentence in the text that proves a chosen answer.",
        "description": "For any answer you pick, find and confirm the specific line of text that supports it -- proof, not a guess.",
        "lesson_content": {
            "what": "Textual verification is the habit of identifying the exact sentence or phrase in the passage that justifies your chosen answer, before committing to it.",
            "why": "It's the single check that catches wrong answers chosen from memory, assumption, or general knowledge instead of the actual text -- the most common source of avoidable errors in OET Reading.",
            "when": "Use it as the last step before selecting any answer, especially on questions that feel obvious.",
            "how": "Ask yourself 'which sentence proves this?' If you can't point to one, you likely haven't found the right answer yet -- go back and look, don't guess.",
            "common_mistakes": "Choosing an answer because it sounds medically correct rather than because the text states it; being unable to locate supporting text but selecting the answer anyway.",
            "example": "Answer chosen: 'Patients should fast for 6 hours before the procedure.' Verification: locate the sentence '...patients must not eat or drink for six hours prior to surgery' -- that sentence is the proof.",
        },
    },
    # ── LISTENING ──
    {
        "module": "listening", "skill_tag": "pre_listening", "slug": "pre-listening",
        "name": "Pre-listening Preparation", "difficulty": "easy", "estimated_minutes": 3, "sort_order": 1,
        "learning_objective": "Use the time before audio starts to prime what to listen for.",
        "description": "Read the questions and notes template before the audio plays so you already know what information you're hunting for.",
        "lesson_content": {
            "what": "Pre-listening preparation is reading the questions, gaps, or note headings before the audio begins, so you go in already knowing what to listen for.",
            "why": "Audio plays once, in real time, with no pausing. If you're still reading the question when the relevant sentence is spoken, you miss it permanently.",
            "when": "Use every second of the pause given before each audio section starts.",
            "how": "Read every question/gap in the section, underline key nouns, and predict roughly what kind of answer fits (a number, a symptom name, a time) before the audio starts.",
            "common_mistakes": "Starting to read only after the audio has already started; reading passively without noting what type of information each gap needs.",
            "example": "Gap reads 'Patient's temperature on admission: ___°C' -- before audio starts you already know: listen for a number followed by 'degrees' near the word 'admission' or 'temperature'.",
        },
    },
    {
        "module": "listening", "skill_tag": "keyword_prediction", "slug": "keyword-prediction",
        "name": "Keyword Prediction", "difficulty": "medium", "estimated_minutes": 4, "sort_order": 2,
        "learning_objective": "Predict the specific words likely to appear around each answer before hearing them.",
        "description": "From the question wording, guess the vocabulary the speaker will actually use, since the audio rarely repeats the question word-for-word.",
        "lesson_content": {
            "what": "Keyword prediction is generating likely vocabulary -- both the exact words and their probable synonyms -- that will surround the answer in the audio, based on the written question.",
            "why": "OET Listening audio is natural speech, not a script of the question paper -- the same idea is often expressed in different words. Predicting the vocabulary helps you catch the answer even when the wording shifts.",
            "when": "During pre-listening, immediately after reading each question/gap.",
            "how": "For each gap, list 1-2 words you expect to hear (from the question itself) and 1-2 likely synonyms or related phrases a speaker might use instead.",
            "common_mistakes": "Predicting only the exact question wording and missing the answer when a synonym is used instead; over-predicting so many words that focus is lost.",
            "example": "Question asks about 'known allergies' -- predict you might hear 'allergies', but also 'allergic to', 'reacts badly to', or 'sensitivity'.",
        },
    },
    {
        "module": "listening", "skill_tag": "signpost_tracking", "slug": "signpost-tracking",
        "name": "Signpost Tracking", "difficulty": "medium", "estimated_minutes": 5, "sort_order": 3,
        "learning_objective": "Notice verbal cues that signal a topic change or a key point is coming.",
        "description": "Catch phrases like 'however', 'the main issue is', or 'moving on to' that flag structure shifts and important information.",
        "lesson_content": {
            "what": "Signposts are words/phrases speakers use to mark structure -- topic changes, contrasts, emphasis, or sequence (e.g. 'however', 'the key thing is', 'first... then...').",
            "why": "They tell you when to shift attention to the next question/gap, and often flag exactly where an important, testable point is about to be said.",
            "when": "Continuously while listening, especially in longer Part B/C consultations and presentations.",
            "how": "Keep a mental list of common signposts (contrast: 'however', 'but', 'on the other hand'; emphasis: 'importantly', 'the main issue'; sequence: 'first', 'next', 'finally') and treat them as a cue to focus harder on what follows.",
            "common_mistakes": "Treating all speech as equally important instead of listening for structural cues; missing a topic-change signpost and staying focused on the previous (already-answered) point.",
            "example": "'...so that covers his medication history. Now, in terms of his diet...' -- 'Now, in terms of' signposts a topic shift; anything before it is done, listen fresh from here.",
        },
    },
    {
        "module": "listening", "skill_tag": "paraphrase_synonym_recognition", "slug": "paraphrase-synonym-recognition",
        "name": "Paraphrase & Synonym Recognition", "difficulty": "medium", "estimated_minutes": 5, "sort_order": 4,
        "learning_objective": "Recognize when spoken audio expresses a question's idea using different words.",
        "description": "Match the meaning, not the exact wording, between what's asked and what's said.",
        "lesson_content": {
            "what": "Recognizing when the audio expresses the same idea as a question or gap, but using different vocabulary or sentence structure (a synonym or a paraphrase) rather than the exact words.",
            "why": "Test writers deliberately avoid repeating question wording verbatim in the audio -- listening for exact-word matches alone will make you miss correct answers.",
            "when": "Whenever a predicted keyword doesn't appear as expected -- check for a same-meaning alternative before assuming you've missed the answer.",
            "how": "Practice pairing common OET vocabulary with its everyday spoken equivalent (e.g. 'administer medication' / 'give the medicine'; 'adverse reaction' / 'bad response'), and listen for meaning, not word-shape.",
            "common_mistakes": "Waiting to hear the exact printed word and dismissing a paraphrased mention as irrelevant; not building a mental bank of clinical-term-to-plain-speech pairs in advance.",
            "example": "Question: 'reason for referral' -- speaker says 'that's why I'm sending him to see you' -- same idea, completely different words.",
        },
    },
    # ── WRITING ──
    {
        "module": "writing", "skill_tag": "audience_purpose_identification", "slug": "audience-purpose-identification",
        "name": "Audience & Purpose Identification", "difficulty": "easy", "estimated_minutes": 4, "sort_order": 1,
        "learning_objective": "Identify who the letter is for and what it needs to achieve before writing a word.",
        "description": "Establish the reader (GP, specialist, discharge coordinator...) and the goal (referral, discharge summary, update) to shape tone and content correctly.",
        "lesson_content": {
            "what": "Identifying the specific reader of the letter (their role, and how much clinical background they already have) and the letter's single purpose (e.g. requesting a review, informing of discharge, referring for a procedure).",
            "why": "Audience and purpose determine what to include, what tone to use, and how much explanation is needed -- a letter to a specialist reads very differently from one to a patient's family member.",
            "when": "Before drafting -- as the very first step after reading the case notes.",
            "how": "Underline who the letter is addressed to in the task instructions and identify their professional role. State the purpose explicitly in your own head in one sentence ('I am writing to request X because Y') before writing the opening line.",
            "common_mistakes": "Writing generically without adjusting tone/detail to the specific reader; burying the purpose instead of stating it clearly in the opening; explaining basic clinical terms to a fellow clinician who doesn't need them.",
            "example": "Task: write to a physiotherapist about a post-stroke patient. Audience = a fellow clinician with relevant expertise (skip basic explanations of stroke). Purpose = referral for rehabilitation.",
        },
    },
    {
        "module": "writing", "skill_tag": "case_note_selection", "slug": "case-note-selection",
        "name": "Case-Note Selection", "difficulty": "medium", "estimated_minutes": 6, "sort_order": 2,
        "learning_objective": "Choose which case notes are relevant to the stated purpose and leave out the rest.",
        "description": "Not every case note belongs in the letter -- select only what serves the referral's purpose.",
        "lesson_content": {
            "what": "Deciding which pieces of information from the full case notes are relevant to the letter's specific purpose, and deliberately excluding notes that aren't.",
            "why": "OET Writing case notes always contain more detail than the letter needs. Including irrelevant information dilutes the letter and is penalized under the OET 'Content' criterion.",
            "when": "After identifying audience and purpose, before drafting -- go through the case notes and mark each note as relevant or not.",
            "how": "For each note, ask 'does the reader need this to achieve the letter's purpose?' If the answer is no, leave it out, even if it's clinically interesting.",
            "common_mistakes": "Including every case note 'just in case'; omitting a note that is directly relevant to the purpose because it seemed minor.",
            "example": "Referral for physiotherapy: the patient's unrelated childhood tonsillectomy is not relevant and should be omitted; their current mobility limitations are relevant and must be included.",
        },
    },
    {
        "module": "writing", "skill_tag": "sentence_transformation_synthesis", "slug": "sentence-transformation-synthesis",
        "name": "Sentence Transformation & Synthesis", "difficulty": "hard", "estimated_minutes": 6, "sort_order": 3,
        "learning_objective": "Turn informal, fragmented case notes into a single professional clinical sentence.",
        "description": "Combine and reword shorthand notes into fluent, professional prose suitable for a clinical letter.",
        "lesson_content": {
            "what": "Converting brief, informal case-note fragments (often abbreviated, list-like) into complete, professional, grammatically correct sentences -- sometimes combining several notes into one synthesized sentence.",
            "why": "Case notes are written in clinical shorthand for internal use; a referral letter must read as fluent professional prose. This is directly assessed under OET's 'Language' and 'Style & Tone' criteria.",
            "when": "During drafting, for every case note you've selected as relevant.",
            "how": "Expand abbreviations, add subjects/verbs the shorthand dropped, and where two related notes serve the same point, merge them into one well-structured sentence rather than two short ones.",
            "common_mistakes": "Copying case-note fragments directly into the letter unchanged; writing one short, choppy sentence per note instead of synthesizing related notes together.",
            "example": "Notes: 'BP 160/95, HR 92, c/o headache x3/7' -> 'The patient has been experiencing headaches for three days, with an elevated blood pressure of 160/95 mmHg and a heart rate of 92 beats per minute.'",
        },
    },
    # ── SPEAKING ──
    {
        "module": "speaking", "skill_tag": "setting_context", "slug": "setting-context",
        "name": "Setting Context", "difficulty": "easy", "estimated_minutes": 3, "sort_order": 1,
        "learning_objective": "Open a patient interaction by clearly establishing who you are and why you're there.",
        "description": "Introduce yourself, confirm the patient's identity, and state the purpose of the conversation before diving into questions.",
        "lesson_content": {
            "what": "Opening a clinical conversation by introducing yourself, confirming who you're speaking to, and stating why you're there -- before asking any clinical questions.",
            "why": "Patients who don't know who they're speaking to or why are more anxious and less cooperative; OET's roleplay explicitly assesses opening rapport-building under 'Relationship building'.",
            "when": "At the very start of every speaking roleplay, before any task-specific questions.",
            "how": "In one or two sentences: give your name/role, confirm the patient's name, and briefly state the purpose ('I'm one of the nurses looking after you today, I'd just like to ask a few questions about how you're feeling').",
            "common_mistakes": "Launching straight into clinical questions with no introduction; a rushed, robotic introduction that doesn't sound natural.",
            "example": "'Hello Mr. Kumar, I'm one of the nurses on the ward today. I'd like to ask you a few questions about the pain you've been having, is that alright?'",
        },
    },
    {
        "module": "speaking", "skill_tag": "empathy_validation", "slug": "empathy-validation",
        "name": "Empathy & Validation", "difficulty": "medium", "estimated_minutes": 5, "sort_order": 2,
        "learning_objective": "Acknowledge a patient's emotion explicitly before moving on with the clinical task.",
        "description": "Name and validate what the patient is feeling -- fear, frustration, confusion -- rather than only addressing the clinical facts.",
        "lesson_content": {
            "what": "Explicitly naming and acknowledging a patient's emotional state (e.g. 'that sounds really frightening') before continuing with clinical questions or explanations.",
            "why": "Empathy is one of OET Speaking's directly scored criteria. Patients who feel unheard disengage, and ignoring an emotional cue reads as poor communication even if the clinical content is correct.",
            "when": "Whenever a patient expresses worry, pain, frustration, or confusion -- respond to the emotion before continuing the task.",
            "how": "Use a short acknowledging phrase that names the feeling ('I can see this is worrying you' / 'that must have been really difficult') before moving to information-gathering or advice.",
            "common_mistakes": "Moving straight past an emotional statement to the next clinical question; generic reassurance ('don't worry') instead of specific acknowledgement of what was said.",
            "example": "Patient: 'I'm scared this means the cancer is back.' Nurse: 'I can hear how frightening that thought is for you. Let's talk through what today's tests actually showed.'",
        },
    },
    {
        "module": "speaking", "skill_tag": "chunking_signposting", "slug": "chunking-signposting",
        "name": "Chunking & Signposting", "difficulty": "medium", "estimated_minutes": 5, "sort_order": 3,
        "learning_objective": "Break information into small spoken chunks and signal what's coming next.",
        "description": "Deliver information in short pieces with verbal signposts ('firstly...', 'the next thing is...') instead of one long unbroken explanation.",
        "lesson_content": {
            "what": "Chunking is delivering information in short, digestible spoken segments rather than one long unbroken explanation. Signposting is announcing what each chunk will cover before you say it (e.g. 'firstly...', 'next, I want to explain...').",
            "why": "Patients cannot re-read spoken explanations. Long unbroken delivery is hard to follow and is penalized under OET's 'Providing structure' criterion; chunking with signposts keeps the patient oriented.",
            "when": "Whenever explaining a multi-part process -- a procedure, a set of instructions, test results with next steps.",
            "how": "Break the explanation into 2-4 logical parts. Before each part, say a short signpost phrase, then deliver only that chunk, pausing to check understanding before moving to the next.",
            "common_mistakes": "Explaining everything in one continuous stream with no pauses or verbal markers; signposting without actually pausing/chunking the content that follows.",
            "example": "'There are three things I want to cover today. Firstly, what the test showed. Secondly, what it means for you. And finally, what happens next.' -- then deliver each part separately.",
        },
    },
]


def seed_techniques():
    supabase = get_supabase()
    count = 0
    for technique in TECHNIQUES:
        existing = supabase.table("techniques").select("id").eq("slug", technique["slug"]).execute()
        if existing.data:
            print(f"  [SKIP] Exists: {technique['name']}")
            continue
        supabase.table("techniques").insert(technique).execute()
        count += 1
        print(f"  [OK] Added: {technique['name']}")
    print(f"\n[OK] Seeded {count} techniques to Supabase")
    return count


if __name__ == "__main__":
    seed_techniques()
