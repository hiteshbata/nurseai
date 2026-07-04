"""Simulate frontend STT with gather pattern. Does NOT close client side — lets dg_ws time out naturally."""
import asyncio, json, os, sys, time, websockets

API_URL = os.environ.get("API_URL", "ws://localhost:8000")
AUDIO_PATH = os.path.join(os.path.dirname(__file__), "_test_audio.webm")
META_PATH = os.path.join(os.path.dirname(__file__), "_test_audio_meta.json")

with open(META_PATH) as f: meta = json.load(f)
total_duration_s = meta["total_duration_s"]
with open(AUDIO_PATH, "rb") as f: audio_bytes = f.read()

accumulated_before = ""
out_lines = []

def log(msg):
    out_lines.append(msg); print(msg, flush=True)

def handle_message(data):
    global accumulated_before
    msgType = data.get("type", "Results")
    log(f'[STT] {{type: {msgType!r}, is_final: {data.get("is_final")}, speech_final: {data.get("speech_final")}, transcript: {json.dumps(data.get("transcript",""))}, accumulated_before: {json.dumps(accumulated_before)}}}')
    if data.get("error"):
        log(f"[STT ERROR] {data['error']}"); return
    msgType = data.get("type", "Results")
    if msgType == "UtteranceEnd" or data.get("speech_final") is True:
        if data.get("transcript"):
            accumulated_before += (" " if accumulated_before else "") + data["transcript"].strip()
        finalText = accumulated_before
        log(f"[STT] FINALIZED: {json.dumps(finalText)}")
        accumulated_before = ""
        trimmed = finalText.strip()
        log(f"[STT] trimmed={json.dumps(trimmed)}")
        if trimmed:
            log(f"[STT] >>> ADDED TO HISTORY: {json.dumps(trimmed)} <<<")
        return
    if data.get("transcript"):
        if data.get("is_final"):
            accumulated_before += (" " if accumulated_before else "") + data["transcript"].strip()

async def test():
    global accumulated_before
    start = time.monotonic()
    async with websockets.connect(f"{API_URL}/speaking/stt/stream", close_timeout=60) as ws:
        async def sender():
            dur = total_duration_s; n = max(1, int(dur / 0.25))
            sz = max(1, len(audio_bytes) // n); delay = dur / n
            pos = 0
            while pos < len(audio_bytes):
                await ws.send(audio_bytes[pos:pos+sz]); pos += sz
                await asyncio.sleep(delay)
            # DO NOT close the client connection — sit idle so Deepgram's
            # keepalive timeout (1011) fires naturally on dg_ws side.
            await asyncio.sleep(120)  # stay alive 120s, let dg_ws time out
            log("[STT] sender idle expired (120s)")
        async def receiver():
            try:
                async for msg in ws:
                    handle_message(json.loads(msg))
            except websockets.ConnectionClosed as e:
                log(f"[STT] receiver ConnectionClosed code={e.code} reason={e.reason}")
        await asyncio.gather(sender(), receiver())
    total = time.monotonic() - start
    log(f"\nTotal: {total:.1f}s")
    with open("_stt_sim_output.txt", "w") as f: f.write("\n".join(out_lines))

asyncio.run(test())
