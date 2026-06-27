import json
from typing import List, Dict, Any

OET_QUESTIONS = [
    {"module": "speaking", "type": "role_play", "content": "You are a nurse attending to a patient who has just arrived in the emergency department with chest pain. Explain to the patient what tests you will be conducting and why.", "options": None, "correct_answer": None},
    {"module": "speaking", "type": "role_play", "content": "A patient is anxious about an upcoming surgery. Provide reassurance and explain the pre-operative procedures they will undergo.", "options": None, "correct_answer": None},
    {"module": "speaking", "type": "role_play", "content": "Explain to a patient with diabetes how to properly administer insulin injections at home.", "options": None, "correct_answer": None},
    {"module": "speaking", "type": "role_play", "content": "Discuss medication side effects with a patient and provide guidance on when to seek medical help.", "options": None, "correct_answer": None},
    {"module": "speaking", "type": "role_play", "content": "Communicate discharge instructions to a post-operative patient including activity restrictions and wound care.", "options": None, "correct_answer": None},
    {"module": "writing", "type": "referral_letter", "content": "Write a referral letter from an emergency department nurse to a cardiologist regarding a patient with acute chest pain and elevated cardiac markers.", "options": None, "correct_answer": None},
    {"module": "writing", "type": "case_notes", "content": "Document patient case notes for a 65-year-old male admitted with pneumonia, including vital signs, assessment, and nursing plan.", "options": None, "correct_answer": None},
    {"module": "writing", "type": "incident_report", "content": "Write an incident report for a patient fall that occurred during mobilization on the ward.", "options": None, "correct_answer": None},
    {"module": "writing", "type": "handover_notes", "content": "Prepare handover notes for the day shift including patient status, completed procedures, and pending investigations.", "options": None, "correct_answer": None},
    {"module": "writing", "type": "patient_education", "content": "Write patient education materials for post-discharge care following hip replacement surgery.", "options": None, "correct_answer": None},
    {"module": "reading", "type": "comprehension", "content": "Read the patient case study and answer: What is the primary concern for this hypertensive patient?", "options": ["Acute coronary syndrome", "Hypertensive crisis", "Stroke", "Heart failure"], "correct_answer": "Hypertensive crisis"},
    {"module": "reading", "type": "comprehension", "content": "Based on the patient notes, what medication adjustment is most appropriate?", "options": ["Increase ACE inhibitor dose", "Switch to beta blocker", "Add calcium channel blocker", "Discontinue all antihypertensives"], "correct_answer": "Add calcium channel blocker"},
    {"module": "reading", "type": "comprehension", "content": "What is the correct interpretation of these lab results?", "options": ["Normal kidney function", "Mild renal impairment", "Severe renal failure", "Liver dysfunction"], "correct_answer": "Mild renal impairment"},
    {"module": "reading", "type": "comprehension", "content": "Which nursing intervention is contraindicated for this patient?", "options": ["Position flat in bed", "Continuous cardiac monitoring", "Oxygen therapy", "IV access establishment"], "correct_answer": "Position flat in bed"},
    {"module": "listening", "type": "audio_comprehension", "content": "Listen to the doctor\\'s instructions and identify: What is the main concern mentioned?", "options": ["Infection risk", "Bleeding complications", "Pain management", "Respiratory issues"], "correct_answer": "Infection risk"},
    {"module": "listening", "type": "audio_comprehension", "content": "From the audio, what follow-up appointment is recommended?", "options": ["Within 24 hours", "Within 1 week", "Within 2 weeks", "In 1 month"], "correct_answer": "Within 1 week"},
    {"module": "listening", "type": "audio_comprehension", "content": "What medication should be avoided according to the audio?", "options": ["Paracetamol", "Aspirin", "Ibuprofen", "Codeine"], "correct_answer": "Aspirin"},
    {"module": "listening", "type": "audio_comprehension", "content": "What is the patient\\'s main concern mentioned in the conversation?", "options": ["Cost of treatment", "Side effects of medication", "Time off work", "Family history"], "correct_answer": "Side effects of medication"},
]

class OETQuestionsService:
    @staticmethod
    def get_all_questions() -> List[Dict[str, Any]]:
        return OET_QUESTIONS

    @staticmethod
    def seed_database(supabase) -> int:
        count = 0
        for q in OET_QUESTIONS:
            existing = supabase.table("questions").select("id").eq("content", q["content"]).execute()
            if not existing.data:
                supabase.table("questions").insert({
                    "module": q["module"],
                    "type": q["type"],
                    "content": q["content"],
                    "options": json.dumps(q["options"]) if q["options"] else None,
                    "correct_answer": q["correct_answer"],
                }).execute()
                count += 1
        print(f"Seeded {count} questions")
        return count

oet_service = OETQuestionsService()
