"""Read 10 seeded scenarios, AI-suggest specialty for each. Dry-run only — no DB writes."""
import sys
import os
import json
import asyncio
sys.path.insert(0, '.')
os.environ["AI_PROVIDER"] = "openrouter"

from app.services.ai_scoring import _call_ai

SPECIALTIES = [
    "Cardiology",
    "Respiratory",
    "Paediatrics",
    "Mental Health",
    "Geriatrics / Elderly Care",
    "Oncology",
    "General / Internal Medicine",
    "Emergency / Acute Care",
    "Maternity / Obstetrics",
    "Surgical / Post-Op",
]

SCENARIOS = [
    {
        "title": "Chest Pain in Emergency Department",
        "setting": "Emergency Department, 3:00 PM. Mr. Rajesh Kumar has been brought in by his son after experiencing sudden onset chest pain while gardening. The department is noisy and the patient appears visibly distressed, clutching his chest and breathing rapidly.",
        "patient": "58-year-old man with acute chest pain radiating to left arm, anxious, father died of heart attack at 60.",
    },
    {
        "title": "Pre-operative Anxiety",
        "setting": "Surgical Ward, 7:30 PM the evening before surgery. Mrs. Priya Sharma was admitted for an appendectomy scheduled for 8:00 AM. She is sitting on her bed in a hospital gown, looking tense.",
        "patient": "42-year-old woman, first surgery ever, extremely anxious about anaesthesia, mother of two young children.",
    },
    {
        "title": "Diabetes Insulin Education",
        "setting": "Outpatient Diabetes Clinic, 10:30 AM. Mr. Amit Patel was diagnosed with Type 2 diabetes one week ago and has been prescribed insulin injections. He is sitting in a consultation room, looking nervous.",
        "patient": "35-year-old software engineer, sedentary lifestyle, newly diagnosed Type 2 diabetes, needle phobia, overwhelmed by daily injections.",
    },
    {
        "title": "Discharge Instructions - Post Hip Replacement",
        "setting": "Orthopaedic Ward, 10:00 AM on discharge day. Mrs. Lakshmi Nair had a total hip replacement three days ago and has been cleared for discharge. She is dressed in her own clothes, sitting in a chair.",
        "patient": "67-year-old retired school principal, lives with husband who also has mobility issues, worried about managing stairs at home.",
    },
    {
        "title": "Chemotherapy Side Effects Discussion",
        "setting": "Oncology Outpatient Unit, 2:00 PM. Mr. Sanjay Verma has just completed his third cycle of chemotherapy for Hodgkin lymphoma. He is sitting slumped in a chair, looking exhausted and thin. He has lost 8 kg.",
        "patient": "52-year-old teacher, struggling with severe nausea, mouth sores, extreme fatigue, considering stopping treatment.",
    },
    {
        "title": "Post-Operative Care After Cholecystectomy",
        "setting": "Surgical Day Ward, 4:30 PM. Ms. Deepa Menon had a laparoscopic cholecystectomy this morning and is now awake and stable. She is sitting up in bed sipping water, about to be discharged.",
        "patient": "29-year-old graphic designer, lives alone, worried about managing pain at home after anaesthetic wears off.",
    },
    {
        "title": "Medication Side Effects Counselling",
        "setting": "Respiratory Clinic, 11:00 AM. Mr. Arjun Singh has been prescribed a new combination inhaler for moderate persistent asthma. He has been using it for a week and has come for follow-up. He looks frustrated.",
        "patient": "45-year-old taxi driver, persistent cough and hoarse voice from inhaler, affects his work, considering stopping the medication.",
    },
    {
        "title": "Discharge Planning After Stroke",
        "setting": "Neurology Ward, 9:30 AM. Mrs. Sunita Joshi is being discharged after 10 days in hospital following a mild ischaemic stroke. She has residual weakness in her left hand and mild speech difficulty.",
        "patient": "72-year-old retired nurse, was independent before stroke, frustrated by weak hand and slurred speech, worried about recurrent stroke.",
    },
    {
        "title": "Post-Operative Pain Assessment",
        "setting": "Orthopaedic Ward, 7:00 AM. Mr. Vikram Patel had open reduction and internal fixation of his right tibia and fibula yesterday after a motorcycle accident. He had a restless night and is grimacing.",
        "patient": "33-year-old delivery rider, significant pain, worried about lost income during recovery, stoic but visibly uncomfortable.",
    },
    {
        "title": "Patient Refusing Antibiotic Treatment",
        "setting": "Medical Ward, 2:30 PM. Mr. Gurpreet Singh was admitted two days ago with pneumonia and started on IV antibiotics. The nurse has just entered his room to find the IV disconnected. The patient wants to go home.",
        "patient": "61-year-old construction supervisor, hates being in hospital, feels much better now, frustrated by IV discomfort, worried about work project.",
    },
]

PROMPT_TEMPLATE = """You are classifying OET roleplay scenarios by medical specialty.

Scenario title: {title}
Setting: {setting}
Patient context: {patient}

Choose the SINGLE best specialty from this list:
{specialties}

Return ONLY the specialty name, nothing else."""


async def tag_all():
    results = []
    for i, s in enumerate(SCENARIOS):
        prompt = PROMPT_TEMPLATE.format(
            title=s["title"],
            setting=s["setting"],
            patient=s["patient"],
            specialties="\n".join(f"- {sp}" for sp in SPECIALTIES),
        )

        print(f"[{i+1}/10] Tagging: {s['title']}...", end=" ", flush=True)
        result = await _call_ai(
            [{"role": "user", "content": prompt}],
            max_tokens=50,
            provider="openrouter",
        )
        tag = result.get("raw_feedback", "").strip()
        # Validate it's one of the options
        if tag not in SPECIALTIES:
            # AI might return partial match — find closest
            for sp in SPECIALTIES:
                if sp.lower() in tag.lower() or tag.lower() in sp.lower():
                    tag = sp
                    break
            else:
                tag = "General / Internal Medicine"
        print(tag)
        results.append({"title": s["title"], "specialty": tag})

    print("\n" + "=" * 70)
    print(f"{'Scenario Title':<45} {'Specialty':<25}")
    print("=" * 70)
    for r in results:
        print(f"{r['title']:<45} {r['specialty']:<25}")
    print("=" * 70)

    return results


if __name__ == "__main__":
    asyncio.run(tag_all())
