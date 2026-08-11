"""Seed real micro-practice exercise content for the Phase C launch slice
(Reading's 4 techniques only -- Listening/Writing/Speaking get theirs in a
later pass). Same idempotent insert-if-missing convention as
seed_techniques.py, keyed on (technique_id, title) since micro_practices has
no unique slug column.

All four are deliberately rule_based (exact-match against `options`, via
technique_grading.grade_rule_based) -- no AI-grading dependency for this
first slice. Original short passages, not real OET paper content."""
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
