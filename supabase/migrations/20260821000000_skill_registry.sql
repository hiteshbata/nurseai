-- E2.4.1: canonical Skill Registry / Taxonomy foundation.
--
-- Purely additive: one new table, no ALTER of any existing table, no data
-- mutation outside this table's own creation/seeding. The legacy colon-tag
-- strings skill_graph.py / technique_progress.py write into
-- user_skill_stats / skill_observations / listening_mistake_events /
-- techniques.skill_tag are completely untouched -- this table is a parallel
-- catalog, not a replacement. See backend/app/services/skill_registry.py
-- (the single source of truth this seed data is generated from) and
-- backend/app/services/skill_registry_reconciliation.py (read-only tag <->
-- code comparison, not wired into any runtime path).
--
-- parent_skill_id exists for E2.4.3's prerequisite graph; deliberately left
-- NULL for every row here -- populating it is out of scope for this phase.

CREATE TABLE IF NOT EXISTS public.skills (
    skill_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    module text NOT NULL CHECK (module IN ('reading', 'listening', 'writing', 'speaking')),
    kind text NOT NULL CHECK (kind IN ('part', 'comprehension_skill', 'criterion', 'technique')),
    description text,
    active boolean NOT NULL DEFAULT true,
    parent_skill_id uuid REFERENCES public.skills(skill_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS skills_module_kind_idx ON public.skills (module, kind);
CREATE INDEX IF NOT EXISTS skills_parent_skill_id_idx ON public.skills (parent_skill_id);

-- Content table, same convention as techniques/micro_practices (RLS
-- enabled, zero policies, service-role only -- served through the backend
-- API, never a direct client-side Supabase read).
ALTER TABLE public.skills ENABLE ROW LEVEL SECURITY;

INSERT INTO public.skills (code, name, module, kind, description) VALUES
    ('reading.part.a', 'Reading Part A', 'reading', 'part', NULL),
    ('reading.part.b', 'Reading Part B', 'reading', 'part', NULL),
    ('reading.part.c', 'Reading Part C', 'reading', 'part', NULL),
    ('listening.part.a', 'Listening Part A', 'listening', 'part', NULL),
    ('listening.part.b', 'Listening Part B', 'listening', 'part', NULL),
    ('listening.part.c', 'Listening Part C', 'listening', 'part', NULL),
    ('reading.skill.scanning', 'Scanning', 'reading', 'comprehension_skill', 'Scanning (finding which text has the info)'),
    ('reading.skill.detail', 'Detail', 'reading', 'comprehension_skill', 'Detail (specific stated facts)'),
    ('reading.skill.inference', 'Inference', 'reading', 'comprehension_skill', 'Inference (reading between the lines)'),
    ('reading.skill.main_idea', 'Main Idea', 'reading', 'comprehension_skill', 'Main idea / purpose'),
    ('reading.skill.vocabulary', 'Vocabulary', 'reading', 'comprehension_skill', 'Vocabulary & word meaning'),
    ('reading.skill.writer_view', 'Writer View', 'reading', 'comprehension_skill', 'Writer''s view & attitude'),
    ('speaking.criterion.clinical_communication', 'Clinical Communication', 'speaking', 'criterion', 'Did the nurse gather information effectively, explain clearly, and respond to patient cues?'),
    ('speaking.criterion.linguistic_delivery', 'Linguistic Delivery', 'speaking', 'criterion', 'Was speech clear, fluent, and at an appropriate level for the patient?'),
    ('speaking.criterion.relationship_building', 'Relationship Building', 'speaking', 'criterion', 'Did the nurse show empathy, respect, and build rapport with the patient?'),
    ('speaking.criterion.empathy', 'Empathy', 'speaking', 'criterion', 'Acknowledges the patient''s emotional state, validates concerns, uses supportive language alongside clinical information.'),
    ('speaking.criterion.patient_perspective', 'Patient Perspective', 'speaking', 'criterion', 'Did nurse actively listen and respond to patient cues, concerns and questions throughout?'),
    ('speaking.criterion.providing_structure', 'Providing Structure', 'speaking', 'criterion', 'Did conversation follow OET sequence: introduce, enquire, explain, advise?'),
    ('speaking.criterion.information_gathering', 'Information Gathering', 'speaking', 'criterion', 'Did nurse use open questions first then closed, and check understanding?'),
    ('speaking.criterion.information_giving', 'Information Giving', 'speaking', 'criterion', 'Was advice clear, concise, jargon-free, given as suggestions not orders?'),
    ('speaking.criterion.intelligibility', 'Intelligibility', 'speaking', 'criterion', 'Was speech clear? Correct word stress, intonation, rhythm?'),
    ('speaking.criterion.fluency', 'Fluency', 'speaking', 'criterion', 'Smooth pace? Natural pauses? Minimal filler words?'),
    ('speaking.criterion.appropriateness_of_language', 'Appropriateness Of Language', 'speaking', 'criterion', 'Suitable register for patient? Medical terms explained in plain language?'),
    ('speaking.criterion.grammar', 'Grammar', 'speaking', 'criterion', 'Range of grammar structures used accurately? Varied vocabulary and idioms?'),
    ('writing.criterion.purpose', 'Purpose', 'writing', 'criterion', NULL),
    ('writing.criterion.content', 'Content', 'writing', 'criterion', NULL),
    ('writing.criterion.conciseness', 'Conciseness', 'writing', 'criterion', NULL),
    ('writing.criterion.genre_style', 'Genre Style', 'writing', 'criterion', NULL),
    ('writing.criterion.organization', 'Organization', 'writing', 'criterion', NULL),
    ('writing.criterion.language', 'Language', 'writing', 'criterion', NULL),
    ('technique.skimming', 'Skimming', 'reading', 'technique', 'Read fast for the gist -- headings, topic sentences, first/last lines -- to grasp what a text is about before you need any detail.'),
    ('technique.scanning', 'Scanning', 'reading', 'technique', 'Move your eyes over a text hunting for one specific word, number, or phrase -- not understanding, just finding.'),
    ('technique.elimination', 'Elimination', 'reading', 'technique', 'Systematically cross out options the text contradicts or doesn''t support, narrowing 4 choices down before picking.'),
    ('technique.textual_verification', 'Textual Verification', 'reading', 'technique', 'For any answer you pick, find and confirm the specific line of text that supports it -- proof, not a guess.'),
    ('technique.pre_listening', 'Pre-listening Preparation', 'listening', 'technique', 'Read the questions and notes template before the audio plays so you already know what information you''re hunting for.'),
    ('technique.keyword_prediction', 'Keyword Prediction', 'listening', 'technique', 'From the question wording, guess the vocabulary the speaker will actually use, since the audio rarely repeats the question word-for-word.'),
    ('technique.signpost_tracking', 'Signpost Tracking', 'listening', 'technique', 'Catch phrases like ''however'', ''the main issue is'', or ''moving on to'' that flag structure shifts and important information.'),
    ('technique.paraphrase_synonym_recognition', 'Paraphrase & Synonym Recognition', 'listening', 'technique', 'Match the meaning, not the exact wording, between what''s asked and what''s said.'),
    ('technique.audience_purpose_identification', 'Audience & Purpose Identification', 'writing', 'technique', 'Establish the reader (GP, specialist, discharge coordinator...) and the goal (referral, discharge summary, update) to shape tone and content correctly.'),
    ('technique.case_note_selection', 'Case-Note Selection', 'writing', 'technique', 'Not every case note belongs in the letter -- select only what serves the referral''s purpose.'),
    ('technique.sentence_transformation_synthesis', 'Sentence Transformation & Synthesis', 'writing', 'technique', 'Combine and reword shorthand notes into fluent, professional prose suitable for a clinical letter.'),
    ('technique.setting_context', 'Setting Context', 'speaking', 'technique', 'Introduce yourself, confirm the patient''s identity, and state the purpose of the conversation before diving into questions.'),
    ('technique.empathy_validation', 'Empathy & Validation', 'speaking', 'technique', 'Name and validate what the patient is feeling -- fear, frustration, confusion -- rather than only addressing the clinical facts.'),
    ('technique.chunking_signposting', 'Chunking & Signposting', 'speaking', 'technique', 'Deliver information in short pieces with verbal signposts (''firstly...'', ''the next thing is...'') instead of one long unbroken explanation.')
ON CONFLICT (code) DO NOTHING;
