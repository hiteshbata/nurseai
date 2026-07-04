"""
Test the backend STT WebSocket proxy end-to-end using the cached _test_audio.webm.
Connects to the already-running backend at localhost:8000.
"""

import asyncio
import json
import os
import sys
import time
import websockets

API_URL = os.environ.get("API_URL", "ws://localhost:8000")
AUDIO_PATH = os.path.join(os.path.dirname(__file__), "_test_audio.webm")
META_PATH = os.path.join(os.path.dirname(__file__), "_test_audio_meta.json")

with open(META_PATH) as f:
    meta = json.load(f)
total_duration_s = meta["total_duration_s"]

with open(AUDIO_PATH, "rb") as f:
    audio_bytes = f.read()

print(f"Audio file: {AUDIO_PATH} ({len(audio_bytes)} bytes, {total_duration_s:.1f}s)")
print(f"Connecting to backend at {API_URL}/speaking/stt/stream\n")

async def test():
    start_time = time.monotonic()

    async with websockets.connect(f"{API_URL}/speaking/stt/stream") as ws:

        async def sender():
            target_chunk_duration_s = 0.25
            num_chunks = max(1, int(total_duration_s / target_chunk_duration_s))
            chunk_size = max(1, len(audio_bytes) // num_chunks)
            delay = total_duration_s / num_chunks
            pos = 0
            while pos < len(audio_bytes):
                chunk = audio_bytes[pos:pos + chunk_size]
                await ws.send(chunk)
                pos += chunk_size
                await asyncio.sleep(delay)
            # All audio sent — now wait for Deepgram to finish processing
            # The connection stays open; sender does NOT close it.
            # Just sleep and let the receiver collect remaining messages.
            await asyncio.sleep(15)

        async def receiver():
            try:
                async for message in ws:
                    elapsed = time.monotonic() - start_time
                    data = json.loads(message)
                    msg_type = data.get("type", "?")
                    if msg_type == "Results":
                        transcript = data.get("transcript", "")
                        is_final = data.get("is_final", False)
                        speech_final = data.get("speech_final", False)
                        if transcript:
                            tag = "FINAL" if is_final else "interim"
                            extra = " SPEECH_FINAL" if speech_final else ""
                            print(f"[{elapsed:6.2f}s] [{tag:7}] \"{transcript}\"{extra}")
                        else:
                            print(f"[{elapsed:6.2f}s] [empty    ] is_final={is_final} speech_final={speech_final}")
                    elif msg_type == "UtteranceEnd":
                        print(f"[{elapsed:6.2f}s] [UtteranceEnd]")
                    elif "error" in data:
                        print(f"[{elapsed:6.2f}s] [ERROR] {data}")
                        break
                    else:
                        print(f"[{elapsed:6.2f}s] [{msg_type}] {json.dumps(data, default=str)[:200]}")
            except websockets.exceptions.ConnectionClosed as e:
                print(f"[ConnectionClosed code={e.code} reason={e.reason}]")

        await asyncio.gather(sender(), receiver())

    total = time.monotonic() - start_time
    print(f"\nSession ended after {total:.1f}s")

if __name__ == "__main__":
    asyncio.run(test())
