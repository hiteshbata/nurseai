"""Test updated empathy scoring with realistic synthetic transcripts."""
import sys
import os
import asyncio
sys.path.insert(0, '.')
os.environ["AI_PROVIDER"] = "openrouter"

from app.services.ai_scoring import score_speaking


REALISTIC_CONVERSATIONS = [
    {
        "name": "Good empathy — warm, validating nurse",
        "scenario": "Chest Pain in Emergency Department",
        "history": [
            {"role": "nurse", "content": "Good morning, Mr. Kumar. I'm Sarah, one of the nurses here. I can see you're feeling quite anxious — that's completely understandable when you're experiencing chest pain. Can you tell me when it started and what it feels like?"},
            {"role": "patient", "content": "It started about two hours ago while I was gardening. It's like a heavy pressure on my chest."},
            {"role": "nurse", "content": "I understand that must be frightening. A heavy pressure — that's helpful to know. Has it moved anywhere else, like down your arm or into your jaw? And I want you to know we're going to take good care of you and figure out what's going on."},
            {"role": "patient", "content": "It does go down my left arm a bit. I'm really scared it's a heart attack — my father died of one at my age."},
            {"role": "nurse", "content": "I'm so sorry to hear about your father, and I completely understand why you're worried. That must be on your mind right now. Let me explain what we're going to do — first I'll run an ECG, which is just a painless trace of your heart's electrical activity, and we'll do some blood tests. These will help us see exactly what's happening. You're in the right place, and we'll stay right here with you throughout."},
        ]
    },
    {
        "name": "Poor empathy — purely transactional nurse",
        "scenario": "Chest Pain in Emergency Department",
        "history": [
            {"role": "nurse", "content": "Hello, I need to ask you some questions. When did the chest pain start?"},
            {"role": "patient", "content": "About two hours ago while I was gardening."},
            {"role": "nurse", "content": "Rate your pain on a scale of 1 to 10. Does it radiate anywhere?"},
            {"role": "patient", "content": "It's about 7 out of 10. Yes, it goes down my left arm. I'm really scared it's a heart attack."},
            {"role": "nurse", "content": "I'll order an ECG and blood tests. The doctor will review the results. Wait here."},
        ]
    },
    {
        "name": "Mixed — starts clinical, warms up later",
        "scenario": "Pre-operative Anxiety",
        "history": [
            {"role": "nurse", "content": "Mrs. Sharma? I need to go through the pre-operative checklist with you. Have you had anything to eat or drink since midnight?"},
            {"role": "patient", "content": "No, I haven't. But I'm really nervous. I've never had surgery before."},
            {"role": "nurse", "content": "I understand this is a big moment for you. Actually, I can see you're feeling quite anxious about it. That's very normal. Let me walk you through what will happen step by step so you know exactly what to expect."},
            {"role": "patient", "content": "Will I be awake during the surgery? I'm scared about the anaesthetic."},
            {"role": "nurse", "content": "That's a very common concern. You'll be under general anaesthesia, which means you'll be sleeping comfortably throughout. Our anaesthetist will be with you the whole time. What other questions do you have? I want to make sure you feel prepared."},
        ]
    },
]


async def test():
    for conv in REALISTIC_CONVERSATIONS:
        print(f"{'='*60}")
        print(f"TEST: {conv['name']}")
        print(f"{'='*60}")

        nurse_card = {"tasks": [
            "Introduce yourself warmly to the patient",
            "Enquire about the condition and concerns",
            "Explain next steps in clear language",
            "Provide reassurance and check understanding",
        ]}

        result = await score_speaking(
            nurse_card=nurse_card,
            conversation_history=conv["history"],
            scenario_title=conv["scenario"],
        )

        scores = result.get("scores", {})
        empathy = scores.get("empathy", {})

        print(f"\nEMPATHY SCORE: {empathy.get('score', 'N/A')}/6")
        print(f"Reasoning: {empathy.get('feedback', 'N/A')}")
        print()
        print("ALL CLINICAL SCORES (for comparison):")
        for k in ["empathy", "patient_perspective", "providing_structure",
                   "information_gathering", "information_giving"]:
            s = scores.get(k, {})
            print(f"  {k}: {s.get('score', 'N/A')}/6")
        print(f"\nClinical avg: {result.get('clinical_average', '?')}")
        print(f"Linguistic avg: {result.get('linguistic_average', '?')}")
        print(f"Overall band: {result.get('overall_band', '?')}")
        print()

    print("=== ALL TESTS DONE ===")


if __name__ == "__main__":
    asyncio.run(test())
