"""Seed real micro-practice exercise content for Phase C (Reading's 4
techniques + Listening's 4 techniques so far -- Writing/Speaking get theirs
in a later pass). Same idempotent insert-if-missing convention as
seed_techniques.py, keyed on (technique_id, title) since micro_practices has
no unique slug column.

All eight are deliberately rule_based (exact-match against `options`, via
technique_grading.grade_rule_based) -- no AI-grading dependency for this
slice. Original short passages/transcript excerpts, not real OET paper
content. Listening has no audio pipeline yet, so each exercise presents its
audio content as a written transcript excerpt in `content.passage` -- same
passage/question/options shape the frontend already renders for Reading."""
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
        }).execute()
        count += 1
        print(f"  [OK] Added: {mp['title']}")
    print(f"\n[OK] Seeded {count} micro-practices to Supabase")
    return count


if __name__ == "__main__":
    seed_micro_practices()
