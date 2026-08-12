"""Seed real micro-practice exercise content. Phase C seeded one rule_based
exercise per technique (Reading's 4 + Listening's 4 + Writing's 3 + Speaking's
3, all still present below unchanged). Phase D adds a small representative
slice of *additional* practices on top of that -- proving the architecture
genuinely supports multiple practices per technique, difficulty/stage, and
static explanation/mistake-type content -- without rewriting all 14 techniques
(see docs, Phase D scope limits). Same idempotent insert-if-missing
convention as seed_techniques.py, keyed on (technique_id, title) since
micro_practices has no unique slug column.

All practices are deliberately rule_based (exact-match against `options`, via
technique_grading.grade_rule_based) -- no AI-grading dependency for this
slice. Original short passages/case notes, not real OET paper content.
Listening has no audio pipeline yet, so each exercise presents its audio
content as a written transcript excerpt in `content.passage`. Writing
exercises present case notes / task briefs the same way, in `content.passage`
-- same passage/question/options shape the frontend already renders. Speaking
exercises are small controlled choose-the-best-response drills (not full
roleplays) using the same passage/question/options shape -- `content.passage`
sets the scenario, `content.question` asks which spoken response is best.

`difficulty`/`stage`/`sort_order` are omitted on the original 14 entries
(they take the column defaults: beginner/guided/0) -- only the new Phase D
entries set them explicitly, so they always sort after the originals within
their technique."""
from app.core.supabase import get_supabase

MICRO_PRACTICES = [
    {
        "technique_skill_tag": "skimming",
        "title": "Skim for the Main Idea",
        "instructions": "You have about 20 seconds. Skim the passage below -- don't read every word -- then choose the title that best matches it.",
        "content": {
            "passage": "Patients recovering from hip replacement surgery are encouraged to begin gentle mobility exercises within 24 hours of the procedure. Early movement reduces the risk of blood clots and helps maintain joint flexibility. Physiotherapists typically guide patients through a graded program, starting with bed exercises before progressing to walking with assistive devices. Pain management is coordinated closely with the mobility plan, since untreated pain is one of the most common reasons patients avoid moving after surgery.",
            "options": [
                "Early Mobility After Hip Replacement Surgery",
                "The History of Hip Replacement Techniques",
                "Managing Chronic Pain in Elderly Patients",
                "Choosing the Right Assistive Walking Device",
            ],
        },
        "expected_response": {"correct_answer": "Early Mobility After Hip Replacement Surgery"},
        "scoring_type": "rule_based",
    },
    {
        "technique_skill_tag": "scanning",
        "title": "Scan for the Specific Fact",
        "instructions": "Don't read the whole passage top to bottom -- scan for the exact answer to the question below.",
        "content": {
            "passage": "Amoxicillin is a widely used antibiotic for treating bacterial infections such as ear infections, pneumonia, and urinary tract infections. For adults, the typical oral dose is 500mg every 8 hours, though this may be adjusted based on the severity of the infection and kidney function. Patients should be advised to complete the full course even if symptoms improve early, and to report any signs of an allergic reaction, such as rash or difficulty breathing, immediately.",
            "question": "What is the typical adult oral dose of amoxicillin?",
            "options": ["250mg every 6 hours", "500mg every 8 hours", "1000mg every 12 hours", "500mg every 4 hours"],
        },
        "expected_response": {"correct_answer": "500mg every 8 hours"},
        "scoring_type": "rule_based",
    },
    {
        "technique_skill_tag": "elimination",
        "title": "Eliminate the Distractors",
        "instructions": "Read the passage, then eliminate the options the text contradicts or never mentions before choosing your answer.",
        "content": {
            "passage": "Patients with type 2 diabetes are advised to monitor their blood glucose regularly, particularly before meals and at bedtime. Diet and exercise remain the first line of management, with medication introduced when lifestyle changes alone do not achieve target glucose levels. Metformin is typically the first medication prescribed, as it has a well-established safety profile and rarely causes hypoglycemia on its own.",
            "question": "According to the passage, what is typically the FIRST medication prescribed for type 2 diabetes?",
            "options": ["Insulin", "Metformin", "Sulfonylureas", "Metformin is never prescribed first"],
        },
        "expected_response": {"correct_answer": "Metformin"},
        "scoring_type": "rule_based",
    },
    {
        "technique_skill_tag": "textual_verification",
        "title": "Find the Proof",
        "instructions": "A claim is given below. Which sentence from the passage actually proves it? Don't pick from memory -- point to the text.",
        "content": {
            "passage": "Before any surgical procedure, patients are required to fast for a minimum period to reduce the risk of aspiration during anesthesia. Most guidelines recommend no solid food for at least 6 hours prior to surgery, and clear fluids may be permitted up to 2 hours before. Patients who do not follow fasting instructions may have their surgery postponed for safety reasons.",
            "claim": "Patients must not eat solid food for at least 6 hours before surgery.",
            "options": [
                "Before any surgical procedure, patients are required to fast for a minimum period to reduce the risk of aspiration during anesthesia.",
                "Most guidelines recommend no solid food for at least 6 hours prior to surgery, and clear fluids may be permitted up to 2 hours before.",
                "Patients who do not follow fasting instructions may have their surgery postponed for safety reasons.",
            ],
        },
        "expected_response": {"correct_answer": "Most guidelines recommend no solid food for at least 6 hours prior to surgery, and clear fluids may be permitted up to 2 hours before."},
        "scoring_type": "rule_based",
    },
    {
        "technique_skill_tag": "pre_listening",
        "title": "Prepare Before You Listen",
        "instructions": "OET gives you time to read the question before the audio starts. Use it. Read the gap below and decide what TYPE of information you need to listen for -- don't try to guess the actual answer yet.",
        "content": {
            "passage": "You are about to hear a conversation between a practice nurse and a patient who has come in for a medication review. Here is the note-completion gap you'll need to fill in while listening:\n\nPatient reports missing doses because of: ___________",
            "question": "Before the audio starts, what should you be listening for?",
            "options": [
                "A reason or cause explaining why the patient has been missing doses",
                "The exact brand name of the patient's medication",
                "The patient's next appointment date",
                "The nurse's full name",
            ],
        },
        "expected_response": {"correct_answer": "A reason or cause explaining why the patient has been missing doses"},
        "scoring_type": "rule_based",
    },
    {
        "technique_skill_tag": "keyword_prediction",
        "title": "Predict the Keywords",
        "instructions": "Before listening, predict the words and likely synonyms that will surround the answer. Read the gap below, then choose the best keyword prediction.",
        "content": {
            "passage": "You are about to hear a nurse taking a patient's history. Here is the note-completion gap:\n\nKnown allergies: ___________",
            "question": "Which is the best keyword prediction to prepare for this gap?",
            "options": [
                "Listen for 'allergies', and also related words like 'allergic to', 'reacts badly to', or 'sensitivity'",
                "Listen only for the exact word 'allergies' -- nothing else will be relevant",
                "Listen for the patient's full medical history from birth",
                "Listen for the name of the patient's doctor",
            ],
        },
        "expected_response": {"correct_answer": "Listen for 'allergies', and also related words like 'allergic to', 'reacts badly to', or 'sensitivity'"},
        "scoring_type": "rule_based",
    },
    {
        "technique_skill_tag": "signpost_tracking",
        "title": "Follow the Signpost",
        "instructions": "Speakers use signpost phrases to mark a change in topic or structure. Read the transcript excerpt below, then identify what the signpost tells you.",
        "content": {
            "passage": "TRANSCRIPT EXCERPT -- Practice Nurse to Patient:\n\n\"...so that covers your medication history. Now, moving on to your diet -- can you tell me what a typical day's meals looks like for you?\"",
            "question": "What does the phrase \"Now, moving on to\" signal here?",
            "options": [
                "The speaker is shifting to a new topic (diet) -- the medication-history questions are finished",
                "The speaker is about to contradict what was just said",
                "The speaker is summarising everything said so far",
                "The speaker is asking the patient to repeat their last answer",
            ],
        },
        "expected_response": {"correct_answer": "The speaker is shifting to a new topic (diet) -- the medication-history questions are finished"},
        "scoring_type": "rule_based",
    },
    {
        "technique_skill_tag": "paraphrase_synonym_recognition",
        "title": "Match the Meaning, Not the Words",
        "instructions": "The question paper rarely repeats the audio word-for-word. Read the transcript excerpt below, then choose the part that answers the question -- even though the wording is different.",
        "content": {
            "passage": "TRANSCRIPT EXCERPT -- Doctor to Colleague:\n\n\"I'm sending him over to you because his blood sugar readings have been all over the place these past few weeks.\"",
            "question": "The question paper asks: \"What is the reason for referral?\" Which part of the transcript answers this?",
            "options": [
                "\"...because his blood sugar readings have been all over the place\" -- this is the reason for referral, just worded differently",
                "\"these past few weeks\" -- this states the referral date",
                "\"I'm sending him over to you\" alone, without a reason",
                "The transcript does not mention a reason for referral",
            ],
        },
        "expected_response": {"correct_answer": "\"...because his blood sugar readings have been all over the place\" -- this is the reason for referral, just worded differently"},
        "scoring_type": "rule_based",
    },
    {
        "technique_skill_tag": "audience_purpose_identification",
        "title": "Who Is This Letter For?",
        "instructions": "Read the task brief below, then identify the correct audience and purpose -- don't pick the first option that sounds plausible.",
        "content": {
            "passage": "You are the ward nurse for Mr. James Cole, 68, who has been treated for a chest infection and is ready for discharge. His GP, Dr. Patel, needs to take over his ongoing care and monitor his recovery. Write a letter to Dr. Patel.",
            "question": "Who is the audience, and what is the purpose of this letter?",
            "options": [
                "A GP colleague (Dr. Patel), for the purpose of handing over ongoing care and monitoring after discharge",
                "The patient's family, to reassure them the treatment succeeded",
                "A hospital pharmacist, to request a change in medication dosage",
                "A specialist consultant, to request an urgent second opinion",
            ],
        },
        "expected_response": {"correct_answer": "A GP colleague (Dr. Patel), for the purpose of handing over ongoing care and monitoring after discharge"},
        "scoring_type": "rule_based",
    },
    {
        "technique_skill_tag": "case_note_selection",
        "title": "Which Note Belongs in the Letter?",
        "instructions": "You're writing a referral letter for the stated purpose below. Read the case notes, then decide which one does NOT belong in the letter.",
        "content": {
            "passage": "Case notes for Mrs. Alina Petrov, 74. You are writing a referral letter to a physiotherapist for ongoing rehabilitation of her post-stroke mobility.\n\nCase notes:\n- Right-sided weakness following stroke 3 weeks ago\n- Currently mobilising with a frame, requires supervision\n- Long-standing seasonal pollen allergy, well controlled\n- Referred for gait training and strength exercises",
            "question": "Which case note is NOT relevant to this physiotherapy referral and should be left out of the letter?",
            "options": [
                "Right-sided weakness following stroke 3 weeks ago",
                "Currently mobilising with a frame, requires supervision",
                "Long-standing seasonal pollen allergy, well controlled",
                "Referred for gait training and strength exercises",
            ],
        },
        "expected_response": {"correct_answer": "Long-standing seasonal pollen allergy, well controlled"},
        "scoring_type": "rule_based",
    },
    {
        "technique_skill_tag": "sentence_transformation_synthesis",
        "title": "Turn Notes Into Professional Prose",
        "instructions": "Read the raw case notes below, then choose the sentence that best combines them into fluent, professional clinical prose -- without adding or dropping information.",
        "content": {
            "passage": "Raw case notes:\nSOB on exertion\nAnkle swelling noted\nPt reports worsening over 2 weeks",
            "question": "Which sentence best transforms these case notes for a clinical letter?",
            "options": [
                "The patient has been experiencing shortness of breath on exertion and ankle swelling, both of which have been worsening over the past two weeks.",
                "SOB on exertion, ankle swelling noted, pt reports worsening over 2 weeks.",
                "The patient has shortness of breath.",
                "The patient has been diagnosed with heart failure and started on diuretics two weeks ago.",
            ],
        },
        "expected_response": {"correct_answer": "The patient has been experiencing shortness of breath on exertion and ankle swelling, both of which have been worsening over the past two weeks."},
        "scoring_type": "rule_based",
    },
    # ── SPEAKING ──
    {
        "technique_skill_tag": "setting_context",
        "title": "Open the Conversation Professionally",
        "instructions": "You're about to start a consultation with a patient you haven't met before. Choose the best opening before asking any clinical questions.",
        "content": {
            "passage": "You are a nurse in a general practice clinic. Mrs. Chen, 58, has just been called in for a scheduled blood pressure review. You have never met her before. You open the door and greet her.",
            "question": "Which opening is the best way to start this interaction?",
            "options": [
                "Hello, are you Mrs. Chen? I'm one of the nurses here -- I'll be doing your blood pressure review today. Is that alright with you?",
                "So, have you been taking your blood pressure tablets every day?",
                "Hey there! Come on in, take a seat.",
                "Right, let's get started then.",
            ],
        },
        "expected_response": {"correct_answer": "Hello, are you Mrs. Chen? I'm one of the nurses here -- I'll be doing your blood pressure review today. Is that alright with you?"},
        "scoring_type": "rule_based",
    },
    {
        "technique_skill_tag": "empathy_validation",
        "title": "Respond to the Patient's Worry",
        "instructions": "A patient shares a concern. Choose the response that best acknowledges their feelings before moving forward.",
        "content": {
            "passage": "TRANSCRIPT EXCERPT -- Patient to Nurse:\n\n\"I've been waiting three weeks for these results and I keep thinking the worst. I barely slept last night.\"",
            "question": "What is the most patient-centred way to respond?",
            "options": [
                "That sounds like such an anxious few weeks for you, waiting and not knowing. Let's go through the results together now.",
                "Try not to worry, I'm sure it's nothing.",
                "Okay, well let's talk about your medication instead.",
                "Your results show a normal white cell count and mild inflammation markers.",
            ],
        },
        "expected_response": {"correct_answer": "That sounds like such an anxious few weeks for you, waiting and not knowing. Let's go through the results together now."},
        "scoring_type": "rule_based",
    },
    {
        "technique_skill_tag": "chunking_signposting",
        "title": "Organise the Explanation Into Clear Chunks",
        "instructions": "You need to explain a multi-part discharge plan to a patient. Choose the best way to structure what you say.",
        "content": {
            "passage": "You are discharging Mr. Osei after a minor surgical procedure. You need to cover: (1) wound care, (2) medication, (3) follow-up appointment.",
            "question": "Which is the best way to deliver this information?",
            "options": [
                "There are three things I want to go through before you leave -- first, looking after your wound, then your medication, and finally your follow-up appointment. Let's start with the wound.",
                "So you need to keep the wound clean and dry and change the dressing every two days and take the antibiotics twice a day with food and don't miss any doses and your follow-up is in ten days at the same clinic and bring your discharge letter.",
                "Keep the wound dry. Your appointment is in ten days. Take these tablets.",
                "You need to look after your wound. Looking after your wound is really important. Please look after your wound carefully.",
            ],
        },
        "expected_response": {"correct_answer": "There are three things I want to go through before you leave -- first, looking after your wound, then your medication, and finally your follow-up appointment. Let's start with the wound."},
        "scoring_type": "rule_based",
    },
    # ── PHASE D: progression sample -- proves multiple practices/difficulty/
    # stage/explanations/mistake-types work end to end, on a small slice
    # (1 Reading technique gets the full guided->independent->exam_style
    # ladder; Listening/Writing/Speaking each get one extra practice to prove
    # the architecture generalizes across modules). See module docstring.
    {
        "technique_skill_tag": "textual_verification",
        "title": "Find the Proof (Second Pass)",
        "instructions": "Same skill, a new passage. Which sentence actually proves the claim below?",
        "difficulty": "beginner", "stage": "guided", "sort_order": 10,
        "content": {
            "passage": "The hospital's infection control policy requires all staff to perform hand hygiene before and after every patient contact. Alcohol-based hand rub is the preferred method unless hands are visibly soiled, in which case soap and water must be used. Compliance is audited monthly across all wards.",
            "claim": "Soap and water should be used instead of alcohol-based hand rub when hands are visibly dirty.",
            "options": [
                "The hospital's infection control policy requires all staff to perform hand hygiene before and after every patient contact.",
                "Alcohol-based hand rub is the preferred method unless hands are visibly soiled, in which case soap and water must be used.",
                "Compliance is audited monthly across all wards.",
            ],
        },
        "expected_response": {
            "correct_answer": "Alcohol-based hand rub is the preferred method unless hands are visibly soiled, in which case soap and water must be used.",
            "explanation": "This sentence is the only one that states the soap-and-water exception for visibly soiled hands -- the exact condition in the claim.",
            "distractors": [
                {
                    "option": "The hospital's infection control policy requires all staff to perform hand hygiene before and after every patient contact.",
                    "mistake_type": "missed_evidence",
                    "explanation": "This confirms hand hygiene is required, but says nothing about soap vs. alcohol rub -- it doesn't prove this specific claim.",
                },
                {
                    "option": "Compliance is audited monthly across all wards.",
                    "mistake_type": "distractor_confusion",
                    "explanation": "This is about auditing, not about which hand-hygiene method to use -- unrelated to the claim.",
                },
            ],
        },
        "scoring_type": "rule_based",
    },
    {
        "technique_skill_tag": "textual_verification",
        "title": "Find the Proof (Independent Practice)",
        "instructions": "No hints this time. Read the passage, then find the sentence that proves the claim.",
        "difficulty": "intermediate", "stage": "independent", "sort_order": 20,
        "content": {
            "passage": "Warfarin requires regular INR monitoring because its effect varies with diet, other medications, and individual metabolism. Patients are usually tested weekly when a dose is first started, moving to monthly once a stable INR is achieved. A sudden increase in green leafy vegetable intake can reduce warfarin's effect.",
            "claim": "Testing frequency for warfarin decreases once the patient's INR has stabilized.",
            "options": [
                "Warfarin requires regular INR monitoring because its effect varies with diet, other medications, and individual metabolism.",
                "Patients are usually tested weekly when a dose is first started, moving to monthly once a stable INR is achieved.",
                "A sudden increase in green leafy vegetable intake can reduce warfarin's effect.",
            ],
        },
        "expected_response": {
            "correct_answer": "Patients are usually tested weekly when a dose is first started, moving to monthly once a stable INR is achieved.",
            "explanation": "This sentence directly states the change from weekly to monthly testing -- a drop in frequency -- once INR is stable.",
            "distractors": [
                {
                    "option": "Warfarin requires regular INR monitoring because its effect varies with diet, other medications, and individual metabolism.",
                    "mistake_type": "missed_evidence",
                    "explanation": "This explains why monitoring is needed at all, not how the frequency changes over time.",
                },
                {
                    "option": "A sudden increase in green leafy vegetable intake can reduce warfarin's effect.",
                    "mistake_type": "reasoning",
                    "explanation": "This is a fact about diet affecting warfarin, unrelated to testing frequency.",
                },
            ],
        },
        "scoring_type": "rule_based",
    },
    {
        "technique_skill_tag": "textual_verification",
        "title": "Find the Proof (Exam-Style)",
        "instructions": "Exam pace: one read-through, then answer. Which sentence proves the claim?",
        "difficulty": "exam", "stage": "exam_style", "sort_order": 30,
        "content": {
            "passage": "Pressure ulcers develop most rapidly over bony prominences where sustained pressure restricts blood flow to the skin and underlying tissue. Repositioning patients with limited mobility at least every two hours is the standard preventive measure, though higher-risk patients may need repositioning more frequently. Nutritional status also affects skin integrity and healing capacity.",
            "claim": "Patients at higher risk of pressure ulcers may need to be repositioned more often than every two hours.",
            "options": [
                "Pressure ulcers develop most rapidly over bony prominences where sustained pressure restricts blood flow to the skin and underlying tissue.",
                "Repositioning patients with limited mobility at least every two hours is the standard preventive measure, though higher-risk patients may need repositioning more frequently.",
                "Nutritional status also affects skin integrity and healing capacity.",
            ],
        },
        "expected_response": {
            "correct_answer": "Repositioning patients with limited mobility at least every two hours is the standard preventive measure, though higher-risk patients may need repositioning more frequently.",
            "explanation": "This is the only sentence that mentions higher-risk patients needing more frequent repositioning than the every-two-hours standard.",
            "distractors": [
                {
                    "option": "Pressure ulcers develop most rapidly over bony prominences where sustained pressure restricts blood flow to the skin and underlying tissue.",
                    "mistake_type": "reasoning",
                    "explanation": "This explains why pressure ulcers form, not the repositioning schedule for higher-risk patients.",
                },
                {
                    "option": "Nutritional status also affects skin integrity and healing capacity.",
                    "mistake_type": "distractor_confusion",
                    "explanation": "This is about nutrition, not repositioning frequency -- unrelated to the claim.",
                },
            ],
        },
        "scoring_type": "rule_based",
    },
    {
        "technique_skill_tag": "keyword_prediction",
        "title": "Predict the Keywords (Independent Practice)",
        "instructions": "Predict the vocabulary before listening -- no hints this time.",
        "difficulty": "intermediate", "stage": "independent", "sort_order": 10,
        "content": {
            "passage": "You are about to hear a nurse discussing a patient's discharge plan with a colleague. Here is the note-completion gap:\n\nFollow-up arranged with: ___________",
            "question": "Which is the best keyword prediction to prepare for this gap?",
            "options": [
                "Listen for a role or place -- e.g. 'GP', 'the practice nurse', 'the outpatient clinic' -- and also phrasing like 'follow up with' or 'see him again at'",
                "Listen only for a person's first name",
                "Listen for the patient's date of birth",
                "Listen for the ward name",
            ],
        },
        "expected_response": {"correct_answer": "Listen for a role or place -- e.g. 'GP', 'the practice nurse', 'the outpatient clinic' -- and also phrasing like 'follow up with' or 'see him again at'"},
        "scoring_type": "rule_based",
    },
    {
        "technique_skill_tag": "case_note_selection",
        "title": "Which Note Belongs in the Letter? (Independent Practice)",
        "instructions": "Read the case notes, then decide which one does NOT belong in the letter -- no hints this time.",
        "difficulty": "intermediate", "stage": "independent", "sort_order": 10,
        "content": {
            "passage": "Case notes for Mr. David Okafor, 45. You are writing a referral letter to a cardiologist for investigation of recurrent chest pain.\n\nCase notes:\n- Recurrent central chest pain on exertion, 3 episodes in 2 weeks\n- Family history of ischemic heart disease (father, MI age 52)\n- Works as a primary school teacher\n- Blood pressure 148/92 at last visit",
            "question": "Which case note is NOT relevant to this cardiology referral and should be left out of the letter?",
            "options": [
                "Recurrent central chest pain on exertion, 3 episodes in 2 weeks",
                "Family history of ischemic heart disease (father, MI age 52)",
                "Works as a primary school teacher",
                "Blood pressure 148/92 at last visit",
            ],
        },
        "expected_response": {"correct_answer": "Works as a primary school teacher"},
        "scoring_type": "rule_based",
    },
    {
        "technique_skill_tag": "empathy_validation",
        "title": "Respond to the Patient's Worry (Independent Practice)",
        "instructions": "Choose the response that best acknowledges the patient's feelings -- no hints this time.",
        "difficulty": "intermediate", "stage": "independent", "sort_order": 10,
        "content": {
            "passage": "TRANSCRIPT EXCERPT -- Patient to Nurse:\n\n\"I don't think I can cope with another round of this treatment. I'm exhausted, and I'm not sure it's even worth it anymore.\"",
            "question": "What is the most patient-centred way to respond?",
            "options": [
                "It sounds like you're feeling really worn down by all of this -- can we talk about what's making it feel like too much right now?",
                "You have to keep going, the treatment is working.",
                "Let's just focus on scheduling your next session.",
                "Lots of patients feel that way, it's completely normal.",
            ],
        },
        "expected_response": {"correct_answer": "It sounds like you're feeling really worn down by all of this -- can we talk about what's making it feel like too much right now?"},
        "scoring_type": "rule_based",
    },
]


def seed_micro_practices():
    supabase = get_supabase()
    techniques_by_tag = {
        t["skill_tag"]: t["id"]
        for t in supabase.table("techniques").select("id, skill_tag").execute().data
    }
    count = 0
    for mp in MICRO_PRACTICES:
        technique_id = techniques_by_tag.get(mp["technique_skill_tag"])
        if technique_id is None:
            print(f"  [SKIP] No technique found for skill_tag={mp['technique_skill_tag']!r} -- run seed_techniques.py first")
            continue
        existing = supabase.table("micro_practices").select("id").eq(
            "technique_id", technique_id
        ).eq("title", mp["title"]).execute()
        if existing.data:
            print(f"  [SKIP] Exists: {mp['title']}")
            continue
        supabase.table("micro_practices").insert({
            "technique_id": technique_id,
            "title": mp["title"],
            "instructions": mp["instructions"],
            "content": mp["content"],
            "expected_response": mp["expected_response"],
            "scoring_type": mp["scoring_type"],
            "difficulty": mp.get("difficulty", "beginner"),
            "stage": mp.get("stage", "guided"),
            "sort_order": mp.get("sort_order", 0),
        }).execute()
        count += 1
        print(f"  [OK] Added: {mp['title']}")
    print(f"\n[OK] Seeded {count} micro-practices to Supabase")
    return count


if __name__ == "__main__":
    seed_micro_practices()
