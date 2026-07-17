"""Pre-generate the landing-page demo voice clips via Google WaveNet TTS.

Mirrors backend/app/services/tts_service.py voice config so the demo sounds
identical to the real product. Patient (Amit, 35, male) and nurse (female) get
two distinct voices. Writes turn-0.mp3 .. turn-7.mp3 into public/demo-audio/.

Run whenever DEMO_TRANSCRIPT in
app/components/landing/DemoSection.tsx changes:

    python frontend/scripts/gen_demo_audio.py

Reads GOOGLE_TTS_API_KEY from backend/.env. Stdlib only, no deps.
"""
import base64
import json
import re
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve()
FRONTEND = HERE.parent.parent          # frontend/
REPO = FRONTEND.parent                  # repo root
ENV = REPO / "backend" / ".env"
OUT = FRONTEND / "public" / "demo-audio"

GOOGLE_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"

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

# From get_default_voice_config: male non-elderly, and default female.
PATIENT_VOICE = {"name": "en-GB-Wavenet-B", "rate": 0.90, "pitch": -1.0}  # male, Amit 35
NURSE_VOICE = {"name": "en-GB-Wavenet-A", "rate": 0.95, "pitch": 0.0}      # female

_ACTION_TAG_RE = re.compile(r"\*[^*\n]{1,80}\*")


def strip_action_tags(text: str) -> str:
    cleaned = _ACTION_TAG_RE.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()


def load_key() -> str:
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("GOOGLE_TTS_API_KEY"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("GOOGLE_TTS_API_KEY not found in backend/.env")


def synth(text: str, voice: dict, key: str) -> bytes:
    payload = {
        "input": {"text": strip_action_tags(text) or text},
        "voice": {"languageCode": "en-GB", "name": voice["name"]},
        "audioConfig": {
            "audioEncoding": "MP3",
            "speakingRate": voice["rate"],
            "pitch": voice["pitch"],
        },
    }
    req = urllib.request.Request(
        f"{GOOGLE_TTS_URL}?key={key}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    audio = data.get("audioContent")
    if not audio:
        raise SystemExit(f"no audioContent for: {text[:40]!r}")
    return base64.b64decode(audio)


def main() -> None:
    key = load_key()
    OUT.mkdir(parents=True, exist_ok=True)
    for i, text in enumerate(TRANSCRIPT):
        voice = PATIENT_VOICE if i % 2 == 0 else NURSE_VOICE
        role = "patient" if i % 2 == 0 else "nurse"
        audio = synth(text, voice, key)
        (OUT / f"turn-{i}.mp3").write_bytes(audio)
        print(f"turn-{i}.mp3  {role:7s} {voice['name']}  {len(audio):>7d} bytes")
    print(f"\nWrote {len(TRANSCRIPT)} clips to {OUT}")


if __name__ == "__main__":
    main()
