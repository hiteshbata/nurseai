"""Seed OET speaking scenarios into Supabase with interlocutor + nurse cards."""
import json
from app.core.supabase import get_supabase

SCORING_CRITERIA = {
    "criteria": [
        "relationship_building", "patient_perspective", "providing_structure",
        "information_gathering", "information_giving",
        "intelligibility", "fluency", "appropriateness_of_language", "grammar",
    ]
}

SPEAKING_SCENARIOS = [
    # ── 1. Chest Pain in Emergency Department ──
    {
        "module": "speaking",
        "title": "Chest Pain in Emergency Department",
        "difficulty": "medium",
        "setting": "Emergency Department, 3:00 PM on a busy weekday. Mr. Rajesh Kumar has been brought in by his son after experiencing sudden onset chest pain while gardening at home. The department is noisy and the patient appears visibly distressed, clutching his chest and breathing rapidly. The nurse has just been assigned to triage and assess him.",
        "nurse_card": {

            "role": "You are speaking to a 58-year-old man who has presented to the Emergency Department with acute chest pain radiating to his left arm. He is anxious and frightened, fearing he is having a heart attack.",
            "tasks": [
                "Introduce yourself warmly to the patient and his son; make eye contact and use a calm, reassuring tone",
                "Enquire about the chest pain — onset, duration, character, radiation, associated symptoms; ask about medical history and current medications",
                "Explain the immediate next steps — ECG, blood tests, cardiac monitoring — in clear, jargon-free language",
                "Advise on what to expect in the next hour; reassure the patient without being dismissive of his fears",
                "Check the patient's understanding and invite any questions before proceeding"
            ]
        },
        "interlocutor_card": {
            "persona": "Mr. Rajesh Kumar is a 58-year-old retired bank manager who was gardening when he suddenly felt a crushing chest pain. His father died of a heart attack at age 60, and he is terrified he is having the same thing. He is cooperative but needs constant reassurance.",
            "emotional_triggers": [
                "Mentions his father's heart attack when asked about family history",
                "Becomes more anxious if the nurse seems hurried or uses medical jargon",
                "Relieved when the nurse explains things simply and makes eye contact"
            ],
            "questions_patient_will_ask": [
                "Am I having a heart attack?",
                "Is this serious? Will I be okay?",
                "Do I need surgery?",
                "Can I call my wife?"
            ],
            "information_to_withhold": [
                "Does not mention he had mild indigestion-like pain three days ago unless the nurse asks about recent symptoms",
                "Does not volunteer that he stopped taking his blood pressure medication two weeks ago unless the nurse asks about medication adherence"
            ]
        },
        "scoring_criteria": SCORING_CRITERIA
    },
    # ── 2. Pre-operative Anxiety ──
    {
        "module": "speaking",
        "title": "Pre-operative Anxiety",
        "difficulty": "medium",
        "setting": "Surgical Ward, 7:30 PM the evening before surgery. Mrs. Priya Sharma was admitted this afternoon for an appendectomy scheduled at 8:00 AM tomorrow. She is sitting on her bed in a hospital gown, looking tense. The nurse is doing the pre-operative check and providing information about the procedure.",        "nurse_card": {

            "role": "You are speaking to a 42-year-old woman who has been admitted for an appendectomy. She is extremely anxious, having never had surgery or been hospitalised before.",
            "tasks": [
                "Greet the patient warmly and acknowledge her anxiety; build rapport by asking how she is feeling",
                "Enquire about her understanding of the procedure, her medical history, and any concerns about anaesthesia or recovery",
                "Explain the pre-operative steps — fasting from midnight, pre-medication, consent form, what happens in the operating theatre",
                "Advise on post-operative expectations — pain management, when she can eat, how long she will stay in hospital",
                "Address her worries about recovery and her children; offer to arrange a social work referral if needed"
            ]
        },
        "interlocutor_card": {
            "persona": "Mrs. Priya Sharma is a 42-year-old primary school teacher and mother of two young children (ages 5 and 8). She has never had surgery before and is extremely anxious, especially about the anaesthesia and who will care for her children while she recovers. She is emotional but polite.",
            "emotional_triggers": [
                "Becomes tearful when discussing her children or the possibility of complications",
                "Fearful of needles and anaesthesia — may ask detailed questions about 'not waking up'",
                "Relieved if the nurse mentions specific practical help like social work or visitor hours"
            ],
            "questions_patient_will_ask": [
                "Have you done this before? Is the surgeon good?",
                "Will I be awake during the surgery?",
                "What if something goes wrong?",
                "How long until I can go back to work?"
            ],
            "information_to_withhold": [
                "Does not mention she is worried about the cost of the hospital stay unless the nurse asks about financial concerns",
                "Does not mention her mother had a bad reaction to anaesthesia decades ago unless the nurse asks about family history with anaesthesia"
            ]
        },
        "scoring_criteria": SCORING_CRITERIA
    },
    # ── 3. Diabetes Insulin Education ──
    {
        "module": "speaking",
        "title": "Diabetes Insulin Education",
        "difficulty": "easy",
        "setting": "Outpatient Diabetes Clinic, 10:30 AM. Mr. Amit Patel was diagnosed with Type 2 diabetes one week ago and has been prescribed insulin injections. Today is his first education session with the diabetes nurse. He is sitting in a consultation room, looking nervous and holding the insulin pen packaging.",        "nurse_card": {

            "role": "You are speaking to a 35-year-old man who has been newly diagnosed with Type 2 diabetes and has been prescribed insulin injections. He is confused, overwhelmed, and anxious about self-injection.",
            "tasks": [
                "Introduce yourself and explain the purpose of the session; ask how he has been feeling since the diagnosis",
                "Enquire about his current diet, exercise routine, and any previous experience with injections or glucose monitoring",
                "Explain why insulin is necessary — use a simple analogy the patient can understand",
                "Demonstrate step by step how to prepare and administer the insulin injection; address needle fear",
                "Advise on injection site rotation, timing of doses, storage, and what to do if a dose is missed; ask the patient to demonstrate understanding"
            ]
        },
        "interlocutor_card": {
            "persona": "Mr. Amit Patel is a 35-year-old software engineer who leads a sedentary lifestyle and eats a lot of takeaway food. He was shocked by the diabetes diagnosis and assumed he could just take pills. The idea of daily injections is frightening and feels overwhelming. He is cooperative but needs simple, practical explanations.",
            "emotional_triggers": [
                "Visibly flinches at the sight of the insulin needle — needle phobia is a real concern",
                "Gets confused when medical terms are used without explanation",
                "Relieved and more engaged when the nurse uses a demonstration dummy first"
            ],
            "questions_patient_will_ask": [
                "Will this hurt?",
                "Can I just take tablets instead?",
                "Do I need to do this forever?",
                "What happens if I skip a dose?",
                "Can I still eat what I want?"
            ],
            "information_to_withhold": [
                "Does not mention he has been drinking sugary soft drinks daily unless the nurse asks about his diet",
                "Does not mention he has not checked his blood sugar even once since diagnosis unless the nurse asks about monitoring"
            ]
        },
        "scoring_criteria": SCORING_CRITERIA
    },
    # ── 4. Discharge Instructions - Post Hip Replacement ──
    {
        "module": "speaking",
        "title": "Discharge Instructions - Post Hip Replacement",
        "difficulty": "medium",
        "setting": "Orthopaedic Ward, 10:00 AM on discharge day. Mrs. Lakshmi Nair had a total hip replacement three days ago and has been cleared for discharge. She is dressed in her own clothes, sitting in a chair beside her bed, listening carefully as the nurse goes through the discharge plan. Her discharge summary is on the bedside table.",        "nurse_card": {

            "role": "You are speaking to a 67-year-old woman who has undergone a total hip replacement for severe osteoarthritis and is being discharged. She is relieved to be going home but worried about managing stairs and daily tasks.",
            "tasks": [
                "Greet the patient and congratulate her on her progress; explain the purpose of the discharge discussion",
                "Enquire about her home situation — who lives with her, stairs, bathroom accessibility, who will help during recovery",
                "Explain wound care, signs of infection to watch for, and when to seek medical help",
                "Advise on activity restrictions, safe movement (hip precautions), prescribed exercises, and use of walking aids",
                "Confirm follow-up appointment details, provide emergency contact information, and check understanding before discharge"
            ]
        },
        "interlocutor_card": {
            "persona": "Mrs. Lakshmi Nair is a 67-year-old retired school principal who lives with her husband, who also has mobility problems due to arthritis. She has a two-storey house with stairs and is very worried about how she will manage. She is grateful for the surgery but anxious about her independence.",
            "emotional_triggers": [
                "Becomes visibly worried when stairs or bathing are mentioned",
                "Relieved if the nurse provides specific solutions (e.g., commode chair, arranging meals)",
                "Proud and independent — may downplay how much help she needs; reluctant to ask for assistance"
            ],
            "questions_patient_will_ask": [
                "How do I manage the stairs at home?",
                "When can I drive again?",
                "What exercises should I do? How often?",
                "How do I know if the wound is infected?",
                "When is my follow-up appointment?"
            ],
            "information_to_withhold": [
                "Does not mention her husband has trouble cooking and shopping for both of them unless the nurse asks about support at home",
                "Does not mention she has not been doing the physiotherapy exercises as instructed unless the nurse specifically asks"
            ]
        },
        "scoring_criteria": SCORING_CRITERIA
    },
    # ── 5. Chemotherapy Side Effects Discussion ──
    {
        "module": "speaking",
        "title": "Chemotherapy Side Effects Discussion",
        "difficulty": "hard",
        "setting": "Oncology Outpatient Unit, 2:00 PM. Mr. Sanjay Verma has just completed his third cycle of chemotherapy for Hodgkin lymphoma. He is sitting slumped in a chair, looking exhausted and thin. The nurse has called him aside for a side-effect assessment and supportive care discussion. He has lost 8 kg since starting treatment.",        "nurse_card": {

            "role": "You are speaking to a 52-year-old man who has completed his third cycle of chemotherapy for Hodgkin lymphoma. He is exhausted, frustrated, demoralised, and considering stopping treatment.",
            "tasks": [
                "Approach the patient with warmth and sit at eye level; acknowledge that chemotherapy is difficult and validate his feelings",
                "Enquire systematically about side effects — nausea, vomiting, mouth sores, fatigue, appetite, sleep, pain",
                "Explain specific management strategies for each reported side effect (anti-emetics, mouth care, nutritional support, energy conservation)",
                "Advise on weight loss concerns, refer to dietitian, and discuss the importance of nutrition during treatment",
                "Address his emotional distress and thoughts of stopping treatment; explore what support he has at home and offer counselling services"
            ]
        },
        "interlocutor_card": {
            "persona": "Mr. Sanjay Verma is a 52-year-old secondary school teacher who was active and fit before his lymphoma diagnosis. He has been struggling with severe nausea, painful mouth sores, and extreme fatigue. He feels like the treatment is worse than the disease and is seriously considering stopping. He is not angry — he is defeated.",
            "emotional_triggers": [
                "Becomes tearful and quiet when asked how he is really feeling",
                "Perks up slightly if the nurse offers practical, specific solutions rather than generic reassurance",
                "Pulls away if the nurse pressures him to continue treatment without acknowledging his suffering"
            ],
            "questions_patient_will_ask": [
                "Is this nausea ever going to stop?",
                "Is there anything stronger for the mouth pain? I can barely eat.",
                "I've lost so much weight. Is that dangerous?",
                "What if I just stop the chemo?",
                "Will I ever feel normal again?"
            ],
            "information_to_withhold": [
                "Does not mention he has not been taking his anti-nausea medication because it makes him drowsy unless the nurse asks about medication adherence",
                "Does not mention his wife is struggling to cope and he feels like a burden unless the nurse asks about his home support"
            ]
        },
        "scoring_criteria": SCORING_CRITERIA
    },
    # ── 6. Post-Operative Care Instructions ──
    {
        "module": "speaking",
        "title": "Post-Operative Care After Cholecystectomy",
        "difficulty": "easy",
        "setting": "Surgical Day Ward, 4:30 PM. Ms. Deepa Menon had a laparoscopic cholecystectomy this morning and is now awake and stable. She is sitting up in bed sipping water, about to be discharged home. The nurse needs to provide post-operative care instructions before her husband takes her home.",        "nurse_card": {

            "role": "You are speaking to a 29-year-old woman who has just had a laparoscopic cholecystectomy for gallstones. She is groggy and relieved the surgery is over, but slightly anxious about managing pain at home alone.",
            "tasks": [
                "Greet the patient and confirm she is feeling well enough for discharge; check pain level and vital signs",
                "Enquire about pain — location, severity, what pain relief she has been given and what she will take at home",
                "Explain wound care — keeping incisions dry and clean, signs of infection to watch for, when she can shower",
                "Advise on activity restrictions — no heavy lifting for 2 weeks, gradual return to work, when she can drive",
                "Provide dietary guidance — light meals initially, what to avoid, when to call the GP; check understanding"
            ]
        },
        "interlocutor_card": {
            "persona": "Ms. Deepa Menon is a 29-year-old graphic designer who had her gallbladder removed this morning. She is relieved the surgery went well but is worried about pain when the anaesthetic wears off. She lives alone and wants to know how much she will be able to manage by herself. She is chatty and cooperative.",
            "emotional_triggers": [
                "Worried about being alone at home — may ask several times if she can manage independently",
                "Concerned about returning to work quickly — worried about losing income",
                "Relieved when the nurse provides written instructions she can refer to later"
            ],
            "questions_patient_will_ask": [
                "How bad will the pain get when I get home?",
                "When can I shower?",
                "Can I climb stairs at home?",
                "When can I go back to work?",
                "What should I eat?"
            ],
            "information_to_withhold": [
                "Does not mention she lives alone on the third floor with no lift unless the nurse asks about her home situation",
                "Does not mention she has a history of constipation which may worsen with pain medication unless the nurse asks about bowel habits"
            ]
        },
        "scoring_criteria": SCORING_CRITERIA
    },
    # ── 7. Medication Side Effects Counselling ──
    {
        "module": "speaking",
        "title": "Medication Side Effects Counselling",
        "difficulty": "medium",
        "setting": "Respiratory Clinic, 11:00 AM. Mr. Arjun Singh has been diagnosed with moderate persistent asthma and has been prescribed a new combination inhaler (corticosteroid + long-acting beta-agonist). He has been using it for a week and has come for a follow-up to discuss how he is managing. He looks frustrated.",        "nurse_card": {

            "role": "You are speaking to a 45-year-old man who has been prescribed a new combination inhaler for moderate persistent asthma. He is frustrated by side effects and considering stopping the medication.",
            "tasks": [
                "Greet the patient and ask about his asthma symptoms since starting the new inhaler — improvement, frequency of attacks",
                "Enquire specifically about side effects — thrush, hoarse voice, cough, palpitations, headache",
                "Explain the purpose of each component of the inhaler and why consistent use is important for long-term control",
                "Advise on correct inhaler technique — demonstrate and ask for a return demonstration; discuss rinsing mouth after use",
                "Address his frustration and any concerns about side effects versus benefits; offer a written asthma action plan"
            ]
        },
        "interlocutor_card": {
            "persona": "Mr. Arjun Singh is a 45-year-old taxi driver who works long hours. He was diagnosed with asthma a year ago but his symptoms have worsened. The new inhaler has helped his breathing but he hates the side effects — he has a persistent cough and his voice is hoarse, which affects his work. He is considering going back to his old blue inhaler only.",
            "emotional_triggers": [
                "Becomes defensive if he feels the nurse is not listening to his side-effect concerns",
                "Worried about his livelihood — a hoarse voice affects his ability to interact with passengers",
                "More receptive if the nurse acknowledges the side effects are real and offers practical solutions"
            ],
            "questions_patient_will_ask": [
                "Why do I need two types of medicine in one inhaler?",
                "This cough is worse than before — is the inhaler making it worse?",
                "Can I just use my blue inhaler instead?",
                "How long do I need to use this for?",
                "Will the side effects go away?"
            ],
            "information_to_withhold": [
                "Does not mention he is often too rushed to rinse his mouth after using the inhaler unless the nurse asks about his routine",
                "Does not mention he has been smoking again after quitting for 6 months unless the nurse asks about smoking status"
            ]
        },
        "scoring_criteria": SCORING_CRITERIA
    },
    # ── 8. Discharge Planning After Stroke ──
    {
        "module": "speaking",
        "title": "Discharge Planning After Stroke",
        "difficulty": "hard",
        "setting": "Neurology Ward, 9:30 AM. Mrs. Sunita Joshi is being discharged today after spending 10 days in hospital following a mild ischaemic stroke. She has made a good recovery but has some residual weakness in her left hand and mild speech difficulty. The nurse is coordinating the discharge with the patient and her daughter who is present.",        "nurse_card": {

            "role": "You are speaking to a 72-year-old woman who has spent 10 days in hospital following a mild ischaemic stroke and is being discharged. She is determined but anxious about recurrent stroke and loss of independence.",
            "tasks": [
                "Greet the patient and her daughter; acknowledge her progress and ask how she feels about going home",
                "Enquire about home environment — bathroom accessibility, who will be at home, ability to perform daily activities",
                "Explain the new medications (antiplatelet, statin, antihypertensives) — purpose, dosing, side effects to watch for",
                "Advise on lifestyle modifications — diet, exercise, smoking cessation, blood pressure monitoring; arrange community follow-up",
                "Discuss red-flag symptoms of recurrent stroke and when to call an ambulance; confirm understanding before discharge"
            ]
        },
        "interlocutor_card": {
            "persona": "Mrs. Sunita Joshi is a 72-year-old retired nurse who understands the medical aspects of her condition but is struggling with the emotional reality. She was independent before the stroke and hates relying on her daughter. She is worried about having another stroke and feels frustrated by her weak hand and slight slurred speech.",
            "emotional_triggers": [
                "Tears up when discussing her loss of independence — was always a caregiver, now needs care",
                "Frustrated by her speech difficulty — may say 'I know what I want to say, it just won't come out'",
                "Receptive if the nurse treats her as a capable person rather than a dependent patient"
            ],
            "questions_patient_will_ask": [
                "Will my hand get back to normal?",
                "Am I going to have another stroke?",
                "Can I stop taking all these tablets after a while?",
                "When can I start driving again?",
                "Do I need to stop cooking for the family?"
            ],
            "information_to_withhold": [
                "Does not mention she has fallen twice at home in the past year unless the nurse asks about falls history",
                "Does not mention she stopped taking her blood pressure medication before the stroke because 'it made her dizzy' unless the nurse asks about medication adherence"
            ]
        },
        "scoring_criteria": SCORING_CRITERIA
    },
    # ── 9. Pain Assessment ──
    {
        "module": "speaking",
        "title": "Post-Operative Pain Assessment",
        "difficulty": "easy",
        "setting": "Orthopaedic Ward, 7:00 AM during morning rounds. Mr. Vikram Patel had an open reduction and internal fixation of his right tibia and fibula yesterday after a motorcycle accident. He had a restless night and is now grimacing as the nurse approaches for the morning pain assessment and medication round.",        "nurse_card": {

            "role": "You are speaking to a 33-year-old man who had open reduction and internal fixation of his right tibia and fibula yesterday after a motorcycle accident. He is in significant pain, frustrated about his injury, and worried about lost income.",
            "tasks": [
                "Greet the patient and observe his body language; ask about his night and pain level using a pain scale",
                "Enquire about the nature of the pain — location, type (sharp, aching, throbbing), aggravating/relieving factors, impact on sleep",
                "Explain the pain management plan — scheduled analgesia, breakthrough pain options, non-pharmacological methods (ice, elevation)",
                "Advise on the importance of staying ahead of the pain — taking medication regularly rather than waiting for severe pain",
                "Assess his understanding of when to report worsening pain and what the next steps are for recovery"
            ]
        },
        "interlocutor_card": {
            "persona": "Mr. Vikram Patel is a 33-year-old delivery rider who broke his leg in a motorcycle accident. He is in significant pain and did not sleep well. He is worried about how long recovery will take because he has no income while off work. He is stoic and may underreport his pain initially, but is visibly uncomfortable.",
            "emotional_triggers": [
                "Tries to downplay his pain initially ('I'm fine, just give me something for it') but grimaces when moving",
                "Becomes anxious when discussing recovery time — worried about bills, his bike, his job",
                "More open about pain level if the nurse uses the pain scale and asks specifically about sleep disruption"
            ],
            "questions_patient_will_ask": [
                "Can I get something stronger for the pain?",
                "How long will I be in hospital?",
                "When can I put weight on my leg?",
                "Will I be able to ride my bike again?",
                "Can I have something to help me sleep?"
            ],
            "information_to_withhold": [
                "Does not mention he has been taking leftover painkillers from a previous injury on top of the hospital medication unless the nurse asks specifically",
                "Does not mention he is worried about the cost of the hospital stay unless the nurse asks about financial concerns"
            ]
        },
        "scoring_criteria": SCORING_CRITERIA
    },
    # ── 10. Patient Refusing Treatment ──
    {
        "module": "speaking",
        "title": "Patient Refusing Antibiotic Treatment",
        "difficulty": "hard",
        "setting": "Medical Ward, 2:30 PM. Mr. Gurpreet Singh was admitted two days ago with pneumonia and started on intravenous antibiotics. He has been told he needs to complete a 5-day course. The nurse has just entered his room to administer the next dose and found the IV disconnected. The patient states he wants to go home and does not want any more treatment.",        "nurse_card": {

            "role": "You are speaking to a 61-year-old man who was admitted with pneumonia and is refusing to complete his IV antibiotic course. He is angry, feels trapped, distrustful of the medical system, and wants to go home.",
            "tasks": [
                "Approach calmly and sit down; acknowledge his frustration and thank him for telling you how he feels — do not be defensive",
                "Enquire about the reason — is it the IV site, side effects, feeling better, personal obligations, distrust? Listen actively",
                "Explain the consequences of stopping antibiotics prematurely — risk of relapse, resistance, readmission — in clear terms without coercion",
                "Advise on possible solutions — switching to oral antibiotics, completing the course with a different IV site, involving the doctor",
                "Explore what would make him more comfortable continuing treatment; involve the medical team if he still refuses; document his decision clearly"
            ]
        },
        "interlocutor_card": {
            "persona": "Mr. Gurpreet Singh is a 61-year-old construction site supervisor who rarely gets sick and hates being in hospital. He feels trapped and says the IV is uncomfortable and stopping him from sleeping. He feels much better now and does not see why he needs more 'drips'. He also has a big project starting at work and is worried about letting his team down.",
            "emotional_triggers": [
                "Becomes more defensive if the nurse sounds judgemental or dismisses his feelings",
                "Softens if the nurse acknowledges his autonomy and speaks to him as an equal, not as a disobedient patient",
                "More willing to negotiate if the nurse addresses his practical concerns (work, IV discomfort) first before discussing medical necessity"
            ],
            "questions_patient_will_ask": [
                "Why do I need more medicine if I feel fine now?",
                "Can I just take tablets instead of this drip?",
                "When can I go back to work?",
                "What happens if I just leave now?",
                "Can I at least have the drip taken out for a few hours?"
            ],
            "information_to_withhold": [
                "Does not mention he has a history of alcoholism and is worried about withdrawal symptoms in hospital unless the nurse asks about alcohol intake",
                "Does not mention his wife recently passed away and he is struggling emotionally unless the nurse asks about personal circumstances"
            ]
        },
        "scoring_criteria": SCORING_CRITERIA
    },
]


def seed_scenarios():
    supabase = get_supabase()
    count = 0
    for scenario in SPEAKING_SCENARIOS:
        existing = supabase.table("scenarios").select("id").eq("title", scenario["title"]).execute()
        if not existing.data:
            supabase.table("scenarios").insert(scenario).execute()
            count += 1
            print(f"  [OK] Added: {scenario['title']}")
        else:
            print(f"  [SKIP] Exists: {scenario['title']}")
    print(f"\n[OK] Seeded {count} scenarios to Supabase")
    return count


if __name__ == "__main__":
    seed_scenarios()
