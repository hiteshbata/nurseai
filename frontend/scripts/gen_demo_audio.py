"""Pre-generate the landing-page demo voice clips via OpenAI TTS.

The real product's live roleplay already defaults to OpenAI's realtime voice
model (VOICE_PROVIDER=openai in backend/app/core/config.py) -- using OpenAI
TTS here means the demo actually matches the flagship live experience, not
the older Google-TTS turn-based fallback path.

Patient (Amit, 35, male, anxious) and nurse (female, warm) get distinct
voices, each steered with an `instructions` prompt for natural, human
delivery -- gpt-4o-mini-tts supports this directly, unlike flat TTS models.
Writes turn-0.mp3 .. turn-7.mp3 into public/demo-audio/.

Run whenever DEMO_TRANSCRIPT in app/components/landing/DemoSection.tsx
changes:

    python frontend/scripts/gen_demo_audio.py

Reads OPENAI_API_KEY from backend/.env. Stdlib only, no deps.
"""
import json
import re
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve()
FRONTEND = HERE.parent.parent          # frontend/
REPO = FRONTEND.parent                  # repo root
ENV = REPO / "backend" / ".env"
OUT = FRONTEND / "public" / "demo-audio"

OPENAI_TTS_URL = "https://api.openai.com/v1/audio/speech"
MODEL = "gpt-4o-mini-tts"

# Must stay in lockstep with DEMO_TRANSCRIPT in DemoSection.tsx
# (even index = patient, odd index = nurse).
TRANSCRIPT = [
    "One week ago I was fine. Now they tell me I must inject myself every day. I don’t understand how it came to this.",
    "That is a great deal to take in one week. Before we open the pen — how have you been feeling since they told you?",
    "Frightened, mostly. My father was on insulin. He lost his foot.",
    "I am sorry. So when you look at that box, that is what you see. Can I tell you how I see it? What happened to your father came from years of high sugar — not from the insulin. The insulin was what they used to try to stop it. Starting now is what protects you from that.",
    "Nobody explained it that way.",
    "The pen delivers it into the subcutaneous tissue, so you will need to rotate the sites each time —",
    "The sub— sorry, Sister. I do not follow.",
    "That is my fault, not yours. I mean the fat just under the skin — your stomach is easiest. And the needle is four millimetres, finer than the one they use for blood tests.",
]

PATIENT_VOICE = {
    "voice": "onyx",
    "instructions": (
        "You are Amit, a 35-year-old man diagnosed with diabetes a week ago, "
        "anxious and scared about starting insulin injections. Speak "
        "naturally and conversationally, with real hesitation and "
        "vulnerability in your voice -- like a real, nervous patient, not a "
        "narrator reading lines."
    ),
}
NURSE_VOICE = {
    "voice": "coral",
    "instructions": (
        "You are an Indian nurse speaking gently to an anxious patient. "
        "Speak with a natural Indian English accent -- the way an Indian "
        "nurse actually sounds, not exaggerated or stereotyped. Warm, "
        "calm, unhurried, clear. Not formal, not robotic."
    ),
}

_ACTION_TAG_RE = re.compile(r"\*[^*\n]{1,80}\*")


def strip_action_tags(text: str) -> str:
    cleaned = _ACTION_TAG_RE.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()


def load_key() -> str:
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("OPENAI_API_KEY"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("OPENAI_API_KEY not found in backend/.env")


def synth(text: str, voice: dict, key: str) -> bytes:
    payload = {
        "model": MODEL,
        "input": strip_action_tags(text) or text,
        "voice": voice["voice"],
        "instructions": voice["instructions"],
        "response_format": "mp3",
    }
    req = urllib.request.Request(
        OPENAI_TTS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def main() -> None:
    key = load_key()
    OUT.mkdir(parents=True, exist_ok=True)
    for i, text in enumerate(TRANSCRIPT):
        voice = PATIENT_VOICE if i % 2 == 0 else NURSE_VOICE
        role = "patient" if i % 2 == 0 else "nurse"
        audio = synth(text, voice, key)
        (OUT / f"turn-{i}.mp3").write_bytes(audio)
        print(f"turn-{i}.mp3  {role:7s} {voice['voice']:6s}  {len(audio):>7d} bytes")
    print(f"\nWrote {len(TRANSCRIPT)} clips to {OUT}")


if __name__ == "__main__":
    main()
